"""Fit checks for printed parts that go together (lids, joints, segments).

A preview shows each part alone, so it cannot tell whether two parts
collide or rattle once assembled. Build both parts, move one to its
assembled position, then:

    from mating import check_mating
    check_mating(box, lid.translate((0, 0, box_h)), clearance=0.3,
                 axes=("x", "y"))

Vendored like gridfinity.py: copy it next to the model script.
"""

_AXES = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}


class MatingError(AssertionError):
    pass


def overlap(a, b):
    """Volume in mm^3 shared by two CadQuery Workplanes (0 when apart)."""
    common = a.intersect(b)
    return common.val().Volume() if common.vals() else 0.0


def check_mating(fixed, moving, clearance, axes=("x", "y"), probe=0.1,
                 tol=1e-3, min_capture=1.0):
    """Raise MatingError unless `moving` fits `fixed` with play only up to
    `clearance` along each axis in `axes`.

    Two conditions, both needed for a joint that works:
      1. In the assembled position the parts do not intersect.
      2. Shifted by clearance + probe along each listed axis, both
         directions, they do intersect: the joint locates instead of
         rattling. Leave an axis out when something else holds it
         (screws, gravity).
    """
    nominal = overlap(fixed, moving)
    if nominal > tol:
        raise MatingError(f"parts collide when assembled ({nominal:.2f} mm3)")
    step = clearance + probe
    for name in axes:
        ux, uy, uz = _AXES[name]
        for sign in (1, -1):
            shifted = moving.translate((sign * step * ux, sign * step * uy,
                                        sign * step * uz))
            if overlap(fixed, shifted) < min_capture:
                raise MatingError(
                    f"no capture along {'+' if sign > 0 else '-'}{name}: a "
                    f"{step:.2f} mm shift does not hit anything, the joint "
                    "will rattle or fall apart"
                )
    return nominal
