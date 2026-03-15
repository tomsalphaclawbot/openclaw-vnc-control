#!/usr/bin/env python3
"""
VNC Click Lab input + key regression.

Validates:
1) `agent_input` receives typed text and logs `field_input`
2) `agent_text_field` receives multi-line text with Enter line breaks
3) special keys + modifier combos generate `field_keydown` events

Assumes the lab page is open and visible in the active browser on the VNC target.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple


def run_vnc(vnc_bin: str, cwd: Path, *args: str) -> Dict[str, object]:
    proc = subprocess.run([vnc_bin, *args], cwd=str(cwd), capture_output=True, text=True)
    out = (proc.stdout or proc.stderr or "").strip()
    payload: Dict[str, object]
    try:
        payload = json.loads(out) if out else {}
    except json.JSONDecodeError:
        payload = {"raw": out}
    payload["rc"] = proc.returncode
    return payload


def click_capture(vnc_bin: str, cwd: Path, x: int, y: int) -> Dict[str, object]:
    return run_vnc(vnc_bin, cwd, "click", str(x), str(y), "--space", "capture")


def key_send(vnc_bin: str, cwd: Path, key: str) -> Dict[str, object]:
    return run_vnc(vnc_bin, cwd, "key", key)


def read_events_since(log_path: Path, offset: int) -> Tuple[List[Dict[str, object]], int]:
    if not log_path.exists():
        return [], offset

    raw = log_path.read_bytes()
    if offset >= len(raw):
        return [], offset

    chunk = raw[offset:].decode("utf-8", errors="ignore")
    events: List[Dict[str, object]] = []
    for line in chunk.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    return events, len(raw)


def keydown_summary(events: List[Dict[str, object]], field: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for ev in events:
        if ev.get("event") != "field_keydown":
            continue
        if ev.get("fieldName") != field:
            continue
        k = str(ev.get("key") or "")
        if not k:
            continue
        out[k] = out.get(k, 0) + 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Run VNC lab input + key regression")
    ap.add_argument("--log-path", required=True)
    ap.add_argument("--vnc-binary", default="./vnc")
    ap.add_argument("--vnc-cwd", default=".")
    ap.add_argument("--sleep", type=float, default=0.12)

    # capture-space coordinates calibrated for current lab viewport
    ap.add_argument("--focus-input-x", type=int, default=250)
    ap.add_argument("--focus-input-y", type=int, default=304)
    ap.add_argument("--focus-text-x", type=int, default=355)
    ap.add_argument("--focus-text-y", type=int, default=304)
    ap.add_argument("--blur-x", type=int, default=700)
    ap.add_argument("--blur-y", type=int, default=650)

    args = ap.parse_args()

    log_path = Path(args.log_path)
    vnc_cwd = Path(args.vnc_cwd).resolve()

    offset = len(log_path.read_bytes()) if log_path.exists() else 0

    # --- Test 1: input field text ---
    input_token = "inputcheck"
    click_capture(args.vnc_binary, vnc_cwd, args.focus_input_x, args.focus_input_y)
    time.sleep(args.sleep)
    for ch in input_token:
        key_send(args.vnc_binary, vnc_cwd, ch)
    click_capture(args.vnc_binary, vnc_cwd, args.blur_x, args.blur_y)
    time.sleep(args.sleep)

    # --- Test 2: textarea multiline ---
    lines = ["lineone", "linetwo", "linethree"]
    click_capture(args.vnc_binary, vnc_cwd, args.focus_text_x, args.focus_text_y)
    time.sleep(args.sleep)
    for i, line in enumerate(lines):
        for ch in line:
            key_send(args.vnc_binary, vnc_cwd, ch)
        if i < len(lines) - 1:
            key_send(args.vnc_binary, vnc_cwd, "enter")
    click_capture(args.vnc_binary, vnc_cwd, args.blur_x, args.blur_y)
    time.sleep(args.sleep)

    # --- Test 3: key matrix on textarea ---
    key_matrix = [
        "return",
        "tab",
        "escape",
        "backspace",
        "delete",
        "left",
        "right",
        "up",
        "down",
        "shift-a",
        "cmd-a",
        "option-left",
        "control-a",
        "alt-a",
        "super-a",
    ]

    key_send_results: List[Dict[str, object]] = []
    for key in key_matrix:
        # Re-focus textarea before each key so keys like Tab don't move focus away
        click_capture(args.vnc_binary, vnc_cwd, args.focus_text_x, args.focus_text_y)
        time.sleep(args.sleep)
        r = key_send(args.vnc_binary, vnc_cwd, key)
        key_send_results.append({"requested": key, **r})
        time.sleep(args.sleep)
    click_capture(args.vnc_binary, vnc_cwd, args.blur_x, args.blur_y)
    time.sleep(args.sleep)

    events, _ = read_events_since(log_path, offset)

    # Evaluate field_input checks
    input_values = [
        str(ev.get("fieldValue") or "")
        for ev in events
        if ev.get("event") == "field_input" and ev.get("fieldName") == "agent_input"
    ]
    text_values = [
        str(ev.get("fieldValue") or "")
        for ev in events
        if ev.get("event") == "field_input" and ev.get("fieldName") == "agent_text_field"
    ]

    input_ok = any(input_token in v for v in input_values)
    multiline_expected = "\n".join(lines)
    text_ok = any(multiline_expected in v for v in text_values)

    # Evaluate keydown coverage on textarea
    kd = keydown_summary(events, "agent_text_field")
    required_keys = [
        "Enter",
        "Tab",
        "Escape",
        "Backspace",
        "Delete",
        "ArrowLeft",
        "ArrowRight",
        "ArrowUp",
        "ArrowDown",
        "Shift",
        "Meta",
        "Control",
    ]
    key_checks = {k: (kd.get(k, 0) > 0) for k in required_keys}
    keys_ok = all(key_checks.values())

    failed_key_sends = [r for r in key_send_results if int(r.get("rc", 1)) != 0]

    summary = {
        "input_ok": input_ok,
        "text_multiline_ok": text_ok,
        "keys_ok": keys_ok,
        "key_checks": key_checks,
        "keydown_counts_agent_text_field": kd,
        "input_values_tail": input_values[-3:],
        "text_values_tail": text_values[-3:],
        "failed_key_sends": failed_key_sends,
        "events_seen": len(events),
    }

    print(json.dumps(summary, indent=2))

    if input_ok and text_ok and keys_ok and not failed_key_sends:
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
