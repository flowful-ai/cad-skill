import json
import os
import subprocess
import sys

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "callout.py",
)


def run(*args):
    result = subprocess.run(
        [sys.executable, SCRIPT, *[str(a) for a in args]],
        capture_output=True, text=True,
    )
    return result.returncode, result.stdout + result.stderr


def test_writes_pdf_and_png(tmp_stl, tmp_path):
    out = tmp_path / "cube.pdf"
    rc, log = run(tmp_stl, "--out", out, "--callout", "0,0:The whole cube")
    assert rc == 0, log
    assert out.exists() and out.stat().st_size > 1000
    png = tmp_path / "cube.png"
    assert png.exists() and png.stat().st_size > 1000


def test_numbers_are_printed_for_quoting(tmp_stl, tmp_path):
    """The agent has to be able to quote the numbers back in the same reply."""
    rc, log = run(tmp_stl, "--out", tmp_path / "a.pdf",
                  "--callout", "0,0:Top face", "--callout", "4,4:A corner")
    assert rc == 0, log
    assert "(1)  Top face" in log
    assert "(2)  A corner" in log


def test_callout_on_a_gap_is_only_warned_about(tmp_stl, tmp_path):
    """Pointing at an aperture is legitimate, so this must not be fatal."""
    rc, log = run(tmp_stl, "--out", tmp_path / "b.pdf", "--step", "0.4",
                  "--callout", "0,0:On the cube",
                  "--callout", "5.5,5.5:Just off the corner")
    assert rc == 0, log
    assert "WARNING" in log and "[2]" in log
    assert (tmp_path / "b.pdf").exists()


def test_callout_outside_the_drawing_is_an_error(tmp_stl, tmp_path):
    """Autoscaling to this used to shrink the part until the blank guard fired."""
    rc, log = run(tmp_stl, "--out", tmp_path / "b2.pdf",
                  "--callout", "0,0:On the cube",
                  "--callout", "80,80:Nowhere near it")
    assert rc != 0
    assert "outside the drawing" in log and "[2]" in log
    assert not (tmp_path / "b2.pdf").exists()


def test_no_callouts_is_an_error(tmp_stl, tmp_path):
    rc, log = run(tmp_stl, "--out", tmp_path / "c.pdf")
    assert rc != 0
    assert "no callouts" in log
    assert not (tmp_path / "c.pdf").exists()


def test_malformed_callout_is_an_error(tmp_stl, tmp_path):
    rc, log = run(tmp_stl, "--out", tmp_path / "d.pdf", "--callout", "oops")
    assert rc != 0
    assert "is not in the form" in log


def test_missing_stl_is_an_error(tmp_path):
    rc, log = run(tmp_path / "nope.stl", "--callout", "0,0:x")
    assert rc != 0
    assert "Failed to load STL" in log


def test_key_block_survives_many_long_labels(tmp_stl, tmp_path):
    """The key used to run off its axes past about eight entries."""
    args = []
    for i in range(20):
        args += ["--callout", f"0,0:Entry {i} with a label long enough to "
                              f"need wrapping, because real descriptions of "
                              f"a part run well past a hundred characters "
                              f"once they say where it is and why it matters"]
    rc, log = run(tmp_stl, "--out", tmp_path / "e.pdf", *args)
    assert rc == 0, log
    assert "(20)" in log
    assert (tmp_path / "e.pdf").exists()


def test_spec_file_round_trip(tmp_stl, tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({
        "title": "Cube from a spec",
        "view": "front",
        "callouts": [{"at": [0, 0], "label": "Front face"}],
        "overlays": [{"points": [[-5, -5], [5, -5]], "label": "bed line"}],
    }))
    rc, log = run(tmp_stl, "--spec", spec, "--out", tmp_path / "f.pdf")
    assert rc == 0, log
    assert "front view" in log
    assert "(1)  Front face" in log


def test_every_view_renders(tmp_stl, tmp_path):
    for view in ("top", "bottom", "front", "right"):
        rc, log = run(tmp_stl, "--out", tmp_path / f"{view}.pdf",
                      "--view", view, "--callout", "0,0:centre")
        assert rc == 0, log
        assert f"{view} view" in log
