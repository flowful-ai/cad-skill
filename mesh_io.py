"""Pure trimesh STL loading with validation guards.

Kept separate from preview.py so consumers that only need mesh loading
(stl_to_3mf.py, run_cadquery_model.py's --strict watertight check) don't
pay the pyrender + PyOpenGL import cost. Only depends on trimesh + numpy.
"""
import math

import numpy as np
import trimesh


def load_mesh(path):
    """Load an STL file via trimesh.

    Raises ValueError if the file cannot be parsed, contains no geometry,
    has zero faces, or has non-finite vertex coordinates. Callers handle
    the failure in-process instead of being killed by sys.exit, and silent
    garbage (zero-face or NaN meshes) is stopped before it reaches pyrender.
    """
    try:
        tm = trimesh.load(path, force="mesh")
    except Exception as e:
        raise ValueError(f"Failed to load STL: {e}") from e
    if not hasattr(tm, "vertices") or len(tm.vertices) == 0:
        raise ValueError("STL file contains no vertices")
    if not hasattr(tm, "faces") or len(tm.faces) == 0:
        raise ValueError("STL file contains no triangles")
    if not np.isfinite(tm.vertices).all():
        raise ValueError("STL file has non-finite vertex coordinates (NaN or inf)")
    # OCC's tessellator emits zero-area triangles at the poles of
    # spherical faces (and similar degenerate spots). They carry no
    # surface, but their zero-length open edges make an otherwise
    # closed mesh read as non-watertight. Drop them before any checks.
    tm.update_faces(tm.nondegenerate_faces())
    tm.merge_vertices()
    return tm


# Build volumes (X, Y, Z) in mm, from the manufacturers' spec sheets.
# Keys are what `--bed` accepts besides an explicit "WxDxH" or "N".
PRINTER_BEDS = {
    "a1": (256, 256, 256),          # Bambu Lab A1
    "a1mini": (180, 180, 180),      # Bambu Lab A1 mini
    "p1s": (256, 256, 256),         # Bambu Lab P1S
    "p1p": (256, 256, 256),         # Bambu Lab P1P
    "x1c": (256, 256, 256),         # Bambu Lab X1 Carbon
    "h2d": (325, 320, 325),         # Bambu Lab H2D, single nozzle
    "mk4": (250, 210, 220),         # Prusa MK4
    "mk4s": (250, 210, 220),        # Prusa MK4S
    "mini": (180, 180, 180),        # Prusa MINI+
    "core1": (250, 220, 270),       # Prusa CORE One
    "ender3": (220, 220, 250),      # Creality Ender-3 / Ender-3 V2
    "k1": (220, 220, 250),          # Creality K1
}


def parse_bed(spec):
    """Turn a printer name, "WxDxH" or a single "N" (cube) into (x, y, z) mm.

    Raises ValueError with the list of known printers on a bad spec.
    """
    raw = spec.strip().lower().replace(" ", "")
    name = raw.replace("-", "").replace("_", "")
    if name in PRINTER_BEDS:
        return PRINTER_BEDS[name]
    try:
        nums = [float(p) for p in raw.split("x")]
    except ValueError:
        nums = []
    if len(nums) == 1:
        nums = nums * 3
    if len(nums) != 3 or not all(math.isfinite(n) and n > 0 for n in nums):
        known = ", ".join(sorted(PRINTER_BEDS))
        raise ValueError(
            f"Unknown bed '{spec}'. Use WxDxH in mm (e.g. 256x256x256) "
            f"or a printer name: {known}"
        )
    return tuple(nums)


def bed_fit(extents, bed, margin=5.0):
    """Check a part's bounding box against a build volume.

    The part may be rotated 90 degrees on the bed, so X/Y are compared
    in both orders. `margin` is kept free on each side in X and Y (purge
    line, brim, skirt). Returns (fits, message).
    """
    x, y, z = (float(v) for v in extents)
    bx, by, bz = (float(v) for v in bed)
    ux, uy = bx - 2 * margin, by - 2 * margin
    fits_xy = (x <= ux and y <= uy) or (y <= ux and x <= uy)
    fits_z = z <= bz
    if fits_xy and fits_z:
        return True, f"fits {bx:.0f}x{by:.0f}x{bz:.0f} bed"
    problems = []
    if not fits_xy:
        problems.append(
            f"footprint {x:.1f}x{y:.1f} exceeds usable "
            f"{ux:.0f}x{uy:.0f} ({margin:.0f} mm margin per side)"
        )
    if not fits_z:
        problems.append(f"height {z:.1f} exceeds {bz:.0f}")
    return False, "; ".join(problems)


def estimate_mass(tm, density=1.24, shell=0.85, infill=0.15):
    """Approximate printed mass in grams (default: PLA, 2 walls, 15% infill).

    A slicer prints a solid skin about `shell` mm thick over the whole
    surface and fills the rest at `infill`. Solid volume x density, the
    old estimate, overstated large parts by 2x or more.
    """
    vol = abs(float(tm.volume))
    skin = min(vol, float(tm.area) * shell)
    return (skin + (vol - skin) * infill) / 1000 * density
