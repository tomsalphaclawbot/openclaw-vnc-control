"""
Phase 15 — Workflow Runner unit tests.
Tests vnc-workflow.py without any VNC connection.
"""

from __future__ import annotations

import json
import os
import sys
import subprocess
import tempfile
from pathlib import Path

import pytest

# ── locate scripts ────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent.resolve()
_WORKFLOW_SCRIPT = _ROOT / "vnc-workflow.py"

# ── import module under test directly ────────────────────────────────────
sys.path.insert(0, str(_ROOT))
from vnc_workflow import (  # noqa: E402
    validate_workflow,
    interpolate,
    evaluate_when,
    run_workflow,
    load_workflow_str,
    WorkflowError,
)

# ── helpers ───────────────────────────────────────────────────────────────
MINIMAL_WF = {
    "name": "test",
    "steps": [{"command": "echo", "args": ["hi"]}],
}


def wf_json(wf: dict) -> str:
    return json.dumps(wf)


# ══════════════════════════════════════════════════════════════════════════
# Validation tests
# ══════════════════════════════════════════════════════════════════════════

class TestValidation:
    def test_valid_minimal(self):
        errors = validate_workflow(MINIMAL_WF)
        assert errors == []

    def test_missing_name(self):
        wf = {"steps": [{"command": "echo"}]}
        errors = validate_workflow(wf)
        assert any("name" in e for e in errors)

    def test_missing_steps(self):
        wf = {"name": "x"}
        errors = validate_workflow(wf)
        assert any("steps" in e for e in errors)

    def test_empty_steps(self):
        wf = {"name": "x", "steps": []}
        errors = validate_workflow(wf)
        assert any("empty" in e for e in errors)

    def test_unknown_command(self):
        wf = {"name": "x", "steps": [{"command": "warp_drive"}]}
        errors = validate_workflow(wf)
        assert any("warp_drive" in e for e in errors)

    def test_duplicate_step_ids(self):
        wf = {
            "name": "x",
            "steps": [
                {"id": "a", "command": "echo"},
                {"id": "a", "command": "sleep", "args": ["0.1"]},
            ],
        }
        errors = validate_workflow(wf)
        assert any("duplicate" in e.lower() for e in errors)

    def test_invalid_on_error(self):
        wf = {
            "name": "x",
            "steps": [{"command": "echo", "on_error": "explode"}],
        }
        errors = validate_workflow(wf)
        assert any("on_error" in e for e in errors)

    def test_invalid_retry_max(self):
        wf = {
            "name": "x",
            "steps": [{"command": "echo", "retry_max": -1}],
        }
        errors = validate_workflow(wf)
        assert any("retry_max" in e for e in errors)

    def test_args_must_be_list(self):
        wf = {
            "name": "x",
            "steps": [{"command": "echo", "args": "not-a-list"}],
        }
        errors = validate_workflow(wf)
        assert any("args" in e for e in errors)

    def test_valid_all_fields(self):
        wf = {
            "name": "full",
            "description": "full test",
            "variables": {"x": "1"},
            "steps": [
                {
                    "id": "s1",
                    "command": "echo",
                    "args": ["hello"],
                    "on_error": "continue",
                    "retry_max": 2,
                    "retry_delay": 0.5,
                    "timeout": 30,
                    "save_output": "s1_out",
                }
            ],
        }
        errors = validate_workflow(wf)
        assert errors == []


# ══════════════════════════════════════════════════════════════════════════
# Variable interpolation tests
# ══════════════════════════════════════════════════════════════════════════

class TestInterpolation:
    def test_simple_variable(self):
        result = interpolate("Hello {{name}}", {"name": "Alpha"}, {})
        assert result == "Hello Alpha"

    def test_step_output_variable(self):
        outputs = {"my_step": {"x": 100, "y": 200}}
        result = interpolate("{{my_step.x}}", {}, outputs)
        assert result == "100"

    def test_nested_data(self):
        outputs = {"step1": {"data": {"native_x": 42}}}
        result = interpolate("{{step1.data.native_x}}", {}, outputs)
        assert result == "42"

    def test_interpolate_list(self):
        result = interpolate(["{{a}}", "{{b}}"], {"a": "1", "b": "2"}, {})
        assert result == ["1", "2"]

    def test_interpolate_dict(self):
        result = interpolate({"key": "{{val}}"}, {"val": "ok"}, {})
        assert result == {"key": "ok"}

    def test_no_substitution_needed(self):
        result = interpolate("plain string", {}, {})
        assert result == "plain string"

    def test_missing_variable_raises(self):
        with pytest.raises(WorkflowError, match="Variable not found"):
            interpolate("{{missing}}", {}, {})

    def test_numeric_value_stringified(self):
        result = interpolate("{{n}}", {"n": 42}, {})
        assert result == "42"

    def test_multiple_vars_in_one_string(self):
        result = interpolate("{{a}} + {{b}}", {"a": "X", "b": "Y"}, {})
        assert result == "X + Y"

    def test_variables_override_order(self):
        # step_outputs take precedence when key matches step id
        outputs = {"x": "from_step"}
        result = interpolate("{{x}}", {"x": "from_var"}, outputs)
        # Top-level variables are checked first
        assert result == "from_var"


# ══════════════════════════════════════════════════════════════════════════
# Workflow execution tests (built-ins only — no VNC)
# ══════════════════════════════════════════════════════════════════════════

class TestWorkflowExecution:
    def test_echo_step(self):
        wf = {
            "name": "echo-test",
            "steps": [{"id": "greet", "command": "echo", "args": ["hello"]}],
        }
        result = run_workflow(wf)
        assert result["ok"] is True
        assert result["steps_passed"] == 1
        assert result["steps_failed"] == 0

    def test_sleep_step(self):
        wf = {
            "name": "sleep-test",
            "steps": [{"id": "nap", "command": "sleep", "args": ["0.01"]}],
        }
        result = run_workflow(wf)
        assert result["ok"] is True
        assert result["steps_passed"] == 1
        assert result["duration_ms"] >= 10

    def test_multi_step_all_pass(self):
        wf = {
            "name": "multi",
            "steps": [
                {"id": "s1", "command": "echo", "args": ["one"]},
                {"id": "s2", "command": "sleep", "args": ["0.01"]},
                {"id": "s3", "command": "echo", "args": ["three"]},
            ],
        }
        result = run_workflow(wf)
        assert result["ok"] is True
        assert result["steps_passed"] == 3
        assert result["steps_failed"] == 0
        assert len(result["steps"]) == 3

    def test_step_output_saved(self):
        wf = {
            "name": "save-test",
            "steps": [
                {"id": "greet", "command": "echo", "args": ["hi"], "save_output": "msg"},
            ],
        }
        result = run_workflow(wf)
        assert result["ok"] is True
        # saved_as should appear in step record
        assert result["steps"][0].get("saved_as") == "msg"

    def test_variable_interpolation_in_step(self):
        wf = {
            "name": "var-test",
            "variables": {"greeting": "world"},
            "steps": [
                {"id": "s1", "command": "echo", "args": ["Hello {{greeting}}"]},
            ],
        }
        result = run_workflow(wf)
        assert result["ok"] is True
        assert result["steps"][0]["args"] == ["Hello world"]

    def test_extra_vars_override(self):
        wf = {
            "name": "override-test",
            "variables": {"x": "default"},
            "steps": [
                {"id": "s1", "command": "echo", "args": ["{{x}}"]},
            ],
        }
        result = run_workflow(wf, extra_vars={"x": "overridden"})
        assert result["ok"] is True
        assert result["steps"][0]["args"] == ["overridden"]

    def test_dry_run_returns_plan(self):
        wf = {
            "name": "dry-run-test",
            "steps": [
                {"id": "s1", "command": "echo", "args": ["hi"]},
                {"id": "s2", "command": "sleep", "args": ["1"]},
            ],
        }
        result = run_workflow(wf, dry_run=True)
        assert result["ok"] is True
        assert result["dry_run"] is True
        assert result["steps_total"] == 2
        # No actual execution
        assert "steps_passed" not in result

    def test_step_chain_via_output(self):
        """Step 2 uses output from step 1 via {{step_id.field}}."""
        # Both steps are echo; step 2's args will reference step 1's resolved output
        # Since "echo" stores {"message": ...}, reference it via {{s1.message}}
        wf = {
            "name": "chain-test",
            "steps": [
                {"id": "s1", "command": "echo", "args": ["alpha"]},
                {"id": "s2", "command": "echo", "args": ["echo says: {{s1.message}}"]},
            ],
        }
        result = run_workflow(wf)
        assert result["ok"] is True
        assert result["steps"][1]["args"] == ["echo says: alpha"]

    def test_validation_error_prevents_run(self):
        wf = {"name": "bad"}  # missing steps
        result = run_workflow(wf)
        assert result["ok"] is False
        assert "validation_errors" in result

    def test_missing_variable_fails_step(self):
        wf = {
            "name": "missing-var",
            "steps": [
                {"id": "s1", "command": "echo", "args": ["{{does_not_exist}}"]},
            ],
        }
        result = run_workflow(wf)
        assert result["ok"] is False
        assert result["steps_failed"] == 1


# ══════════════════════════════════════════════════════════════════════════
# on_error behavior
# ══════════════════════════════════════════════════════════════════════════

class TestOnError:
    def test_on_error_stop_skips_remaining(self):
        """A failing step with on_error=stop skips subsequent steps."""
        wf = {
            "name": "stop-test",
            "steps": [
                # This step will fail: missing variable
                {"id": "fail", "command": "echo", "args": ["{{missing}}"], "on_error": "stop"},
                {"id": "after", "command": "echo", "args": ["should skip"]},
            ],
        }
        result = run_workflow(wf)
        assert result["ok"] is False
        assert result["steps_failed"] == 1
        assert result["steps_skipped"] == 1
        skipped = [s for s in result["steps"] if s.get("skipped")]
        assert len(skipped) == 1
        assert skipped[0]["id"] == "after"

    def test_on_error_continue_runs_next(self):
        """A failing step with on_error=continue still runs next step."""
        wf = {
            "name": "continue-test",
            "steps": [
                {"id": "fail", "command": "echo", "args": ["{{missing}}"], "on_error": "continue"},
                {"id": "after", "command": "echo", "args": ["runs despite failure"]},
            ],
        }
        result = run_workflow(wf)
        # Not ok overall (had a failure) but second step ran
        assert result["steps_failed"] == 1
        assert result["steps_passed"] == 1
        assert result["steps_skipped"] == 0


# ══════════════════════════════════════════════════════════════════════════
# load_workflow_str
# ══════════════════════════════════════════════════════════════════════════

class TestLoader:
    def test_load_json_string(self):
        wf = load_workflow_str(wf_json(MINIMAL_WF), fmt="json")
        assert wf["name"] == "test"

    def test_load_yaml_string(self):
        pytest.importorskip("yaml")
        import yaml
        text = yaml.dump(MINIMAL_WF)
        wf = load_workflow_str(text, fmt="yaml")
        assert wf["name"] == "test"

    def test_load_invalid_json_raises(self):
        with pytest.raises(Exception):
            load_workflow_str("not json", fmt="json")


# ══════════════════════════════════════════════════════════════════════════
# CLI smoke tests
# ══════════════════════════════════════════════════════════════════════════

class TestCLI:
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(_WORKFLOW_SCRIPT)] + list(args),
            capture_output=True, text=True, timeout=15,
        )

    def test_cli_list(self):
        proc = self._run("list")
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert data["ok"] is True

    def test_cli_run_example(self):
        proc = self._run("run", "--example")
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert data["ok"] is True
        assert data["steps_passed"] >= 1

    def test_cli_run_example_dry_run(self):
        proc = self._run("run", "--example", "--dry-run")
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert data["dry_run"] is True

    def test_cli_validate_valid(self):
        wf = {"name": "valid", "steps": [{"command": "echo", "args": ["hi"]}]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(wf, f)
            fpath = f.name
        try:
            proc = self._run("validate", fpath)
            assert proc.returncode == 0
            data = json.loads(proc.stdout)
            assert data["ok"] is True
        finally:
            os.unlink(fpath)

    def test_cli_validate_invalid(self):
        wf = {"name": "bad"}  # no steps
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(wf, f)
            fpath = f.name
        try:
            proc = self._run("validate", fpath)
            assert proc.returncode != 0
            data = json.loads(proc.stdout)
            assert data["ok"] is False
        finally:
            os.unlink(fpath)

    def test_cli_run_file_with_var_override(self):
        wf = {
            "name": "var-test",
            "variables": {"msg": "default"},
            "steps": [{"id": "s1", "command": "echo", "args": ["{{msg}}"]}],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(wf, f)
            fpath = f.name
        try:
            proc = self._run("run", fpath, "--var", "msg=custom")
            assert proc.returncode == 0
            data = json.loads(proc.stdout)
            assert data["ok"] is True
            assert data["steps"][0]["args"] == ["custom"]
        finally:
            os.unlink(fpath)

    def test_cli_run_missing_file(self):
        proc = self._run("run", "/tmp/definitely_does_not_exist_abc123.json")
        assert proc.returncode != 0

    def test_cli_no_args_shows_help(self):
        proc = self._run()
        # Should not crash — exit 0 or non-zero with usage info
        assert proc.stdout or proc.stderr or proc.returncode == 0


# ══════════════════════════════════════════════════════════════════════════
# Phase 16 — Conditional Step Execution (when)
# ══════════════════════════════════════════════════════════════════════════

class TestEvaluateWhen:
    """Unit tests for evaluate_when()."""

    # ── Literal shortcuts ────────────────────────────────────────────────

    def test_literal_true(self):
        assert evaluate_when("true", {}, {}) is True

    def test_literal_false(self):
        assert evaluate_when("false", {}, {}) is False

    def test_literal_true_uppercase(self):
        assert evaluate_when("True", {}, {}) is True

    # ── Equality ==  ────────────────────────────────────────────────────

    def test_string_eq_match(self):
        assert evaluate_when("{{mode}} == verbose", {"mode": "verbose"}, {}) is True

    def test_string_eq_no_match(self):
        assert evaluate_when("{{mode}} == verbose", {"mode": "quiet"}, {}) is False

    def test_bool_eq_true(self):
        # ok field from step output is a Python bool
        assert evaluate_when("{{s1.ok}} == true", {}, {"s1": {"ok": True}}) is True

    def test_bool_eq_false_literal(self):
        assert evaluate_when("{{s1.ok}} == false", {}, {"s1": {"ok": False}}) is True

    def test_bool_eq_mismatch(self):
        assert evaluate_when("{{s1.ok}} == true", {}, {"s1": {"ok": False}}) is False

    # ── Inequality != ────────────────────────────────────────────────────

    def test_string_neq_different(self):
        assert evaluate_when("{{mode}} != quiet", {"mode": "verbose"}, {}) is True

    def test_string_neq_same(self):
        assert evaluate_when("{{mode}} != verbose", {"mode": "verbose"}, {}) is False

    # ── Numeric comparisons ──────────────────────────────────────────────

    def test_numeric_gt_true(self):
        assert evaluate_when("{{count}} > 3", {"count": "5"}, {}) is True

    def test_numeric_gt_false(self):
        assert evaluate_when("{{count}} > 10", {"count": "5"}, {}) is False

    def test_numeric_gte_equal(self):
        assert evaluate_when("{{count}} >= 5", {"count": "5"}, {}) is True

    def test_numeric_lt_true(self):
        assert evaluate_when("{{count}} < {{threshold}}", {"count": "3", "threshold": "5"}, {}) is True

    def test_numeric_lt_false(self):
        assert evaluate_when("{{count}} < {{threshold}}", {"count": "7", "threshold": "5"}, {}) is False

    def test_numeric_lte_equal(self):
        assert evaluate_when("{{count}} <= 5", {"count": "5"}, {}) is True

    # ── Step output reference ────────────────────────────────────────────

    def test_step_output_eq(self):
        assert evaluate_when("{{check.result}} == pass", {}, {"check": {"result": "pass"}}) is True

    def test_step_output_neq(self):
        assert evaluate_when("{{check.result}} != fail", {}, {"check": {"result": "pass"}}) is True

    # ── Error cases ──────────────────────────────────────────────────────

    def test_unknown_variable_raises(self):
        with pytest.raises(WorkflowError, match="when"):
            evaluate_when("{{missing_var}} == x", {}, {})

    def test_non_numeric_gt_raises(self):
        with pytest.raises(WorkflowError, match="non-numeric"):
            evaluate_when("{{s}} > 5", {"s": "hello"}, {})


class TestConditionalStepExecution:
    """Integration tests: when in run_workflow() using builtin commands only."""

    def _wf(self, steps, variables=None):
        wf = {"name": "cond-test", "steps": steps}
        if variables:
            wf["variables"] = variables
        return wf

    def test_when_true_step_runs(self):
        wf = self._wf([
            {"id": "s1", "command": "echo", "args": ["hello"], "when": "true"},
        ])
        result = run_workflow(wf)
        assert result["ok"] is True
        assert not result["steps"][0].get("skipped")  # not skipped
        assert result["steps_passed"] == 1
        assert result["steps_conditional_skipped"] == 0

    def test_when_false_step_skipped(self):
        wf = self._wf([
            {"id": "s1", "command": "echo", "args": ["should skip"], "when": "false"},
            {"id": "s2", "command": "echo", "args": ["should run"]},
        ])
        result = run_workflow(wf)
        assert result["ok"] is True
        assert result["steps"][0]["skipped"] is True
        assert result["steps"][1].get("skipped") is not True
        assert result["steps_conditional_skipped"] == 1
        assert result["steps_passed"] == 1  # s2 ran

    def test_when_variable_match(self):
        wf = self._wf(
            steps=[
                {"id": "s1", "command": "echo", "args": ["verbose"], "when": "{{mode}} == verbose"},
                {"id": "s2", "command": "echo", "args": ["quiet"], "when": "{{mode}} == quiet"},
            ],
            variables={"mode": "verbose"},
        )
        result = run_workflow(wf)
        assert result["ok"] is True
        assert result["steps"][0].get("skipped") is not True  # s1 ran
        assert result["steps"][1]["skipped"] is True           # s2 skipped
        assert result["steps_conditional_skipped"] == 1
        assert result["steps_passed"] == 1

    def test_when_step_output_ok_true(self):
        """Step 2 runs only if step 1 succeeded (ok==true)."""
        wf = self._wf(steps=[
            {"id": "check", "command": "echo", "args": ["ping"]},
            {"id": "follow", "command": "echo", "args": ["ok!"], "when": "{{check.ok}} == true"},
        ])
        result = run_workflow(wf)
        assert result["ok"] is True
        assert result["steps"][0].get("skipped") is not True
        assert result["steps"][1].get("skipped") is not True
        assert result["steps_passed"] == 2
        assert result["steps_conditional_skipped"] == 0

    def test_when_numeric_comparison(self):
        """Steps guarded by numeric thresholds."""
        wf = self._wf(
            steps=[
                {"id": "lo", "command": "echo", "args": ["low"],  "when": "{{x}} < 5"},
                {"id": "hi", "command": "echo", "args": ["high"], "when": "{{x}} >= 5"},
            ],
            variables={"x": "3"},
        )
        result = run_workflow(wf)
        assert result["ok"] is True
        assert result["steps"][0].get("skipped") is not True  # x=3 < 5 → run
        assert result["steps"][1]["skipped"] is True           # x=3 >= 5 → skip
        assert result["steps_conditional_skipped"] == 1

    def test_conditional_skipped_step_not_counted_as_failure(self):
        """Conditional skips must not set ok=False on the workflow."""
        wf = self._wf(steps=[
            {"id": "s1", "command": "echo", "args": ["a"], "when": "false"},
            {"id": "s2", "command": "echo", "args": ["a"], "when": "false"},
        ])
        result = run_workflow(wf)
        assert result["ok"] is True
        assert result["steps_failed"] == 0
        assert result["steps_conditional_skipped"] == 2

    def test_skipped_step_registers_in_outputs(self):
        """Downstream step can reference {{skipped_step.skipped}} == true."""
        wf = self._wf(steps=[
            {"id": "maybe", "command": "echo", "args": ["skip me"], "when": "false"},
            {
                "id": "report",
                "command": "echo",
                "args": ["skipped={{maybe.skipped}}"],
                "when": "{{maybe.skipped}} == true",
            },
        ])
        result = run_workflow(wf)
        assert result["ok"] is True
        # Both steps resolve: maybe is conditionally skipped; report also skipped
        # (because its when reads the saved output {{maybe.skipped}} == True → runs)
        assert result["steps_conditional_skipped"] >= 1

    def test_conditional_workflow_yaml_file(self, tmp_path):
        """Load and execute the sample conditional workflow YAML."""
        wf_path = Path(__file__).parent.parent / "workflows" / "conditional-check.yaml"
        if not wf_path.exists():
            pytest.skip("conditional-check.yaml not found")
        from vnc_workflow import load_workflow
        wf = load_workflow(str(wf_path))
        result = run_workflow(wf)
        assert result["ok"] is True
        # mode=verbose → verbose steps run, quiet-note skipped
        cond_skip_ids = [s["id"] for s in result["steps"] if s.get("skipped") and s.get("when")]
        assert "quiet-note" in cond_skip_ids
        assert "above-threshold" in cond_skip_ids  # count=3 < threshold=5, so above skipped
