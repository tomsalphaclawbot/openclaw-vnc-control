#!/usr/bin/env python3
"""
vnc-workflow.py — Phase 17: Workflow Event Hooks for openclaw-vnc-control

Execute multi-step VNC automation workflows defined in YAML or JSON.
Each step calls a vnc-control.py command; results are tracked and summarized.

Phase 17 adds: lifecycle event hooks — shell commands that fire before/after
each step and at workflow completion, enabling external observability and
integration without embedding logic inside the workflow itself.

Phase 16 adds: `when` conditional expressions — steps can be skipped based on
previous step output or variable values, enabling branching automation logic.

Usage:
    python3 vnc-workflow.py run <workflow.yaml>
    python3 vnc-workflow.py run <workflow.json>
    python3 vnc-workflow.py validate <workflow.yaml>    # dry-run validation only
    python3 vnc-workflow.py list                        # list built-in examples

Workflow format (YAML):
    name: my-workflow
    description: Optional description
    variables:
      username: "alpha"
    steps:
      - id: screenshot
        command: screenshot
        args: ["--format", "jpeg", "--out", "/tmp/step1.jpg"]
        on_error: stop     # stop (default) | continue | retry
        retry_max: 2
        retry_delay: 1.0
      - id: find-button
        command: find_element
        args: ["Login button"]
        save_output: button_coords
      - id: click-button
        command: click
        args: ["{{button_coords.native_x}}", "{{button_coords.native_y}}", "--space", "native"]
        when: "{{find-button.ok}} == true"   # only run if find-button succeeded
      - id: pause
        command: sleep
        args: ["0.5"]
        when: "{{retries}} > 0"              # only run if variable retries > 0

Conditional expressions (`when`):
    Simple comparisons against interpolated left-hand side:
      "{{step_id.field}} == value"           — equals (string or bool)
      "{{step_id.field}} != value"           — not equals
      "{{step_id.field}} > value"            — numeric greater-than
      "{{step_id.field}} >= value"           — numeric greater-than-or-equal
      "{{step_id.field}} < value"            — numeric less-than
      "{{step_id.field}} <= value"           — numeric less-than-or-equal
      "{{step_id.ok}} == true"               — boolean check
      "{{step_id.ok}} != false"              — boolean check

    Boolean shortcuts:
      when: "true"                           — always execute (default)
      when: "false"                          — always skip

    When a step is skipped due to `when`, it appears in results with skipped=true.

Variable interpolation:
    {{var_name}}               — top-level variable
    {{step_id.field}}          — field from a previous step's output
    {{step_id.data.field}}     — nested field from a step's "data" object

Built-in commands (no subprocess):
    sleep SECONDS  — pause execution
    echo MESSAGE   — log a message in the step output

Event hooks (Phase 17):
    Hooks fire shell commands at lifecycle points. Configure at workflow level
    under a `hooks` key, or per-step under a step's `hooks` key (step overrides
    workflow-level hooks for that step only).

    Workflow-level hooks:
      hooks:
        step_start: "echo 'Starting {{STEP_ID}}'"
        step_end: "echo 'Step {{STEP_ID}} ok={{STEP_OK}} took {{STEP_DURATION_MS}}ms'"
        step_fail: "screenshot --out /tmp/fail-{{STEP_ID}}.jpg"
        workflow_complete: "curl -s -X POST https://notify.example.com/done -d '{{WORKFLOW_SUMMARY_JSON}}'"

    Per-step hook override:
      steps:
        - id: risky-step
          command: click
          args: [100, 200]
          hooks:
            step_fail: "echo 'risky-step failed, screenshot saved'"
            step_start: ""   # empty string disables the global hook for this step

    Environment variables injected into all hook commands:
      STEP_ID           — step id string
      STEP_OK           — "true" or "false"
      STEP_DURATION_MS  — integer milliseconds
      STEP_COMMAND      — vnc-control command name
      STEP_ATTEMPTS     — number of attempts made
      WORKFLOW_NAME     — workflow name
      WORKFLOW_SUMMARY_JSON — (workflow_complete only) full result JSON string

    Hook commands support {{VAR}} interpolation (same as step args).
    Hook failures do NOT abort the workflow by default.
    Set `hook_on_error: stop` to change this behavior.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Optional YAML support ──────────────────────────────────────────────────
try:
    import yaml as _yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

# ── Locate vnc-control.py sibling ─────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).parent.resolve()
_VNC_CTRL = _SCRIPT_DIR / "vnc-control.py"

# ── Error types ───────────────────────────────────────────────────────────
class WorkflowError(Exception):
    pass

class StepError(Exception):
    pass

# ── Loader ────────────────────────────────────────────────────────────────
def load_workflow(path: str) -> Dict[str, Any]:
    """Load a workflow from YAML or JSON file."""
    p = Path(path)
    if not p.exists():
        raise WorkflowError(f"Workflow file not found: {path}")
    content = p.read_text()
    suffix = p.suffix.lower()
    if suffix in (".yaml", ".yml"):
        if not _HAS_YAML:
            raise WorkflowError("PyYAML not installed. Install with: pip install pyyaml")
        return _yaml.safe_load(content)
    elif suffix == ".json":
        return json.loads(content)
    else:
        # Try JSON first, then YAML
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            if _HAS_YAML:
                return _yaml.safe_load(content)
            raise WorkflowError(f"Unknown format and PyYAML not installed: {path}")


def load_workflow_str(text: str, fmt: str = "json") -> Dict[str, Any]:
    """Load workflow from a string (for testing)."""
    if fmt in ("yaml", "yml"):
        if not _HAS_YAML:
            raise WorkflowError("PyYAML not installed")
        return _yaml.safe_load(text)
    return json.loads(text)


# ── Validation ────────────────────────────────────────────────────────────
VALID_ON_ERROR = {"stop", "continue", "retry"}
VALID_COMMANDS = {
    "screenshot", "click", "move", "type", "key", "combo", "dialog", "map",
    "connect", "status", "find_element", "wait_for", "assert_visible",
    "scroll", "drag", "diff", "crop", "annotate", "macro", "clipboard",
    "read_text", "sessions",
    # built-ins
    "sleep", "echo",
}


def validate_workflow(wf: Dict[str, Any]) -> List[str]:
    """Return list of validation errors. Empty list = valid."""
    errors = []
    if not isinstance(wf, dict):
        return ["Workflow must be a mapping/dict"]
    if "name" not in wf:
        errors.append("Missing required field: name")
    if "steps" not in wf:
        errors.append("Missing required field: steps")
        return errors  # Can't validate steps without them
    if not isinstance(wf["steps"], list):
        errors.append("'steps' must be a list")
        return errors
    if len(wf["steps"]) == 0:
        errors.append("'steps' must not be empty")

    seen_ids = set()
    for i, step in enumerate(wf.get("steps", [])):
        prefix = f"steps[{i}]"
        if not isinstance(step, dict):
            errors.append(f"{prefix}: step must be a mapping")
            continue
        if "command" not in step:
            errors.append(f"{prefix}: missing required field 'command'")
        else:
            cmd = step["command"]
            if cmd not in VALID_COMMANDS:
                errors.append(f"{prefix}: unknown command '{cmd}'")
        if "id" in step:
            sid = step["id"]
            if sid in seen_ids:
                errors.append(f"{prefix}: duplicate step id '{sid}'")
            seen_ids.add(sid)
        on_error = step.get("on_error", "stop")
        if on_error not in VALID_ON_ERROR:
            errors.append(f"{prefix}: on_error must be one of {VALID_ON_ERROR}, got '{on_error}'")
        if "args" in step and not isinstance(step["args"], list):
            errors.append(f"{prefix}: 'args' must be a list")
        retry_max = step.get("retry_max", 0)
        if not isinstance(retry_max, int) or retry_max < 0:
            errors.append(f"{prefix}: 'retry_max' must be a non-negative integer")

    return errors


# ── Variable Interpolation ────────────────────────────────────────────────
def _deep_get(obj: Any, keys: List[str]) -> Any:
    """Navigate nested dict/list with a list of keys."""
    for k in keys:
        if isinstance(obj, dict):
            if k not in obj:
                raise KeyError(k)
            obj = obj[k]
        elif isinstance(obj, (list, tuple)):
            try:
                obj = obj[int(k)]
            except (ValueError, IndexError):
                raise KeyError(k)
        else:
            raise KeyError(k)
    return obj


def evaluate_when(
    when_expr: str,
    variables: Dict[str, Any],
    step_outputs: Dict[str, Any],
) -> bool:
    """
    Evaluate a `when` conditional expression.

    Supported forms:
      "true" | "false"                        — literal bool
      "<lhs> <op> <rhs>"                      — comparison
        ops: == != > >= < <=
        lhs may contain {{...}} interpolation
        rhs is a bare literal (string, number, true/false)

    Returns True (run step) or False (skip step).
    Raises WorkflowError on evaluation failure.
    """
    expr = when_expr.strip()

    # Literal shortcuts
    if expr.lower() == "true":
        return True
    if expr.lower() == "false":
        return False

    # Parse: "<lhs> <op> <rhs>"
    # Operators sorted longest-first to avoid partial matches (e.g. >= before >)
    _OPS = ["!=", "==", ">=", "<=", ">", "<"]
    op_found: Optional[str] = None
    lhs_raw: str = ""
    rhs_raw: str = ""

    for op in _OPS:
        idx = expr.find(op)
        if idx != -1:
            lhs_raw = expr[:idx].strip()
            rhs_raw = expr[idx + len(op):].strip()
            op_found = op
            break

    if op_found is None:
        # No operator — treat as truthy string (non-empty interpolated value)
        try:
            resolved = interpolate(expr, variables, step_outputs)
        except WorkflowError:
            raise WorkflowError(f"when: could not interpolate expression: {expr!r}")
        lv = str(resolved).lower()
        return lv not in ("", "false", "0", "none", "null")

    # Interpolate LHS and RHS (RHS may also contain {{...}} placeholders)
    try:
        lhs_resolved = interpolate(lhs_raw, variables, step_outputs)
    except WorkflowError as e:
        raise WorkflowError(f"when: {e}")

    try:
        rhs_resolved = interpolate(rhs_raw, variables, step_outputs)
    except WorkflowError:
        # RHS is a bare literal — use as-is
        rhs_resolved = rhs_raw

    lhs = str(lhs_resolved)
    rhs = str(rhs_resolved).strip('"\'')  # strip optional quotes from literal

    # Bool coercion helpers
    def _to_bool(v: str) -> bool:
        return v.lower() not in ("false", "0", "none", "null", "")

    def _to_num(v: str) -> float:
        try:
            return float(v)
        except ValueError:
            raise WorkflowError(f"when: cannot compare non-numeric values with {op_found!r}: {v!r}")

    try:
        if op_found == "==":
            # bool-aware: "true"/"false" literals
            if rhs.lower() in ("true", "false"):
                return _to_bool(lhs) == (rhs.lower() == "true")
            return lhs == rhs
        elif op_found == "!=":
            if rhs.lower() in ("true", "false"):
                return _to_bool(lhs) != (rhs.lower() == "true")
            return lhs != rhs
        elif op_found == ">":
            return _to_num(lhs) > _to_num(rhs)
        elif op_found == ">=":
            return _to_num(lhs) >= _to_num(rhs)
        elif op_found == "<":
            return _to_num(lhs) < _to_num(rhs)
        elif op_found == "<=":
            return _to_num(lhs) <= _to_num(rhs)
    except WorkflowError:
        raise
    except Exception as e:
        raise WorkflowError(f"when: evaluation error: {e}")

    return True  # unreachable


def interpolate(value: Any, variables: Dict[str, Any], step_outputs: Dict[str, Any]) -> Any:
    """Recursively interpolate {{...}} placeholders in strings, lists, and dicts."""
    if isinstance(value, str):
        def _replace(m: re.Match) -> str:
            expr = m.group(1).strip()
            parts = expr.split(".")
            # First try top-level variables
            if parts[0] in variables:
                try:
                    result = _deep_get(variables[parts[0]], parts[1:]) if len(parts) > 1 else variables[parts[0]]
                    return str(result)
                except KeyError:
                    pass
            # Then try step outputs
            if parts[0] in step_outputs:
                try:
                    result = _deep_get(step_outputs[parts[0]], parts[1:])
                    return str(result)
                except KeyError:
                    pass
            raise WorkflowError(f"Variable not found: {{{{{expr}}}}}")
        return re.sub(r"\{\{(.+?)\}\}", _replace, value)
    elif isinstance(value, list):
        return [interpolate(v, variables, step_outputs) for v in value]
    elif isinstance(value, dict):
        return {k: interpolate(v, variables, step_outputs) for k, v in value.items()}
    return value


# ── Hook Execution ────────────────────────────────────────────────────────

def fire_hook(
    hook_cmd: str,
    hook_env: Dict[str, str],
    variables: Dict[str, Any],
    step_outputs: Dict[str, Any],
    hook_on_error: str = "ignore",
) -> Dict[str, Any]:
    """
    Fire a lifecycle hook shell command.
    Returns dict with ok, returncode, stdout, stderr.
    Non-zero exit is suppressed unless hook_on_error == 'stop'.
    """
    if not hook_cmd or not hook_cmd.strip():
        return {"ok": True, "skipped": True}

    # Interpolate {{VAR}} in hook command string
    try:
        resolved_cmd = interpolate(hook_cmd, {**variables, **hook_env}, step_outputs)
    except WorkflowError:
        resolved_cmd = hook_cmd

    env = os.environ.copy()
    env.update(hook_env)

    try:
        proc = subprocess.run(
            resolved_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        result = {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        result = {"ok": False, "error": "hook timed out after 30s"}
    except Exception as e:
        result = {"ok": False, "error": str(e)}

    return result


def _resolve_step_hooks(step: Dict[str, Any], workflow_hooks: Dict[str, str]) -> Dict[str, str]:
    """Merge workflow-level hooks with per-step hook overrides."""
    merged = dict(workflow_hooks)
    step_hooks = step.get("hooks", {})
    if isinstance(step_hooks, dict):
        merged.update(step_hooks)
    return merged


# ── Step Execution ────────────────────────────────────────────────────────
def run_step_builtin(step: Dict[str, Any], args: List[str]) -> Dict[str, Any]:
    """Execute a built-in command (sleep, echo) — no subprocess."""
    cmd = step["command"]
    if cmd == "sleep":
        secs = float(args[0]) if args else 1.0
        time.sleep(secs)
        return {"ok": True, "data": {"slept_seconds": secs}}
    elif cmd == "echo":
        msg = " ".join(args)
        return {"ok": True, "data": {"message": msg}}
    raise StepError(f"Unknown built-in: {cmd}")


def run_step_subprocess(
    step: Dict[str, Any],
    args: List[str],
    extra_env: Optional[Dict[str, str]] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    """Execute a vnc-control.py command and return parsed JSON result."""
    cmd = [sys.executable, str(_VNC_CTRL), step["command"]] + args
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        stdout = proc.stdout.strip()
        if stdout:
            try:
                result = json.loads(stdout)
                return result
            except json.JSONDecodeError:
                return {"ok": proc.returncode == 0, "raw": stdout, "returncode": proc.returncode}
        else:
            stderr = proc.stderr.strip()
            return {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stderr": stderr,
            }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Step timed out after {timeout}s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def execute_step(
    step: Dict[str, Any],
    variables: Dict[str, Any],
    step_outputs: Dict[str, Any],
    extra_env: Optional[Dict[str, str]] = None,
    workflow_hooks: Optional[Dict[str, str]] = None,
    hook_on_error: str = "ignore",
    workflow_name: str = "unnamed",
) -> Tuple[bool, Dict[str, Any]]:
    """
    Execute one workflow step with retry logic.
    Returns (step_ok, step_record).
    """
    step_id = step.get("id", step.get("command", "unknown"))
    command = step["command"]
    raw_args = step.get("args", [])
    on_error = step.get("on_error", "stop")
    retry_max = int(step.get("retry_max", 0))
    retry_delay = float(step.get("retry_delay", 1.0))
    step_timeout = int(step.get("timeout", 60))
    save_output = step.get("save_output")
    when_expr = step.get("when")

    # Resolve hooks for this step (workflow-level + step-level overrides)
    effective_hooks = _resolve_step_hooks(step, workflow_hooks or {})

    # Evaluate `when` conditional — skip step if expression is False
    if when_expr is not None:
        try:
            should_run = evaluate_when(str(when_expr), variables, step_outputs)
        except WorkflowError as e:
            record = {
                "id": step_id,
                "command": command,
                "ok": False,
                "on_error": on_error,
                "error": f"when evaluation failed: {e}",
                "attempts": 0,
                "duration_ms": 0,
            }
            return False, record
        if not should_run:
            record = {
                "id": step_id,
                "command": command,
                "ok": True,   # skipped steps don't count as failures
                "skipped": True,
                "when": when_expr,
                "reason": "when condition was false",
                "attempts": 0,
                "duration_ms": 0,
            }
            # Still register step_id in outputs so downstream {{step_id.skipped}} works
            step_outputs[step_id] = {"skipped": True, "ok": True}
            return True, record

    # Interpolate args
    try:
        resolved_args = interpolate(raw_args, variables, step_outputs)
    except WorkflowError as e:
        record = {
            "id": step_id,
            "command": command,
            "ok": False,
            "on_error": on_error,
            "error": str(e),
            "attempts": 0,
            "duration_ms": 0,
        }
        return False, record

    builtin = command in ("sleep", "echo")
    attempts = 0
    last_result = None
    hook_records: List[Dict[str, Any]] = []
    t_start = time.monotonic()

    # ── Fire step_start hook ──
    step_start_hook = effective_hooks.get("step_start", "")
    if step_start_hook:
        hook_env = {
            "STEP_ID": step_id,
            "STEP_COMMAND": command,
            "STEP_OK": "unknown",
            "STEP_DURATION_MS": "0",
            "STEP_ATTEMPTS": "0",
            "WORKFLOW_NAME": workflow_name,
        }
        hr = fire_hook(step_start_hook, hook_env, variables, step_outputs, hook_on_error)
        hook_records.append({"event": "step_start", **hr})

    for attempt in range(retry_max + 1):
        attempts = attempt + 1
        try:
            if builtin:
                last_result = run_step_builtin(step, resolved_args)
            else:
                last_result = run_step_subprocess(step, resolved_args, extra_env, step_timeout)
        except Exception as e:
            last_result = {"ok": False, "error": str(e)}

        if last_result.get("ok"):
            break
        if attempt < retry_max:
            time.sleep(retry_delay)

    duration_ms = round((time.monotonic() - t_start) * 1000)
    step_ok = bool(last_result.get("ok"))

    # ── Fire step_end hook ──
    step_end_hook = effective_hooks.get("step_end", "")
    if step_end_hook:
        hook_env = {
            "STEP_ID": step_id,
            "STEP_COMMAND": command,
            "STEP_OK": str(step_ok).lower(),
            "STEP_DURATION_MS": str(duration_ms),
            "STEP_ATTEMPTS": str(attempts),
            "WORKFLOW_NAME": workflow_name,
        }
        hr = fire_hook(step_end_hook, hook_env, variables, step_outputs, hook_on_error)
        hook_records.append({"event": "step_end", **hr})

    # ── Fire step_fail hook (only on failure) ──
    if not step_ok:
        step_fail_hook = effective_hooks.get("step_fail", "")
        if step_fail_hook:
            hook_env = {
                "STEP_ID": step_id,
                "STEP_COMMAND": command,
                "STEP_OK": "false",
                "STEP_DURATION_MS": str(duration_ms),
                "STEP_ATTEMPTS": str(attempts),
                "WORKFLOW_NAME": workflow_name,
            }
            hr = fire_hook(step_fail_hook, hook_env, variables, step_outputs, hook_on_error)
            hook_records.append({"event": "step_fail", **hr})

    # Build the step output record: always includes 'ok', plus any data fields
    data = last_result.get("data", {})
    if isinstance(data, dict):
        step_output_record: Dict[str, Any] = {"ok": step_ok, **data}
    else:
        step_output_record = {"ok": step_ok, "value": data}
    # Also surface top-level fields from last_result (e.g. native_x, native_y)
    for k, v in last_result.items():
        if k not in ("ok", "data") and k not in step_output_record:
            step_output_record[k] = v

    # Save output to variables if requested
    if save_output and step_ok:
        step_outputs[save_output] = step_output_record
    # Always save under step ID
    step_outputs[step_id] = step_output_record

    record = {
        "id": step_id,
        "command": command,
        "args": resolved_args,
        "ok": step_ok,
        "on_error": on_error,
        "attempts": attempts,
        "duration_ms": duration_ms,
        "result": last_result,
    }
    if save_output:
        record["saved_as"] = save_output
    if hook_records:
        record["hooks"] = hook_records

    return step_ok, record


# ── Workflow Runner ────────────────────────────────────────────────────────
def run_workflow(
    wf: Dict[str, Any],
    extra_vars: Optional[Dict[str, str]] = None,
    extra_env: Optional[Dict[str, str]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Execute a workflow dict. Returns summary JSON.
    """
    wf_name = wf.get("name", "unnamed")
    wf_desc = wf.get("description", "")
    steps = wf.get("steps", [])
    workflow_hooks = wf.get("hooks", {})
    hook_on_error = wf.get("hook_on_error", "ignore")

    # Merge variables: workflow defaults < extra_vars
    variables: Dict[str, Any] = {}
    variables.update(wf.get("variables", {}))
    if extra_vars:
        variables.update(extra_vars)

    # Validate
    errors = validate_workflow(wf)
    if errors:
        return {
            "ok": False,
            "workflow": wf_name,
            "error": "Validation failed",
            "validation_errors": errors,
        }

    if dry_run:
        return {
            "ok": True,
            "workflow": wf_name,
            "dry_run": True,
            "steps_total": len(steps),
            "validation_errors": [],
            "steps": [
                {
                    "id": s.get("id", s.get("command", f"step_{i}")),
                    "command": s.get("command"),
                    "args": s.get("args", []),
                    **({"when": s["when"]} if "when" in s else {}),
                }
                for i, s in enumerate(steps)
            ],
        }

    step_records: List[Dict[str, Any]] = []
    step_outputs: Dict[str, Any] = {}
    passed = failed = skipped = cond_skipped = 0
    workflow_ok = True
    t_start = time.monotonic()

    for step in steps:
        step_ok, record = execute_step(
            step, variables, step_outputs, extra_env,
            workflow_hooks=workflow_hooks,
            hook_on_error=hook_on_error,
            workflow_name=wf_name,
        )
        step_records.append(record)

        if record.get("skipped") and record.get("when") is not None:
            # Conditional skip — not a failure, not a pass
            cond_skipped += 1
        elif step_ok:
            passed += 1
        else:
            failed += 1
            on_error = step.get("on_error", "stop")
            if on_error == "stop":
                workflow_ok = False
                # Mark remaining steps as skipped (error-abort)
                for remaining in steps[len(step_records):]:
                    skipped += 1
                    step_records.append({
                        "id": remaining.get("id", remaining.get("command", "?")),
                        "command": remaining.get("command"),
                        "ok": None,
                        "skipped": True,
                        "reason": f"skipped after step '{record['id']}' failed",
                    })
                break
            # on_error == "continue" or "retry" (retry already handled in execute_step)

    total_duration_ms = round((time.monotonic() - t_start) * 1000)
    final_ok = workflow_ok and failed == 0

    result = {
        "ok": final_ok,
        "workflow": wf_name,
        "description": wf_desc,
        "steps_total": len(steps),
        "steps_passed": passed,
        "steps_failed": failed,
        "steps_skipped": skipped,
        "steps_conditional_skipped": cond_skipped,
        "duration_ms": total_duration_ms,
        "steps": step_records,
    }

    # ── Fire workflow_complete hook ──
    wf_complete_hook = workflow_hooks.get("workflow_complete", "")
    if wf_complete_hook:
        try:
            summary_json = json.dumps(result)
        except (TypeError, ValueError):
            summary_json = "{}"
        hook_env = {
            "WORKFLOW_NAME": wf_name,
            "WORKFLOW_OK": str(final_ok).lower(),
            "WORKFLOW_DURATION_MS": str(total_duration_ms),
            "STEPS_PASSED": str(passed),
            "STEPS_FAILED": str(failed),
            "STEP_ID": "",
            "STEP_COMMAND": "",
            "STEP_OK": str(final_ok).lower(),
            "STEP_DURATION_MS": str(total_duration_ms),
            "STEP_ATTEMPTS": "0",
            "WORKFLOW_SUMMARY_JSON": summary_json,
        }
        hr = fire_hook(wf_complete_hook, hook_env, variables, step_outputs, hook_on_error)
        result["workflow_complete_hook"] = hr

    return result


# ── CLI ───────────────────────────────────────────────────────────────────
EXAMPLE_WORKFLOW_JSON = """{
  "name": "screenshot-check",
  "description": "Take a screenshot and verify the screen is accessible",
  "steps": [
    {
      "id": "pause",
      "command": "sleep",
      "args": ["0.1"]
    },
    {
      "id": "status-check",
      "command": "echo",
      "args": ["Workflow runner is operational"]
    }
  ]
}"""


def cmd_run(path: str, var_overrides: List[str], dry_run: bool = False) -> None:
    """Run a workflow file."""
    try:
        wf = load_workflow(path)
    except WorkflowError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)

    # Parse --var KEY=VALUE overrides
    extra_vars: Dict[str, str] = {}
    for v in var_overrides:
        if "=" in v:
            k, val = v.split("=", 1)
            extra_vars[k.strip()] = val.strip()

    result = run_workflow(wf, extra_vars=extra_vars, dry_run=dry_run)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("ok") else 1)


def cmd_validate(path: str) -> None:
    """Validate a workflow file without executing it."""
    try:
        wf = load_workflow(path)
    except WorkflowError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)
    errors = validate_workflow(wf)
    if errors:
        print(json.dumps({"ok": False, "workflow": wf.get("name", "?"), "errors": errors}))
        sys.exit(1)
    print(json.dumps({
        "ok": True,
        "workflow": wf.get("name", "?"),
        "steps": len(wf.get("steps", [])),
        "message": "Workflow is valid",
    }))


def cmd_list() -> None:
    """List example/built-in workflow templates."""
    # Check for workflows/ directory
    wf_dir = _SCRIPT_DIR / "workflows"
    examples = []
    if wf_dir.exists():
        for f in sorted(wf_dir.glob("*.yaml")) + sorted(wf_dir.glob("*.json")):
            examples.append(str(f.relative_to(_SCRIPT_DIR)))
    print(json.dumps({
        "ok": True,
        "workflows_dir": str(wf_dir),
        "found": examples,
        "builtin_example": "screenshot-check (run with --example)",
    }))


def main():
    import argparse
    parser = argparse.ArgumentParser(
        prog="vnc-workflow",
        description="VNC automation workflow runner for openclaw-vnc-control",
    )
    sub = parser.add_subparsers(dest="action", metavar="ACTION")

    # run
    p_run = sub.add_parser("run", help="Execute a workflow file")
    p_run.add_argument("file", nargs="?", default=None,
                       help="Path to workflow YAML or JSON file (omit with --example)")
    p_run.add_argument("--var", dest="vars", action="append", default=[],
                       metavar="KEY=VALUE", help="Override workflow variable (repeatable)")
    p_run.add_argument("--dry-run", action="store_true",
                       help="Validate and show plan without executing")
    p_run.add_argument("--example", action="store_true",
                       help="Run the built-in example workflow (omit file arg)")

    # validate
    p_val = sub.add_parser("validate", help="Validate a workflow file without executing")
    p_val.add_argument("file", help="Path to workflow YAML or JSON file")

    # list
    sub.add_parser("list", help="List available workflow files")

    args = parser.parse_args()
    if not args.action:
        parser.print_help()
        sys.exit(0)

    if args.action == "run":
        if getattr(args, "example", False):
            import tempfile
            tf = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
            tf.write(EXAMPLE_WORKFLOW_JSON)
            tf.close()
            cmd_run(tf.name, args.vars, dry_run=args.dry_run)
            os.unlink(tf.name)
        elif args.file:
            cmd_run(args.file, args.vars, dry_run=args.dry_run)
        else:
            print(json.dumps({"ok": False, "error": "Provide a workflow file or use --example"}))
            sys.exit(1)
    elif args.action == "validate":
        cmd_validate(args.file)
    elif args.action == "list":
        cmd_list()


if __name__ == "__main__":
    main()
