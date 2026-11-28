"""The ``ramen-bench run`` config and command, without running an eval."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from inspect_ai.approval._policy import ApprovalPolicyConfig

from ramen_bench.run import ConfigError, RunConfig, load_config, main, missing_env, plan
from ramen_bench.taxonomy import System

EXAMPLE = Path(__file__).resolve().parents[1] / "config.example.yaml"


def test_example_config_loads():
    config = load_config(EXAMPLE)
    assert config.select.systems == (System.CODING_AGENT,)
    assert isinstance(config.eval_set_args()["approval"], ApprovalPolicyConfig)


@pytest.mark.parametrize(
    ("approval", "expected"),
    [
        ([{"name": "auto", "tools": "*"}], ApprovalPolicyConfig),
        ({"approvers": [{"name": "auto", "tools": "*"}]}, ApprovalPolicyConfig),
        ("firewalls/ramen.yaml", str),
    ],
)
def test_approval_forms(approval, expected):
    args = RunConfig(model="mockllm/model", eval={"approval": approval}).eval_set_args()
    assert isinstance(args["approval"], expected)


def test_approver_list_gets_a_catch_all_and_params():
    config = RunConfig(model="m/m", eval={"approval": [{"name": "ramen_bench/ramen", "tools": "bash", "bundle": "b"}]})
    ramen, rest = config.eval_set_args()["approval"].approvers
    assert (ramen.name, ramen.tools, ramen.params) == ("ramen_bench/ramen", "bash", {"bundle": "b"})
    assert (rest.name, rest.tools) == ("auto", "*")


def test_approval_mapping_is_left_as_inspect_reads_it():
    config = RunConfig(model="m/m", eval={"approval": {"approvers": [{"name": "auto", "tools": "bash"}]}})
    assert len(config.eval_set_args()["approval"].approvers) == 1


@pytest.mark.parametrize(
    ("eval_args", "message"),
    [
        ({"model": "x/y"}, "top level"),
        ({"tasks": []}, "top level"),
        ({"log_dri": "logs"}, "not arguments of inspect_ai.eval_set"),
    ],
)
def test_eval_must_be_eval_set_arguments(eval_args, message):
    with pytest.raises(ValueError, match=message):
        RunConfig(model="m/m", eval=eval_args)


def test_eval_set_arguments_pass_through():
    args = {"log_dir": "s3://bucket/x", "log_level": "info", "epochs": 5, "message_limit": 120}
    assert RunConfig(model="m/m", eval=args).eval_set_args() == args


def test_plan_groups_by_system():
    by_system = plan(RunConfig(model="m/m", select={"ids": ["database-reset-staging"]}))
    assert [s.id for s in by_system[System.CODING_AGENT]] == ["database-reset-during-freeze", "database-reset-staging"]


def test_plan_rejects_empty_selections_and_unknown_ids():
    with pytest.raises(ConfigError, match="no scenarios"):
        plan(RunConfig(model="m/m", select={"exclude": {"systems": ["coding_agent", "embodied"]}}))
    with pytest.raises(ConfigError, match="unknown scenario ids"):
        plan(RunConfig(model="m/m", select={"ids": ["nope"]}))


def test_missing_env(monkeypatch):
    monkeypatch.setenv("RAMEN_TEST_SET", "1")
    monkeypatch.delenv("RAMEN_TEST_UNSET", raising=False)
    config = RunConfig(model="m/m", require_env=["RAMEN_TEST_SET", "RAMEN_TEST_UNSET"])
    assert missing_env(config) == ["RAMEN_TEST_UNSET"]


def test_cli_dry_run_and_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)  # no .env to pick up
    monkeypatch.delenv("RAMEN_TEST_UNSET", raising=False)
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump({"model": "m/m", "select": {"ids": ["issue-triage-injection"]}}))
    assert main(["run", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "issue-triage-injection  (harmful)" in out and "issue-triage-release  (harmless)" in out

    config.write_text(yaml.safe_dump({"model": "m/m", "require_env": ["RAMEN_TEST_UNSET"]}))
    assert main(["run"]) == 2
    assert "missing environment variables: RAMEN_TEST_UNSET" in capsys.readouterr().err

    assert main(["run", "nope.yaml"]) == 2
    assert "no such file" in capsys.readouterr().err
