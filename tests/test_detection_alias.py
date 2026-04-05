from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_vnc_module():
    repo_root = Path(__file__).resolve().parent.parent
    mod_path = repo_root / "vnc-control.py"
    spec = importlib.util.spec_from_file_location("vnc_control_alias_test", mod_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_detect_element_remote_alias_maps_to_anthropic(monkeypatch):
    vnc = load_vnc_module()

    called = {"anthropic": 0}

    def fake_anthropic(image_path, query, model_id=None):
        called["anthropic"] += 1
        return {
            "found": True,
            "query": query,
            "backend": "anthropic",
            "image_size": {"w": 100, "h": 100},
            "center": {"x": 50, "y": 50},
            "center_norm": {"x": 0.5, "y": 0.5},
            "box": {"x_min": 40, "y_min": 40, "x_max": 60, "y_max": 60},
            "box_norm": {"x_min": 0.4, "y_min": 0.4, "x_max": 0.6, "y_max": 0.6},
        }

    monkeypatch.setattr(vnc, "_detect_anthropic", fake_anthropic)
    # prevent accidental moondream path if alias breaks
    monkeypatch.setattr(vnc, "_detect_moondream", lambda *a, **k: (_ for _ in ()).throw(AssertionError("wrong backend")))

    # image existence check happens in callers, not detect_element; backend function is invoked directly here
    result = vnc.detect_element("/tmp/fake.jpg", "Allow button", backend="remote")

    assert called["anthropic"] == 1
    assert result["backend"] == "anthropic"
    assert result["found"] is True
