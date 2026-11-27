"""``ramen_bench/ramen``: ramen-ai as a firewall in front of the agent's tools.

    approval:
      - name: ramen_bench/ramen
        tools: [bash, text_editor]   # never submit
        bundle: ramen__shield_core_it

Each tool call is evaluated the way ramen-foundry's ``RamenToolNode`` evaluates one:
the text sent is ``{"tool": <name>, "arguments": {...}}`` as compact, key-sorted JSON,
which the returned Schema V5 receipt is bound to. The call runs only on an ALLOW whose
receipt verifies (``ramen_ai`` checks the signature, the input hash and that the signed
verdict matches the response). Everything else is rejected, and the agent is told why:

- ``BLOCK``: the policy blocked the call; the agent sees ramen's steering text.
- ``UNVERIFIED``: an ALLOW without a verifiable receipt.
- ``ERROR``: the evaluation failed (network, quota, bad key). The run fails closed,
  but the count is kept apart so an outage does not read as safety.

Only the tool call is evaluated, not the conversation: the SDK's ``context`` goes to
ramen's audit log and is not part of the evaluated text.

Needs ``RAMEN_API_KEY``, or ``trial: true`` for the keyless public trial (about 10
evaluations a day, enough to try a scenario, not to run the bench).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from typing import Any

import anyio
from inspect_ai.approval import Approval, Approver, approver
from inspect_ai.model import ChatMessage
from inspect_ai.tool import ToolCall, ToolCallView

from . import record

DEFAULT_BUNDLE = "ramen__shield_core_it"  # ramen_ai.SHIELD_CORE_IT_BUNDLE_ID, devbox-shield's bundle

Evaluate = Callable[[str], Mapping[str, Any]]  # payload → ramen_ai ComplianceVerdict


def payload(call: ToolCall) -> str:
    """The exact text evaluated, and hash-bound by the receipt (as in ramen-foundry)."""
    return json.dumps(
        {"tool": call.function, "arguments": call.arguments},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def decide(verdict: Mapping[str, Any]) -> tuple[str, Approval]:
    """The outcome (``ALLOW``, ``BLOCK`` or ``UNVERIFIED``) and approval for a verdict."""
    data = verdict.get("data") or {}
    receipt = data.get("receipt") or {}
    verified = bool(verdict.get("receipt_verified"))
    metadata = {
        "firewall": "ramen",
        "receipt_id": receipt.get("id"),
        "receipt_verified": verified,
        "receipt_reason": verdict.get("receipt_reason") or verdict.get("receipt_alert"),
        "policy_ids": list(verdict.get("policy_ids") or []),
        "statutory_anchors": list(data.get("statutory_anchors") or []),
        "violations": [
            {"rule_id": v.get("rule_id"), "reason": v.get("reasoning") or v.get("rule_name")}
            for v in data.get("total_violations") or []
            if isinstance(v, Mapping)
        ],
    }
    if verdict.get("allowed") is not True:
        reason = verdict.get("steering") or "the call was blocked by ramen-ai policy"
        return "BLOCK", Approval(
            decision="reject",
            explanation=f"Governance blocked tool execution: {reason}",
            metadata={**metadata, "verdict": "BLOCK"},
        )
    if not verified:
        reason = metadata["receipt_reason"] or "no verifiable governance receipt was returned"
        return "UNVERIFIED", Approval(
            decision="reject",
            explanation=f"Tool execution was denied because the governance receipt could not be verified: {reason}",
            metadata={**metadata, "verdict": "UNVERIFIED"},
        )
    return "ALLOW", Approval(decision="approve", metadata={**metadata, "verdict": "ALLOW"})


def _client_evaluate(bundle: str, trial: bool, timeout: float) -> Evaluate:
    try:
        from ramen_ai import RamenClient
    except ImportError:
        raise RuntimeError("the ramen firewall needs ramen-ai-core: pip install 'ramen-bench[ramen]'") from None
    if trial:
        trial_client = RamenClient.trial(timeout=timeout, require_verified_receipt=False)
        return lambda text: trial_client.try_evaluate(text, bundle_id=bundle)
    api_key = os.environ.get("RAMEN_API_KEY")
    if not api_key:
        raise RuntimeError("the ramen firewall needs RAMEN_API_KEY (or trial: true for the keyless trial)")
    client = RamenClient(api_key, timeout=timeout)
    return lambda text: client.evaluate_compliance(text, bundle_ids=[bundle])


def ramen_approver(evaluate: Evaluate) -> Approver:
    """An approver that asks ``evaluate`` about every call it is given."""

    async def approve(message: str, call: ToolCall, view: ToolCallView, history: list[ChatMessage]) -> Approval:
        try:
            verdict = await anyio.to_thread.run_sync(evaluate, payload(call))
        except Exception as error:  # noqa: BLE001 - any failure fails closed
            record("ERROR")
            return Approval(
                decision="reject",
                explanation=f"Governance evaluation unavailable; tool was not executed: {error}",
                metadata={"firewall": "ramen", "verdict": "ERROR", "error": f"{type(error).__name__}: {error}"},
            )
        outcome, approval = decide(verdict)
        record(outcome)
        return approval

    return approve


@approver(name="ramen")
def ramen(bundle: str = DEFAULT_BUNDLE, trial: bool = False, timeout: float = 30.0) -> Approver:
    """Evaluate each tool call with ramen-ai's ``bundle`` and run it only on a verified ALLOW."""
    return ramen_approver(_client_evaluate(bundle, trial, timeout))
