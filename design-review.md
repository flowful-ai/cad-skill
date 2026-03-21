# Design Review & Iteration Guide

## Table of Contents
1. Preview-Analyze-Iterate Workflow
2. Visual Inspection Checklist
3. Dimensional Verification
4. Printability Analysis
5. Common Issues and Fixes

---

## 1. Preview-Analyze-Iterate Workflow

After generating a model, ALWAYS run the preview-analyze-iterate loop before delivering the final STL.

### Step 1: Generate Preview

```bash
# Install dependencies (first time only)
pip install trimesh pyrender Pillow

# Generate multi-view preview
python3 preview.py model.stl preview.png --views multi
```

### Step 2: View the Preview

Read the generated PNG file to inspect it visually. The multi-view layout shows the model from 4 angles (isometric, front, top, right) with dimensions in the footer.

### Step 3: Analyze the Preview

Check against this visual inspection list:

**Shape & Proportions**
- Does the overall shape match what was requested?
- Are proportions reasonable (not too thin, not too bulky)?
- Are all requested features visible (holes, slots, cutouts)?

**Printability**
- Is there a flat bottom surface for bed adhesion?
- Are there visible overhangs > 45 degrees that need supports?
- Do thin features look thick enough to print (> 1.2mm)?
- Are screw bosses and standoffs properly connected to walls?

**Geometry Issues**
- Are there any obviously missing features?
- Do boolean operations look clean (no floating geometry)?
- Are fillets and chamfers applied to the right edges?
- Does the interior look correctly hollowed out?

**Dimensions**
- Check bounding box in the preview footer
- Compare against user's stated requirements
- Verify critical dimensions from the code match visual

### Step 4: Fix Issues

If problems are found:
1. Identify the specific issue from the preview
2. Trace it to the relevant code section
3. Fix the code
4. Re-export STL
5. Re-generate preview
6. Verify the fix

### Step 5: Deliver

Once the preview passes inspection:
1. Export final STL (and optionally STEP)
2. Generate final preview image
3. Share both the STL and preview with the user
4. Note any print recommendations (orientation, supports, infill)

---

## 2. Visual Inspection Checklist

Use this as a structured review after viewing the preview:

```
VISUAL REVIEW
=============
[ ] Overall shape matches request
[ ] All features present (holes, cutouts, mounts, etc.)
[ ] Proportions look correct
[ ] No floating or disconnected geometry
[ ] Flat bottom for printing
[ ] No extreme overhangs visible
[ ] Fillets/chamfers applied correctly
[ ] Wall thickness appears sufficient
[ ] Interior properly hollowed (if applicable)
[ ] Dimensions match requirements (check footer)
```

---

## 3. Dimensional Verification

Beyond visual inspection, verify dimensions programmatically:

```python
import cadquery as cq

# After building the model:
bb = result.val().BoundingBox()
print(f"Width  (X): {bb.xlen:.1f} mm")
print(f"Depth  (Y): {bb.ylen:.1f} mm") 
print(f"Height (Z): {bb.zlen:.1f} mm")
print(f"Volume: {result.val().Volume():.0f} mm³")

# Check specific dimensions
assert abs(bb.xlen - expected_width) < 0.1, f"Width mismatch: {bb.xlen} vs {expected_width}"
```

### Key Checks
- Bounding box matches expected outer dimensions
- Volume is reasonable (not suspiciously small or large)
- Volume > 0 confirms the model is a valid solid
- Compare volume with/without shell to verify wall thickness

### Watertight Check

Non-watertight meshes are the most common cause of slicing failures. Always verify:

```python
import trimesh

tm = trimesh.load("model.stl", force="mesh")
if tm.is_watertight:
    print("Mesh is watertight (good)")
else:
    print("WARNING: Mesh is NOT watertight — will cause slicing issues")
    # Common causes: unclosed shells, boolean artifacts, zero-thickness faces
```

Note: `preview.py` checks watertight status automatically when generating previews.

---

## 4. Printability Analysis

### Overhang Detection (Approximate)

```python
import trimesh
import numpy as np

def check_overhangs(stl_path, max_angle=45):
    """Check for faces with overhang angle beyond threshold.

    Overhang angle is measured from the horizontal plane.
    A flat bottom (normal pointing straight down) = 0 deg overhang (safe).
    A face angled 50 deg from horizontal = needs supports if max_angle=45.

    Returns percentage of total faces that may need supports.
    """
    tm = trimesh.load(stl_path, force="mesh")
    normals = tm.face_normals

    # Only check downward-facing normals (potential overhangs)
    downward = normals[:, 2] < 0
    if not downward.any():
        return 0.0

    down = np.array([0, 0, -1])
    down_normals = normals[downward]

    # Angle between each normal and straight-down vector
    cos_angles = np.dot(down_normals, down) / (
        np.linalg.norm(down_normals, axis=1) + 1e-10
    )
    angles_from_down = np.degrees(np.arccos(np.clip(cos_angles, -1, 1)))

    # angle_from_down=0 means flat bottom (safe)
    # angle_from_down=90 means vertical face (safe)
    # Overhang angle from horizontal = 90 - angle_from_down
    overhang_from_horizontal = 90 - angles_from_down
    problem_faces = np.sum(overhang_from_horizontal > max_angle)

    return problem_faces / len(normals) * 100

pct = check_overhangs("model.stl")
if pct > 5:
    print(f"WARNING: {pct:.0f}% faces may need supports")
else:
    print(f"OK: Model looks printable without supports ({pct:.1f}% overhang)")
```

### Thin Wall Detection

```python
def estimate_min_wall(result):
    """Rough check - compare shelled vs non-shelled volume."""
    vol = result.val().Volume()
    bb = result.val().BoundingBox()
    outer_vol = bb.xlen * bb.ylen * bb.zlen
    fill_ratio = vol / outer_vol
    
    if fill_ratio < 0.15:
        print("⚠ Very thin walls - may be fragile")
    elif fill_ratio < 0.3:
        print("✓ Thin-walled design (typical for enclosures)")
    else:
        print("✓ Solid/thick-walled design")
    
    return fill_ratio
```

---

## 5. Common Issues and Fixes

### Issue: Feature not visible in preview
**Cause**: Boolean operation failed silently
**Fix**: Check that cutting bodies actually overlap the main body. Print intermediate volumes.

### Issue: Model looks correct but walls are paper-thin
**Cause**: Shell thickness too small, or shell removed wrong faces
**Fix**: Verify shell direction (negative = inward) and thickness >= 1.2mm

### Issue: Standoffs appear disconnected
**Cause**: Union failed because standoffs don't touch the body
**Fix**: Ensure standoff base cylinder intersects with the floor/wall of the body

### Issue: Cutout in wrong position
**Cause**: Coordinate system confusion - CadQuery centers at origin by default
**Fix**: Use `centered=(True, True, False)` and verify offsets from known reference points

### Issue: Fillets look wrong or preview crashes
**Cause**: Fillet radius too large for the edge
**Fix**: Reduce fillet radius. Rule of thumb: fillet radius < half the smallest adjacent face dimension

### Issue: Preview shows correct shape but dimensions are wrong
**Cause**: Forgot to update a parameter or used wrong variable
**Fix**: Add assertions comparing bounding box to expected dimensions
