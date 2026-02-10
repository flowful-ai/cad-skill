# parametric-3d-printing

A Claude Code skill for generating parametric 3D-printable models using [CadQuery](https://cadquery.readthedocs.io/) (Python). Ask Claude to design physical objects and it will write parametric scripts, export STL files, and render multi-view previews for visual inspection before delivery.

## Installation

Copy or symlink this folder into one of Claude Code's skill discovery paths:

**Personal** (available in all projects):

```bash
mkdir -p ~/.claude/skills
ln -s "$(pwd)" ~/.claude/skills/parametric-3d-printing
```

**Project-specific** (one repo only):

```bash
mkdir -p <your-project>/.claude/skills
ln -s "$(pwd)" <your-project>/.claude/skills/parametric-3d-printing
```

## Dependencies

Requires **Python 3.10-3.12** (CadQuery's OCC kernel does not have wheels for 3.13+). If your system default is newer, specify the version explicitly:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install cadquery numpy-stl matplotlib
```

If CadQuery fails to install (OCC kernel build errors), try conda:

```bash
conda install -c cadquery -c conda-forge cadquery
```

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | Main skill definition — frontmatter triggers + instructions for Claude |
| `preview.py` | Renders multi-view PNG previews from STL files (isometric, front, top, right) |
| `design-review.md` | Visual inspection checklist, dimensional verification, and printability analysis |

## How it works

1. You ask Claude to design something physical (e.g. "make me a Raspberry Pi enclosure")
2. Claude matches your request against the skill's `description` field and loads SKILL.md
3. Claude gathers your requirements (dimensions, tolerances, what it attaches to)
4. Claude writes a parametric CadQuery script with all dimensions as editable variables
5. Claude exports STL, runs `preview.py` to render a 4-view technical sheet, and visually inspects it
6. If issues are found, Claude fixes and re-iterates
7. Claude delivers the final STL + preview PNG

## preview.py usage

```bash
# 4-view technical sheet (default)
python3 preview.py model.stl output.png --views multi

# Single isometric view
python3 preview.py model.stl output.png --views iso

# Custom title
python3 preview.py model.stl output.png --title "My Enclosure"
```

## Example prompts

- "Design a wall mount for a Raspberry Pi 4"
- "Make me a cable organizer for my desk, 6 slots"
- "I need an enclosure for an Arduino Nano with a USB cutout"
- "Create a parametric bracket that attaches to 2020 aluminum extrusion"

---

Created by [Nicolas Chourrout](https://flowful.ai) from [Flowful.ai](https://flowful.ai)
