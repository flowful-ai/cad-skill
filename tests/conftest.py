import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)


@pytest.fixture
def tmp_stl(tmp_path):
    """Generate a watertight 10mm cube STL on demand."""
    stl = tmp_path / "cube.stl"
    script = tmp_path / "cube.py"
    script.write_text(
        "import cadquery as cq\n"
        "r = cq.Workplane('XY').box(10, 10, 10)\n"
        f"cq.exporters.export(r, {str(stl)!r},"
        " tolerance=0.01, angularTolerance=0.1)\n"
    )
    subprocess.run([sys.executable, str(script)], check=True, cwd=str(tmp_path))
    return stl


@pytest.fixture
def good_script(tmp_path):
    """CadQuery script that writes a watertight cube next to itself."""
    script = tmp_path / "good_model.py"
    script.write_text(
        "import cadquery as cq\n"
        "r = cq.Workplane('XY').box(10, 10, 10)\n"
        "cq.exporters.export(r, 'good_model.stl',"
        " tolerance=0.01, angularTolerance=0.1)\n"
    )
    return script


@pytest.fixture
def bad_script(tmp_path):
    """CadQuery script that raises (fillet radius too large)."""
    script = tmp_path / "bad.py"
    script.write_text(
        "import cadquery as cq\n"
        "cq.Workplane('XY').box(10, 10, 10).edges('|Z').fillet(99)\n"
    )
    return script


@pytest.fixture
def empty_script(tmp_path):
    """Script that exits 0 without writing any STL."""
    script = tmp_path / "empty.py"
    script.write_text('print("no export called")\n')
    return script
