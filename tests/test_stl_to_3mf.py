import os
import subprocess
import sys

CONVERTER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "stl_to_3mf.py",
)


def test_convert_happy_path(tmp_stl):
    result = subprocess.run(
        [sys.executable, CONVERTER, str(tmp_stl)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert tmp_stl.with_suffix(".3mf").exists()


def test_convert_missing_file(tmp_path):
    result = subprocess.run(
        [sys.executable, CONVERTER, str(tmp_path / "nope.stl")],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "not found" in result.stderr
