#!/usr/bin/env python3
"""
vnc-workflow.py — Phase 15: Workflow Runner for openclaw-vnc-control

Execute multi-step VNC automation workflows defined in YAML or JSON.
Each step calls a vnc-control.py command; results are tracked and summarized.

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
      - id: pause
        command: sleep
        args: ["0.5"]

Variable interpolation:
    {{var_name}}               — top-level variable
    {{step_id.field}}          — field from a previous step's output
    {{step_id.data.field}}     — nested field from a step's "data" object

Built-in commands (no subprocess):
    sleep SECONDS  — pause execution
    echo MESSAGE   — log a message in the step output
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
    t_start = time.monotonic()

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

    # Save output to variables if requested
    if save_output and step_ok:
        data = last_result.get("data", last_result)
        step_outputs[save_output] = data
        # Also save by step ID for {{step_id.field}} access
    # Always save under step ID
    step_outputs[step_id] = last_result.get("data", last_result)

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
                {"id": s.get("id", s.get("command", f"step_{i}")), "command": s.get("command"), "args": s.get("args", [])}
                for i, s in enumerate(steps)
            ],
        }

    step_records: List[Dict[str, Any]] = []
    step_outputs: Dict[str, Any] = {}
    passed = failed = skipped = 0
    workflow_ok = True
    t_start = time.monotonic()

    for step in steps:
        step_ok, record = execute_step(step, variables, step_outputs, extra_env)
        step_records.append(record)

        if step_ok:
            passed += 1
        else:
            failed += 1
            on_error = step.get("on_error", "stop")
            if on_error == "stop":
                workflow_ok = False
                # Mark remaining steps as skipped
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

    return {
        "ok": final_ok,
        "workflow": wf_name,
        "description": wf_desc,
        "steps_total": len(steps),
        "steps_passed": passed,
        "steps_failed": failed,
        "steps_skipped": skipped,
        "duration_ms": total_duration_ms,
        "steps": step_records,
    }


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
