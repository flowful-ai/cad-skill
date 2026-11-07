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
        "threemfs", "threemf", "steps", "step", "watertight",
        "bboxes", "fits_bed", "stdout", "stderr", "returncode",
    }
    assert expected.issubset(data.keys())


def test_step_discovered(step_script):
    rc, data = run(step_script)
    assert rc == 0
    assert data["success"] is True
    assert len(data["steps"]) == 1
    assert data["step"].endswith("step_model.step")
    # STL is still discovered alongside the STEP.
    assert data["stl"].endswith("step_model.stl")


def test_preview_renders_png(good_script):
    rc, data = run(good_script, "--preview")
    assert rc == 0
    assert len(data["previews"]) == 1
    assert os.path.exists(data["previews"][0])
    assert data["preview"].endswith("_preview.png")


def test_bed_fits(good_script):
    rc, data = run(good_script, "--bed", "a1")
    assert rc == 0
    assert data["fits_bed"] is True
    assert data["bboxes"] == [[10.0, 10.0, 10.0]]


def test_bed_too_small_fails(good_script):
    rc, data = run(good_script, "--bed", "15x15x15")
    assert rc == 1
    assert data["success"] is False
    assert data["fits_bed"] is False
    assert "Does not fit the bed" in data["stderr"]
    # The misfit is still measured.
    assert data["bboxes"] == [[10.0, 10.0, 10.0]]


def test_bed_without_stl_fails(empty_script):
    rc, data = run(empty_script, "--bed", "a1")
    assert rc == 1
    assert "No STL files produced" in data["stderr"]


def test_bed_unknown_printer_is_usage_error(good_script):
    result = subprocess.run(
        [sys.executable, WRAPPER, str(good_script), "--bed", "nope"],
        capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert "a1mini" in result.stderr


def test_bed_empty_string_is_usage_error(good_script):
    result = subprocess.run(
        [sys.executable, WRAPPER, str(good_script), "--bed", ""],
        capture_output=True, text=True,
    )
    assert result.returncode == 2


def test_strict_and_bed_report_both_problems(tmp_path):
    """A non-watertight part that is also too big gets both errors in one run."""
    script = tmp_path / "open_big.py"
    script.write_text(
        "import trimesh\n"
        "m = trimesh.creation.box((300, 10, 10))\n"
        "m.update_faces([i for i in range(len(m.faces)) if i != 0])\n"
        "m.export('open_big.stl')\n"
    )
    rc, data = run(script, "--strict", "--bed", "a1")
    assert rc == 1
    assert data["watertight"] is False
    assert data["fits_bed"] is False
    assert "not watertight" in data["stderr"]
    assert "Does not fit the bed" in data["stderr"]
