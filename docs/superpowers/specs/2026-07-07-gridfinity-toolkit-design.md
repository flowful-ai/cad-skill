# Gridfinity Toolkit Design

Date: 2026-07-07
Status: approved

## Goal

Add a tested, reusable Gridfinity bin generator to the parametric-3d-printing skill. A session producing a Gridfinity bin should write ~30 lines of model-specific code instead of re-deriving ~200 lines of base-profile math (as happened in `gridfinity_d110_bin.py` and `gridfinity_d110_tape_bin.py`).

Scope this round: bins only. Baseplates, image-to-shape pipeline, printability analyzers, print-in-place and Multiboard references are out of scope.

## Packaging decision

Vendored module. `gridfinity.py` lives in the skill repo, is tested once, and gets copied next to each generated model script. Generated scripts import it. MakerWorld releases ship both files so published scripts stay runnable.

Rejected alternatives: reference-doc-only (re-pastes ~150 lines of boilerplate that can drift) and hybrid inline-on-release (adds an inlining step to build and keep correct).

## Module: `gridfinity.py`

Single file, depends only on `cadquery`. Builder-style API:

```python
from gridfinity import GridfinityBin

bin = GridfinityBin(grid_x=3, grid_y=2, height_units=3,
                    stacking_lip=True, magnets=True, screws=False)
bin.add_pocket(length=88.6, width=72.6,
               corner_r=(12.0, 1.0))   # (-X end, +X end) radii
bin.add_polygon_pocket(points, depth, clearance=0.0)
bin.add_compartments(cols=2, rows=1, scoop_r=8.0, label_tab=True)
bin.add_finger_notch(side="+X", width=30.0, depth=15.0)
result = bin.build()   # cq.Workplane, bottom at Z=0, ready to export
```

### Spec constants (single SPEC section at top of module)

Sources: gridfinity.xyz/specification, gridfinity-unofficial/specification, and the
proven printed bins in this repo (published on MakerWorld, verified fit).

- Grid pitch 42.0 mm; bin footprint 41.5 mm per cell (0.25 mm clearance per side).
- Height unit 7.0 mm; bin nominal height = height_units x 7.
- Base profile per cell, bottom up: 0.8 mm chamfer (45 deg), 1.8 mm vertical riser,
  2.15 mm chamfer (45 deg). Total 4.75 mm.
- Corner radii follow the profile insets: 3.75 mm at the body, 1.6 mm at the riser,
  0.8 mm at the bottom.
- Stacking lip: mirrored base profile on the top rim (matches the shipped bins).
- Magnet bores: 6.5 mm dia x 2.4 mm deep (for 6x2 mm magnets), blind holes from below.
- Screw holes: 3.0 mm dia x 6.0 mm deep (M3 thread-forming).
- Magnet/screw centers on a 26 x 26 mm square centered in each cell.

### Features

- `add_pocket`: rounded-rect cavity. `corner_r` accepts a scalar or a 4-tuple for
  per-corner radii (the D110 cradle case: 12 mm grip end, 1 mm label-exit end).
- `add_polygon_pocket`: arbitrary closed outline, optional outward clearance offset.
  This is the future entry point for the image-to-shape pipeline.
- `add_compartments`: N x M divided storage with optional scoop radius and label tab.
- `add_finger_notch`: rounded cutout on a chosen side wall for grabbing contents.

### Validation (fail loudly in `build()`)

- Pocket or compartment footprint exceeding the interior.
- Pocket depth leaving less than the minimum floor above the base profile.
- Divider or perimeter walls under 1.2 mm.
- Non-positive grid or height units.

## SKILL.md changes

- Add "Gridfinity" to the frontmatter trigger keywords.
- New "Gridfinity bins" section: when a request is Gridfinity-shaped, copy
  `gridfinity.py` next to the model script and use the builder; never hand-roll the
  base profile. Include one compact usage example and a cheat sheet (42 mm pitch,
  7 mm height units, footprint math).
- Release guidance: ship `my_bin.py` + `gridfinity.py` together.

## Reference example

`examples/gridfinity_d110_bin.py`: the D110 cradle bin rebuilt on the module.
The original hand-rolled `gridfinity_d110_bin.py` at the repo root is left untouched
(it is an untracked working file that documents the known-good dimensions).

## Testing: `tests/test_gridfinity.py`

- Config matrix (1x1 through 4x2; lip/magnets/screws on and off; pockets,
  compartments): each build exports watertight with the expected bounding box
  (grid x 42 - 0.5 mm, height = units x 7 + 4.75 if lip).
- D110 regression: rebuild via the module, assert footprint 125.5 x 83.5 mm,
  total height 25.75 mm (3U + lip; the printer protrudes above the rim),
  pocket 88.6 x 72.6 mm reaching the floor at Z=6.75 mm. Note: the header
  comments in the original script ("total height = 42mm") are stale; the
  shipped STL measures 125.5 x 83.5 x 25.45 and is the reference.
- Validation tests: oversized pocket, too-deep pocket, thin dividers all raise.

## Out of scope (future rounds)

Baseplates, image -> shape -> bin pipeline, automated overhang/thin-wall analysis,
print-in-place patterns, Multiboard/Honeycomb references, MakerWorld release
automation.
