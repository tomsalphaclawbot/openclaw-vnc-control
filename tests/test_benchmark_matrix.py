from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_bench_module():
    repo_root = Path(__file__).resolve().parent.parent
    mod_path = repo_root / "bench" / "run_benchmark_matrix.py"
    spec = importlib.util.spec_from_file_location("bench_matrix", mod_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_cases_respects_limits_and_templates():
    mod = load_bench_module()
    fixture = {
        "elements": [
            {"id": "btn_save", "kind": "button", "label": "Save", "center_px": {"x": 100, "y": 200}},
            {"id": "input_email", "kind": "input", "label": "Email", "center_px": {"x": 200, "y": 250}},
            {"id": "nav_home", "kind": "nav-link", "label": "Home", "center_px": {"x": 50, "y": 20}},
        ],
        "negative_queries": [
            {"id": "neg1", "query": 'button labeled "Ghost"', "expected_found": False},
            {"id": "neg2", "query": 'input field named "Phantom"', "expected_found": False},
        ],
    }

    cases = mod.build_cases(fixture, max_positive=2, max_negative=1)

    assert len(cases) == 3
    assert cases[0].expected_found is True
    assert "button labeled" in cases[0].query
    assert cases[1].expected_found is True
    assert any(tok in cases[1].query for tok in ["button labeled", "input field labeled"])
    assert cases[2].expected_found is False
    assert cases[2].case_id == "neg1"


def test_summarize_backend_metrics():
    mod = load_bench_module()
    probe = mod.Probe(
        backend="moondream",
        runnable=True,
        reason_class="ok",
        reason="available",
        dry_run_command="cmd",
        next_steps=[],
    )

    rows = [
        {"classification": "tp", "error_px": 12.0, "elapsed_s": 1.0},
        {"classification": "tp", "error_px": 24.0, "elapsed_s": 2.0},
        {"classification": "fn", "elapsed_s": 1.5},
        {"classification": "tn", "elapsed_s": 0.7},
        {"classification": "fp", "elapsed_s": 0.9},
    ]

    summary = mod.summarize_backend(rows, probe)

    assert summary["runnable"] is True
    assert summary["attempted"] == 5
    assert summary["tp"] == 2
    assert summary["fn"] == 1
    assert summary["tn"] == 1
    assert summary["fp"] == 1
    assert summary["positive_recall"] == 0.6667
    assert summary["negative_specificity"] == 0.5
    assert summary["median_error_px"] == 18.0
    assert summary["median_latency_s"] == 1.0


def test_summarize_backend_not_runnable():
    mod = load_bench_module()
    probe = mod.Probe(
        backend="anthropic",
        runnable=False,
        reason_class="missing_api_key",
        reason="ANTHROPIC_API_KEY missing",
        dry_run_command="cmd",
        next_steps=["export ANTHROPIC_API_KEY=..."],
    )

    summary = mod.summarize_backend([], probe)

    assert summary["runnable"] is False
    assert summary["attempted"] == 0
    assert summary["reason_class"] == "missing_api_key"
