---
name: parametric-3d-printing
description: "Use this skill whenever the user wants to create, modify, or iterate on 3D printable models. Triggers include: any mention of '3D print', 'STL', 'parametric model', 'enclosure', 'bracket', 'mount', 'case', 'housing', 'CadQuery', 'OpenSCAD', 'CAD', or requests to design physical objects. Also use when the user mentions their 3D printer (e.g. Bambu Lab, Prusa, Ender), asks about print-friendly design, snap-fits, tolerances, or wants to create functional parts like Arduino enclosures, cable organizers, wall mounts, adapters, or mechanical components. Use this skill even if the user just describes a physical object they want to make without explicitly mentioning 3D printing. Do NOT use for 3D rendering, game assets, or non-manufacturing 3D work."
---

# Parametric 3D Printing with CadQuery

## Overview

This skill generates parametric 3D models using **CadQuery** (Python) and exports them as STL files ready for slicing. CadQuery is preferred because it installs via pip, has a Pythonic API, and handles complex geometry (fillets, chamfers, booleans, assemblies) better than alternatives.

## Setup

```bash
# CadQuery requires Python 3.10-3.12 (OCC kernel lacks 3.13+ wheels)
python3.12 -m venv .venv && source .venv/bin/activate

# Install CadQuery and preview dependencies
pip install cadquery trimesh pyrender Pillow
```

CadQuery uses the OpenCASCADE kernel under the hood. trimesh, pyrender, and Pillow are used for the preview-analyze-iterate loop. No display server is needed — everything renders headlessly via pyrender's offscreen backend.

**If CadQuery fails to install** (OCC kernel build errors), try:
```bash
# Option 1: Use conda (CadQuery's officially recommended method)
conda install -c cadquery -c conda-forge cadquery

# Option 2: Use the pre-built wheels
pip install cadquery --find-links https://github.com/CadQuery/CadQuery/releases
```

## Real-World Dimension Research

When designing objects that interface with real products (phones, chargers, PCBs, connectors, etc.), **use web search to find accurate dimensions** before writing any geometry code. Don't guess or use approximate values — even 1-2mm off can make a part unusable.

**What to research:**
- Connector/port dimensions (USB-C: 8.4 x 2.6mm opening, Lightning, barrel jacks)
- Device dimensions (phone width/thickness, PCB footprints, charger puck diameters)
- Mounting hole patterns and screw sizes (M2.5, M3, etc.)
- Standard component specs (MagSafe puck: 56mm diameter, 5.6mm thick)
- Cable bend radii and strain relief requirements

**How to use it:**
1. Search for "[product] dimensions mm" or "[component] datasheet"
2. Cross-reference at least 2 sources when precision matters
3. Add the sourced dimensions as comments in the PARAMETERS section:
   ```python
   # MagSafe puck dimensions (source: Apple spec + iFixit teardown)
   puck_diameter = 56.0    # mm
   puck_thickness = 5.6    # mm
   ```
4. When in doubt, add 0.3-0.5mm clearance to external dimensions

This is especially important for: phone cases/stands, charger mounts, PCB enclosures, cable management, adapter fittings, and anything that clips onto or wraps around an existing product.

## Core Workflow

1. **Gather requirements** (see Requirements Gathering below)
2. **Research dimensions** of any real-world products involved (see above)
3. **Phase 1 — Base shape**: Build outer shell, preview, get user feedback
4. **Phase 2 — Features**: Add functional details, preview, get user feedback
5. **Phase 3 — Final delivery**: Fillets, cleanup, final preview + STL + print recommendations
6. **Offer parameter tweaks** after delivery

This is a **collaborative, show-as-you-go** process. Do NOT disappear and come back with a finished model. Show the user your progress at each phase and incorporate their feedback before moving on.

## Requirements Gathering

Before writing any code, walk through these topics with the user **conversationally**. Don't dump all questions at once — ask the most important ones first, then follow up based on answers. Use reasonable defaults when the user doesn't specify.

**What is it?**
Object type, purpose, what it holds/protects/attaches to. Get a clear mental model of the object before anything else.

**Critical dimensions**
Must-fit measurements — PCB size, phone width, screw spacing, diameter of the thing it wraps around, etc. These are non-negotiable and drive everything else.

**Mounting & attachment**
How does it connect to things? Screws (what size?), snap-fit, adhesive tape, magnets, freestanding on a desk? This affects wall thickness, boss placement, and overall structure.

**Printer & material**
What printer do they have? (Bambu, Prusa, Ender, etc.) Nozzle size? Material — PLA, PETG, TPU? This directly affects tolerances, minimum feature sizes, and design constraints. Defaults: 0.4mm nozzle, PLA, 0.2mm layer height.

**Functional needs**
Ventilation/airflow, water resistance, cable routing, access panels, visibility windows, stacking, weight limits. Ask only what's relevant to the object.

**Aesthetic preferences**
Rounded vs sharp edges, minimal vs industrial look, color considerations (affects visibility of layer lines). Ask briefly — most users care more about function than form.

Start with the first two (what + dimensions), then ask about mounting and material if relevant. Only ask about aesthetics if the user seems to care or if it affects structural choices.

## Progressive Preview Workflow

Build the model in phases. At each phase, export an STL, render a preview, self-review it, then **show it to the user and ask for feedback** before proceeding. This catches problems early and keeps the user involved.

### Preview recipe (use at every phase)
```bash
python3 preview.py model.stl preview.png --views multi
```
Then view the preview image, self-review it against the checklist in `design-review.md`, and fix any issues you spot **before** showing it to the user.

---

### Phase 1 — Base Shape

Build the basic outer form: overall dimensions, shell/walls, bottom plate. No cutouts, no fillets, no details yet.

1. Write the script with parameters and basic geometry
2. Export STL and render preview
3. Self-review: Does the shape and size look right? Is the bottom flat for printing?
4. **Show the preview to the user**: "Here's the basic shape — does this look right before I add details?" Include key dimensions.
5. Wait for feedback. If the user wants changes, iterate here before moving on.

### Phase 2 — Features

Add functional details: holes, cutouts, mounting bosses, cable slots, ventilation, snap-fits, internal structures.

1. Add features to the script
2. Export STL and render preview
3. Self-review: Are all features visible? Do booleans look clean? Are holes in the right positions?
4. **Show the preview to the user**: "I've added [list features]. Anything to change before I finalize?"
5. Wait for feedback. Iterate if needed.

### Phase 3 — Final Delivery

Apply finishing touches: fillets, chamfers, edge cleanup. Do a full printability review.

1. Add fillets/chamfers (largest radius first, apply after shell)
2. Export final STL and render preview
3. **Full self-review** using the complete checklist from `design-review.md` — visual inspection, dimensional verification, printability analysis
4. Fix any issues found, re-export if needed
5. **Deliver to the user**: final STL + preview image + print recommendations (orientation, supports, infill, material notes)

---

**Important:** Do NOT skip phases or combine them unless the model is very simple (e.g., a flat bracket with two holes). For anything with enclosed geometry, multiple features, or tight tolerances, follow all three phases.

Read `design-review.md` for the full visual inspection checklist, dimensional verification code, and printability analysis helpers.

## Script Template

ALWAYS structure scripts like this:

```python
import cadquery as cq

# ============================================================
# PARAMETERS - Edit these to customize the model
# ============================================================
# Overall dimensions
width = 60.0        # mm - outer width
depth = 40.0        # mm - outer depth  
height = 25.0       # mm - outer height

# Wall and structural
wall = 2.0          # mm - wall thickness (min 1.2 for FDM)
corner_r = 2.0      # mm - corner fillet radius

# Tolerances
fit_clearance = 0.3 # mm - clearance for press-fit (adjust per printer)

# ============================================================
# MODEL
# ============================================================
result = (
    cq.Workplane("XY")
    .box(width, depth, height, centered=(True, True, False))
    # ... build geometry using parameters above (bottom at Z=0)
)

# ============================================================
# EXPORT
# ============================================================
cq.exporters.export(result, "output.stl")
print(f"Exported: {width}x{depth}x{height}mm")
```

## Key Rules

### Parameters First
- ALL dimensions go in the PARAMETERS section at the top
- Use descriptive names: `screw_hole_d`, not `d1`
- Add units in comments (always mm)
- Group related parameters with blank lines and section comments

### Print-Friendly Defaults
Key FDM design defaults:

| Property | Minimum | Recommended |
|----------|---------|-------------|
| Wall thickness | 1.2mm | 2.0mm |
| Layer height | 0.08mm | 0.2mm |
| Hole clearance | 0.2mm | 0.3mm |
| Press-fit interference | 0.1mm | 0.15mm |
| Min feature size | 0.4mm (nozzle) | 0.8mm |
| Fillet radius (bottom) | 0.5mm | 1.0mm |
| Bridge span | - | < 20mm unsupported |
| Overhang angle | - | < 45 degrees from vertical |

**Material-specific adjustments:** TPU needs larger clearances (~0.5mm) due to flex. PETG is stickier, so add +0.1mm to fit clearances. ABS shrinks ~0.5-0.7%, so scale critical dimensions up slightly. When in doubt, print a small test piece first.

### Orientation Awareness
- Design with print orientation in mind
- Flat bottom surfaces print best
- Avoid supports when possible by designing around overhangs
- Add chamfers to bottom edges instead of fillets (fillets need supports)
- Comment the intended print orientation in the script

### CadQuery Patterns

Common patterns to know:

**Hollow enclosure:**
```python
result = (
    cq.Workplane("XY")
    .box(width, depth, height, centered=(True, True, False))
    .edges("|Z").fillet(corner_r)
    .shell(-wall)  # negative = shell inward
)
```

**Screw boss:**
```python
.pushPoints([(x, y)])
.circle(boss_od / 2).extrude(boss_h)
.pushPoints([(x, y)])
.hole(screw_d + fit_clearance)
```

**Snap-fit clip:**
```python
# Cantilever beam with overhang hook
.workplane(offset=wall)
.moveTo(x, y).rect(clip_w, clip_l).extrude(clip_h)
# Add hook at tip with a small overhang (< 45 deg)
```

**Ventilation grid:**
```python
.pushPoints(vent_positions)
.slot2D(slot_l, slot_w).cutThruAll()
```

Other patterns: mounting brackets, cable routing channels, text/labels (`.text()`), multi-part assemblies with alignment pins.

### Common Pitfalls
- **Zero-thickness geometry**: Ensure boolean operations don't create infinitely thin walls
- **Fillet failures**: Apply fillets from largest to smallest radius. If a fillet fails, reduce its radius.
- **Fillet/shell/cut ordering**: The correct sequence is `.shell()` first (hollow out), then `.fillet()` (round edges), then boolean cuts (holes, slots, pockets). Shelling a filleted body often fails, and filleting edges left by cuts is fragile.
- **Coordinate system**: CadQuery centers geometry at origin by default. Use `centered=(True, True, False)` on `.box()` to place bottom at Z=0.
- **Hole direction**: `.hole()` cuts through the entire part by default. Use `.cboreHole()` or `.cskHole()` for counterbore/countersink.
- **Export errors**: If export fails, the geometry may be invalid. Check for self-intersecting shapes.
- **Taper direction**: In `.extrude(taper=angle)`, a **positive** taper angle narrows the shape (draft inward), **negative** flares it outward. This is opposite to what many people expect.
- **Shell on tapered/complex geometry**: `.shell()` frequently fails on tapered bodies, lofted shapes, or geometry with many fillets. The reliable alternative is **boolean subtraction** — create the outer solid, create a slightly smaller inner solid, then use `outer.cut(inner)` to hollow it out. This gives you full control over wall thickness at every point.
- **Loft is fragile**: CadQuery's `.loft()` fails on many cross-section combinations. Prefer `.extrude(taper=angle)` when transitioning between a shape and a scaled version of itself. Only use `.loft()` when you need to transition between genuinely different profiles (e.g., circle to rectangle).

## Export

```python
# STL (for slicing)
cq.exporters.export(result, "model.stl")

# STEP (for further CAD editing)
cq.exporters.export(result, "model.step")

# Both formats
for fmt in ["stl", "step"]:
    cq.exporters.export(result, f"model.{fmt}")
```

Always export STL for printing. Optionally export STEP if the user might want to edit in Fusion 360 or similar.

## Multi-Part Models

For models with multiple parts (e.g., enclosure + lid):

```python
# Export each part separately
cq.exporters.export(body, "enclosure_body.stl")
cq.exporters.export(lid, "enclosure_lid.stl")
```

Name files descriptively so the user knows which part is which.

## Parameter Adjustment Offer

After delivering the final model, **always present the key parameters as a summary table** and offer to tweak them. This lets the user fine-tune without re-explaining the whole design.

Example:
```
Here's your final model! Current parameters:

| Parameter       | Value  |
|----------------|--------|
| Width          | 90 mm  |
| Depth          | 65 mm  |
| Height         | 30 mm  |
| Wall thickness | 4 mm   |
| Cable slot     | 18 mm  |
| Corner radius  | 3 mm   |
| Fit clearance  | 0.3 mm |

Want me to adjust anything? Just say e.g. "make it 5mm taller" or "wider cable slot."
```

Only include parameters the user would plausibly want to change — skip internal constants like `eps` or `nozzle_d`. Group them logically (dimensions first, then structural, then tolerances).

## Output Checklist

Before delivering a model, verify:
- [ ] All dimensions are parameterized (no magic numbers in geometry code)
- [ ] Wall thickness >= 1.2mm
- [ ] Designed for printability (minimal overhangs/supports)
- [ ] Print orientation noted in comments
- [ ] STL exported and file size is reasonable (not 0 bytes)
- [ ] Clear parameter names with units
- [ ] Script runs without errors
- [ ] **Multi-view preview generated and visually inspected**
- [ ] **Preview shows correct shape, features, and proportions**
- [ ] **Bounding box dimensions match requirements**
- [ ] Both STL and preview PNG delivered to user
