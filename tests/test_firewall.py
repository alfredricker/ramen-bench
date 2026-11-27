"""The ramen firewall, through the real ``ramen_ai`` client and a stand-in API.

The stand-in signs Schema V5 receipts with a test key, so receipt verification runs
for real; nothing goes over the network.
"""

from __future__ import annotations

import base64
import hashlib
import json

import anyio
import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from inspect_ai.tool import ToolCall
from ramen_ai import RamenClient

from ramen_bench.harness.firewalls import ramen as firewall

KEY = Ed25519PrivateKey.generate()
KID = "test_key"
PUBLIC_KEYS = {KID: base64.b64encode(KEY.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)).decode()}
EXECUTED_AT = "2026-11-27T12:00:00Z"
POLICY_IDS = ["11111111-1111-1111-1111-111111111111"]


def receipt(input_text: str, verdict: int, *, key: Ed25519PrivateKey = KEY) -> dict:
    canonical = json.dumps(
        {
            "schema_version": "5.0",
            "id": "rcpt_1",
            "kid": KID,
            "payload_hash": hashlib.sha256(input_text.encode()).hexdigest(),
            "verdict": verdict,
            "timestamp": EXECUTED_AT,
            "policy_ids": POLICY_IDS,
            "statutory_anchors": [],
        },
        sort_keys=True,
    )
    signature = base64.urlsafe_b64encode(key.sign(canonical.encode())).decode().rstrip("=")
    return {"id": "rcpt_1", "schema_version": "5.0", "kid": KID, "signature": signature, "canonical_payload": canonical}


def api(respond):
    """A RamenClient whose API answers with ``respond(input_text)`` (the ``data`` payload)."""
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        return httpx.Response(200, json={"data": respond(body["input"])})

    client = RamenClient("test-key", public_keys=PUBLIC_KEYS, transport=httpx.MockTransport(handler))
    return (lambda text: client.evaluate_compliance(text, bundle_ids=["ramen__shield_core_it"])), sent


def data(allowed: bool, rcpt: dict | None, **extra) -> dict:
    return {
        "allowed": allowed,
        "policy_ids": POLICY_IDS,
        "executed_at": EXECUTED_AT,
        "statutory_anchors": [],
        **({"receipt": rcpt} if rcpt else {}),
        **extra,
    }


CALL = ToolCall(id="1", function="bash", arguments={"cmd": "python scripts/reset_db.py"})


def approve(evaluate):
    return anyio.run(firewall.ramen_approver(evaluate), "", CALL, None, [])


def test_payload_matches_ramen_foundry():
    assert firewall.payload(CALL) == '{"arguments":{"cmd":"python scripts/reset_db.py"},"tool":"bash"}'


def test_verified_allow_runs_the_call():
    evaluate, sent = api(lambda text: data(True, receipt(text, 1)))
    approval = approve(evaluate)
    assert approval.decision == "approve"
    assert approval.metadata["verdict"] == "ALLOW" and approval.metadata["receipt_id"] == "rcpt_1"
    assert sent == [{"input": firewall.payload(CALL), "bundle_ids": ["ramen__shield_core_it"]}]


def test_block_is_rejected_with_steering():
    violation = {"rule_id": "R1", "reasoning": "Destructive reset", "recovery_instruction": "Use a test database."}
    evaluate, _ = api(lambda text: data(False, receipt(text, 0), total_violations=[violation]))
    approval = approve(evaluate)
    assert approval.decision == "reject"
    assert approval.explanation == "Governance blocked tool execution: Use a test database."
    assert approval.metadata["verdict"] == "BLOCK"
    assert approval.metadata["violations"] == [{"rule_id": "R1", "reason": "Destructive reset"}]


@pytest.mark.parametrize(
    "respond",
    [
        lambda text: data(True, None),  # no receipt
        lambda text: data(True, receipt(text, 0)),  # a BLOCK receipt wrapped in allowed: true
        lambda text: data(True, receipt("something else", 1)),  # signed over other input
        lambda text: data(True, receipt(text, 1, key=Ed25519PrivateKey.generate())),  # wrong key
    ],
)
def test_allow_without_a_verifiable_receipt_is_rejected(respond):
    evaluate, _ = api(respond)
    approval = approve(evaluate)
    assert approval.decision == "reject"
    assert approval.metadata["verdict"] == "UNVERIFIED"


def test_failures_fail_closed():
    def unavailable(text):
        raise httpx.ConnectError("connection refused")

    approval = approve(unavailable)
    assert approval.decision == "reject"
    assert approval.metadata["verdict"] == "ERROR"
    assert "connection refused" in approval.explanation


def test_api_errors_fail_closed():
    def handler(request):
        return httpx.Response(401, json={"error": "bad key"})

    client = RamenClient("test-key", public_keys=PUBLIC_KEYS, transport=httpx.MockTransport(handler))
    approval = approve(lambda text: client.evaluate_compliance(text, bundle_ids=["b"]))
    assert approval.metadata["verdict"] == "ERROR"


def test_needs_a_key_unless_trial(monkeypatch):
    monkeypatch.delenv("RAMEN_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="RAMEN_API_KEY"):
        firewall.ramen()
    firewall.ramen(trial=True)  # builds without a key; nothing is sent until a call
