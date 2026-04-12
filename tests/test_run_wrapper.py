import json
import os
import subprocess
import sys

import pytest

WRAPPER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "run_cadquery_model.py",
)


def run(script_path, *extra_args):
    result = subprocess.run(
        [sys.executable, WRAPPER, str(script_path), *extra_args],
        capture_output=True, text=True,
    )
    data = json.loads(result.stdout) if result.stdout.strip() else None
    return result.returncode, data


def test_happy_path(good_script):
    rc, data = run(good_script)
    assert rc == 0
    assert data["success"] is True
    assert len(data["stls"]) == 1
    assert data["stl"].endswith("good_model.stl")
    assert data["returncode"] == 0


def test_strict_watertight(good_script):
    rc, data = run(good_script, "--strict")
    assert rc == 0
    assert data["success"] is True
    assert data["watertight"] is True


def test_strict_empty_fails(empty_script):
    rc, data = run(empty_script, "--strict")
    assert rc == 1
    assert data["success"] is False
    assert "No STL files produced" in data["stderr"]


def test_bad_script_traceback(bad_script):
    rc, data = run(bad_script)
    assert rc == 1
    assert data["success"] is False
    assert "Traceback" in data["stderr"] or "Error" in data["stderr"]


def test_json_shape_keys(good_script):
    """All documented keys must be present in every response."""
    _, data = run(good_script)
    expected = {
        "success", "script", "stls", "stl", "previews", "preview",
        "threemfs", "threemf", "watertight", "stdout", "stderr", "returncode",
    }
    assert expected.issubset(data.keys())


def test_preview_renders_png(good_script):
    rc, data = run(good_script, "--preview")
    assert rc == 0
    assert len(data["previews"]) == 1
    assert os.path.exists(data["previews"][0])
    assert data["preview"].endswith("_preview.png")
