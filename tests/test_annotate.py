"""Phase 11: annotate command unit tests."""
import json
import os
import subprocess
import sys

import pytest

_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "vnc-control.py")


class TestPhase11Annotate:
    """Tests for the annotate command — draw shapes on screenshots."""

    @staticmethod
    def _make_image(path, size=(200, 200), color=(100, 120, 140)):
        from PIL import Image
        img = Image.new("RGB", size, color)
        img.save(str(path))
        return str(path)

    def test_annotate_single_rect(self, tmp_path):
        """Draw one rectangle and verify JSON output."""
        src = self._make_image(tmp_path / "src.png")
        out = str(tmp_path / "annotated.jpg")
        result = subprocess.run(
            [sys.executable, _SCRIPT, "annotate", src,
             "--shape", "rect:10,10,100,80,red,Button",
             "--out", out],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["action"] == "annotate"
        assert data["shapes_drawn"] == 1
        assert data["shapes"][0]["type"] == "rect"
        assert data["shapes"][0]["label"] == "Button"
        assert os.path.exists(out)

    def test_annotate_multiple_shapes(self, tmp_path):
        """Draw rect + circle + arrow + text simultaneously."""
        src = self._make_image(tmp_path / "src.png")
        out = str(tmp_path / "multi.jpg")
        result = subprocess.run(
            [sys.executable, _SCRIPT, "annotate", src,
             "--shape", "rect:10,10,80,60,blue,Box",
             "--shape", "circle:150,150,30,green,Dot",
             "--shape", "arrow:50,50,150,150,yellow,Flow",
             "--shape", "text:5,180,Hello_World,cyan",
             "--out", out],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["shapes_drawn"] == 4
        types = [s["type"] for s in data["shapes"]]
        assert "rect" in types
        assert "circle" in types
        assert "arrow" in types
        assert "text" in types
        assert os.path.exists(out)

    def test_annotate_default_color(self, tmp_path):
        """Omitting color should default to red."""
        src = self._make_image(tmp_path / "src.png")
        out = str(tmp_path / "default_color.jpg")
        result = subprocess.run(
            [sys.executable, _SCRIPT, "annotate", src,
             "--shape", "rect:10,10,50,50",
             "--out", out],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        # Default red is #ff3232 (255, 50, 50)
        assert data["shapes"][0]["color"] == "#ff3232"

    def test_annotate_hex_color(self, tmp_path):
        """Hex color codes should work."""
        src = self._make_image(tmp_path / "src.png")
        out = str(tmp_path / "hex.jpg")
        result = subprocess.run(
            [sys.executable, _SCRIPT, "annotate", src,
             "--shape", "circle:100,100,25,#00FF00,Green",
             "--out", out],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["shapes"][0]["color"] == "#00ff00"

    def test_annotate_missing_source(self, tmp_path):
        """Missing source image should fail gracefully."""
        result = subprocess.run(
            [sys.executable, _SCRIPT, "annotate", str(tmp_path / "nonexistent.png"),
             "--shape", "rect:10,10,50,50"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0
        data = json.loads(result.stdout)
        assert data["ok"] is False

    def test_annotate_no_shapes(self, tmp_path):
        """No shapes drawn — should still produce output (passthrough)."""
        src = self._make_image(tmp_path / "src.png")
        out = str(tmp_path / "no_shapes.jpg")
        result = subprocess.run(
            [sys.executable, _SCRIPT, "annotate", src, "--out", out],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["shapes_drawn"] == 0
        assert os.path.exists(out)

    def test_annotate_line_width(self, tmp_path):
        """Custom line width should be accepted."""
        src = self._make_image(tmp_path / "src.png")
        out = str(tmp_path / "thick.jpg")
        result = subprocess.run(
            [sys.executable, _SCRIPT, "annotate", src,
             "--shape", "rect:10,10,100,100,red",
             "--line-width", "5",
             "--out", out],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert os.path.exists(out)

    def test_annotate_png_output(self, tmp_path):
        """Output as PNG instead of default JPEG."""
        src = self._make_image(tmp_path / "src.png")
        out = str(tmp_path / "result.png")
        result = subprocess.run(
            [sys.executable, _SCRIPT, "annotate", src,
             "--shape", "circle:50,50,20,purple",
             "--format", "png", "--out", out],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert os.path.exists(out)

    def test_annotate_malformed_shape_skipped(self, tmp_path):
        """Malformed shape spec produces error entry but doesn't crash."""
        src = self._make_image(tmp_path / "src.png")
        out = str(tmp_path / "malformed.jpg")
        result = subprocess.run(
            [sys.executable, _SCRIPT, "annotate", src,
             "--shape", "rect:10,10",  # missing x2,y2
             "--shape", "circle:100,100,25,green,OK",
             "--out", out],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["shapes_drawn"] == 2
        # First shape should have an error entry
        assert "error" in data["shapes"][0]
        # Second shape should be fine
        assert data["shapes"][1]["type"] == "circle"

    def test_annotate_arrow_geometry(self, tmp_path):
        """Arrow should have from/to coords in output."""
        src = self._make_image(tmp_path / "src.png")
        out = str(tmp_path / "arrow.jpg")
        result = subprocess.run(
            [sys.executable, _SCRIPT, "annotate", src,
             "--shape", "arrow:20,20,180,180,orange,Click_here",
             "--out", out],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        arrow = data["shapes"][0]
        assert arrow["from"] == [20, 20]
        assert arrow["to"] == [180, 180]
        assert arrow["label"] == "Click_here"

    def test_annotate_parser_registered(self):
        """annotate subcommand help should be accessible."""
        result = subprocess.run(
            [sys.executable, _SCRIPT, "annotate", "--help"],
            capture_output=True, text=True, timeout=5,
        )
        assert result.returncode == 0
        assert "annotate" in result.stdout.lower()
        assert "shape" in result.stdout.lower()
        assert "source" in result.stdout.lower()
