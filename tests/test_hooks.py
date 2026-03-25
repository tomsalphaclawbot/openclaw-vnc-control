"""
Unit tests for Phase 17: Workflow Event Hooks.

Tests cover:
- fire_hook() function (dispatch, env injection, error handling)
- _resolve_step_hooks() (merge logic)
- Hook integration in execute_step() (step_start, step_end, step_fail)
- Hook integration in run_workflow() (workflow_complete)
- Per-step hook overrides
- Empty/disabled hooks
- hook_on_error behavior
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

import vnc_workflow  # noqa: E402
from vnc_workflow import (
    fire_hook,
    _resolve_step_hooks,
    execute_step,
    run_workflow,
)


# ── fire_hook() tests ──────────────────────────────────────────────────────

class TestFireHook:
    """Tests for the fire_hook function."""

    def test_empty_hook_is_skipped(self):
        """Empty or whitespace-only hook command should be skipped."""
        result = fire_hook("", {}, {}, {})
        assert result["ok"] is True
        assert result.get("skipped") is True

    def test_whitespace_hook_is_skipped(self):
        result = fire_hook("   ", {}, {}, {})
        assert result["ok"] is True
        assert result.get("skipped") is True

    def test_successful_hook_execution(self):
        """Hook that echoes should succeed."""
        result = fire_hook("echo hello", {}, {}, {})
        assert result["ok"] is True
        assert result["returncode"] == 0
        assert "hello" in result["stdout"]

    def test_failed_hook_returns_nonzero(self):
        """Hook with exit 1 should report ok=False."""
        result = fire_hook("exit 1", {}, {}, {})
        assert result["ok"] is False
        assert result["returncode"] == 1

    def test_env_vars_injected(self):
        """Hook should receive environment variables."""
        hook_env = {"STEP_ID": "my-step", "STEP_OK": "true"}
        result = fire_hook("echo $STEP_ID", hook_env, {}, {})
        assert result["ok"] is True
        assert "my-step" in result["stdout"]

    def test_env_workflow_name(self):
        hook_env = {"WORKFLOW_NAME": "test-wf", "STEP_ID": "s1", "STEP_OK": "true"}
        result = fire_hook("echo $WORKFLOW_NAME", hook_env, {}, {})
        assert result["ok"] is True
        assert "test-wf" in result["stdout"]

    def test_interpolation_in_hook_command(self):
        """Variables should be interpolated in hook command string."""
        variables = {"target": "world"}
        result = fire_hook("echo {{target}}", {}, variables, {})
        assert result["ok"] is True
        assert "world" in result["stdout"]

    def test_hook_timeout(self):
        """Hook that exceeds timeout should report failure."""
        with patch("vnc_workflow.subprocess.run") as mock_run:
            import subprocess
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="sleep", timeout=30)
            result = fire_hook("sleep 999", {}, {}, {})
            assert result["ok"] is False
            assert "timed out" in result.get("error", "")


# ── _resolve_step_hooks() tests ──────────────────────────────────────────

class TestResolveStepHooks:
    """Tests for the hook merge logic."""

    def test_no_step_hooks_returns_workflow_hooks(self):
        wf_hooks = {"step_start": "echo start", "step_end": "echo end"}
        step = {"command": "screenshot"}
        result = _resolve_step_hooks(step, wf_hooks)
        assert result == wf_hooks

    def test_step_hooks_override_workflow_hooks(self):
        wf_hooks = {"step_start": "echo global-start", "step_end": "echo global-end"}
        step = {"command": "click", "hooks": {"step_start": "echo step-start"}}
        result = _resolve_step_hooks(step, wf_hooks)
        assert result["step_start"] == "echo step-start"
        assert result["step_end"] == "echo global-end"

    def test_empty_string_disables_hook(self):
        wf_hooks = {"step_start": "echo global", "step_fail": "echo fail"}
        step = {"command": "click", "hooks": {"step_start": ""}}
        result = _resolve_step_hooks(step, wf_hooks)
        assert result["step_start"] == ""
        assert result["step_fail"] == "echo fail"

    def test_step_adds_new_hook(self):
        wf_hooks = {"step_start": "echo start"}
        step = {"command": "click", "hooks": {"step_fail": "echo oops"}}
        result = _resolve_step_hooks(step, wf_hooks)
        assert result["step_start"] == "echo start"
        assert result["step_fail"] == "echo oops"


# ── execute_step() hook integration ────────────────────────────────────────

class TestExecuteStepHooks:
    """Tests for hook firing within execute_step."""

    def test_step_start_hook_fires(self):
        """step_start hook should fire before step execution."""
        step = {"id": "greet", "command": "echo", "args": ["hi"]}
        wf_hooks = {"step_start": "echo started-$STEP_ID"}
        ok, record = execute_step(
            step, {}, {}, workflow_hooks=wf_hooks, workflow_name="test"
        )
        assert ok is True
        assert "hooks" in record
        start_hooks = [h for h in record["hooks"] if h["event"] == "step_start"]
        assert len(start_hooks) == 1
        assert start_hooks[0]["ok"] is True
        assert "started-greet" in start_hooks[0]["stdout"]

    def test_step_end_hook_fires(self):
        """step_end hook should fire after step execution."""
        step = {"id": "msg", "command": "echo", "args": ["ok"]}
        wf_hooks = {"step_end": "echo ended-$STEP_ID-ok=$STEP_OK"}
        ok, record = execute_step(
            step, {}, {}, workflow_hooks=wf_hooks, workflow_name="test"
        )
        assert ok is True
        end_hooks = [h for h in record["hooks"] if h["event"] == "step_end"]
        assert len(end_hooks) == 1
        assert "ended-msg-ok=true" in end_hooks[0]["stdout"]

    def test_step_fail_hook_fires_on_failure(self):
        """step_fail hook should only fire when step fails."""
        step = {"id": "bad", "command": "nonexistent_vnc_cmd", "args": [], "on_error": "continue"}
        wf_hooks = {"step_fail": "echo failed-$STEP_ID"}
        ok, record = execute_step(
            step, {}, {}, workflow_hooks=wf_hooks, workflow_name="test"
        )
        assert ok is False
        fail_hooks = [h for h in record["hooks"] if h["event"] == "step_fail"]
        assert len(fail_hooks) == 1
        assert "failed-bad" in fail_hooks[0]["stdout"]

    def test_step_fail_hook_does_not_fire_on_success(self):
        """step_fail hook should NOT fire when step succeeds."""
        step = {"id": "good", "command": "echo", "args": ["fine"]}
        wf_hooks = {"step_fail": "echo should-not-see-this"}
        ok, record = execute_step(
            step, {}, {}, workflow_hooks=wf_hooks, workflow_name="test"
        )
        assert ok is True
        hooks = record.get("hooks", [])
        fail_hooks = [h for h in hooks if h["event"] == "step_fail"]
        assert len(fail_hooks) == 0

    def test_no_hooks_key_when_no_hooks_configured(self):
        """Step record should not have 'hooks' key when no hooks are configured."""
        step = {"id": "plain", "command": "echo", "args": ["bare"]}
        ok, record = execute_step(step, {}, {})
        assert ok is True
        assert "hooks" not in record

    def test_per_step_hook_override(self):
        """Per-step hook override should replace workflow-level hook."""
        step = {
            "id": "custom",
            "command": "echo",
            "args": ["test"],
            "hooks": {"step_start": "echo custom-start"},
        }
        wf_hooks = {"step_start": "echo global-start"}
        ok, record = execute_step(
            step, {}, {}, workflow_hooks=wf_hooks, workflow_name="test"
        )
        assert ok is True
        start_hooks = [h for h in record["hooks"] if h["event"] == "step_start"]
        assert "custom-start" in start_hooks[0]["stdout"]

    def test_empty_step_hook_disables_global(self):
        """Empty string per-step hook should disable the global hook."""
        step = {
            "id": "quiet",
            "command": "echo",
            "args": ["shh"],
            "hooks": {"step_start": ""},
        }
        wf_hooks = {"step_start": "echo global-should-not-fire"}
        ok, record = execute_step(
            step, {}, {}, workflow_hooks=wf_hooks, workflow_name="test"
        )
        assert ok is True
        # No hooks should have fired (step_start disabled, no step_end configured)
        assert "hooks" not in record


# ── run_workflow() hook integration ──────────────────────────────────────

class TestRunWorkflowHooks:
    """Tests for hooks in the full workflow runner."""

    def test_workflow_complete_hook_fires(self):
        """workflow_complete hook should fire after all steps finish."""
        wf = {
            "name": "hooked-wf",
            "steps": [
                {"id": "s1", "command": "echo", "args": ["done"]}
            ],
            "hooks": {
                "workflow_complete": "echo wf-done-$WORKFLOW_NAME-ok=$WORKFLOW_OK",
            },
        }
        result = run_workflow(wf)
        assert result["ok"] is True
        assert "workflow_complete_hook" in result
        hr = result["workflow_complete_hook"]
        assert hr["ok"] is True
        assert "wf-done-hooked-wf-ok=true" in hr["stdout"]

    def test_workflow_complete_receives_summary_json(self):
        """workflow_complete hook should have WORKFLOW_SUMMARY_JSON in env."""
        wf = {
            "name": "json-wf",
            "steps": [
                {"id": "s1", "command": "echo", "args": ["x"]}
            ],
            "hooks": {
                "workflow_complete": "echo $WORKFLOW_SUMMARY_JSON",
            },
        }
        result = run_workflow(wf)
        assert result["ok"] is True
        hr = result["workflow_complete_hook"]
        # The stdout should contain parseable JSON
        assert hr["ok"] is True
        parsed = json.loads(hr["stdout"])
        assert parsed["workflow"] == "json-wf"
        assert parsed["ok"] is True

    def test_all_hooks_fire_in_order(self):
        """step_start, step_end, and workflow_complete should all fire."""
        wf = {
            "name": "full-hooks",
            "steps": [
                {"id": "s1", "command": "echo", "args": ["a"]},
                {"id": "s2", "command": "echo", "args": ["b"]},
            ],
            "hooks": {
                "step_start": "echo start-$STEP_ID",
                "step_end": "echo end-$STEP_ID",
                "workflow_complete": "echo all-done",
            },
        }
        result = run_workflow(wf)
        assert result["ok"] is True
        # Each step should have 2 hook records (start + end)
        for step_rec in result["steps"]:
            hooks = step_rec.get("hooks", [])
            events = [h["event"] for h in hooks]
            assert "step_start" in events
            assert "step_end" in events
        # workflow_complete should be present
        assert result["workflow_complete_hook"]["ok"] is True

    def test_no_workflow_hooks_key_when_none_configured(self):
        """No workflow_complete_hook key when hooks not configured."""
        wf = {
            "name": "no-hooks",
            "steps": [{"id": "s1", "command": "echo", "args": ["plain"]}],
        }
        result = run_workflow(wf)
        assert result["ok"] is True
        assert "workflow_complete_hook" not in result

    def test_step_hooks_with_conditional_skip(self):
        """Hooks should NOT fire for conditionally-skipped steps."""
        wf = {
            "name": "cond-hooks",
            "steps": [
                {"id": "s1", "command": "echo", "args": ["yes"]},
                {"id": "s2", "command": "echo", "args": ["no"], "when": "false"},
            ],
            "hooks": {
                "step_start": "echo start-$STEP_ID",
            },
        }
        result = run_workflow(wf)
        assert result["ok"] is True
        # s1 should have hooks, s2 should be skipped with no hooks
        s1 = result["steps"][0]
        s2 = result["steps"][1]
        assert "hooks" in s1
        assert s2.get("skipped") is True
        assert "hooks" not in s2
