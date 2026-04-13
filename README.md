# CAD Skill for Claude Code

A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skill for generating parametric 3D-printable models using [CadQuery](https://cadquery.readthedocs.io/). Describe a physical object, and Claude will write a parametric script, export STL, render previews, and iterate with you until it's right.

<p align="center">
  <img src="docs/magsafe_stand_preview.png" alt="MagSafe stand preview — 4 views" width="480">
  <img src="docs/iphone13_pro_case_preview.png" alt="iPhone 13 Pro case preview — 4 views" width="480">
</p>

Read the full write-up: [I Taught Claude to Design 3D-Printable Parts. Here's How](https://medium.com/@nchourrout/i-taught-claude-to-design-3d-printable-parts-heres-how-675f644af78a)

## More examples

Published on [MakerWorld](https://makerworld.com/en/@sercanto).

<p align="center">
  <img src="docs/gridfinity_d110_bin_preview.png" alt="Gridfinity 3x2 bin for Orico D110 label printer" width="640">
</p>

<p align="center">
  <img src="docs/magnet_catch_preview.png" alt="Magnetic door catch (frame side)" width="640">
  <img src="docs/magnet_strike_preview.png" alt="Magnetic door catch (door side)" width="640">
</p>

## Installation

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/flowful-ai/cad-skill ~/.claude/skills/parametric-3d-printing
```

## Dependencies

Requires **Python 3.10-3.12** (CadQuery's OCC kernel does not have wheels for 3.13+):

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | Skill definition and workflow instructions for Claude |
| `preview.py` | Headless STL to 6-view PNG renderer (trimesh + pyrender). Use `--strict` to fail on non-watertight meshes. |
| `run_cadquery_model.py` | Subprocess wrapper that runs a CadQuery script, captures errors, optionally renders the preview, and emits a JSON result so Claude can self-correct in a loop. |
| `mesh_io.py` | STL loading with validation (no pyrender dependency). Used by the wrapper and converter. |
| `stl_to_3mf.py` | Standalone STL to 3MF converter for Bambu Studio / PrusaSlicer. |
| `design-review.md` | Visual inspection checklist and printability analysis |
| `requirements.txt` | Pinned dependency versions |

---

Created by [Nicolas Chourrout](https://github.com/nchourrout) from [Flowful.ai](https://flowful.ai)
