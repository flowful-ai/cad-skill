"""Extract a 2D pocket outline from a 3D scan of an object.

Produces the max cross-section of the object's bottom `--zmax` mm (the
region a Gridfinity pocket wraps), as a point list ready to paste into
`GridfinityBin.add_polygon_pocket`. Pipeline: PCA-align the mesh in XY
(long axis to X), drop it to Z=0, optionally scale anisotropically to
known real dims, slice every millimeter, union the sections, simplify.

Example (MX Master 3 cradle from robomo's scan of the mouse):
    python3 outline_from_scan.py scan.stl --dims 124.9x84.3x51 \
        --zmax 19 --out outline.json

With --rotate-min-square the outline is rotated to the angle that
minimizes its bounding square (diagonal placement in a smaller grid)
and the chosen angle is reported.

Deps: trimesh, shapely, numpy (pip install shapely if missing).
"""

import argparse
import json

import numpy as np
import trimesh
from shapely import affinity
from shapely.geometry import Polygon
from shapely.ops import unary_union


def align_and_scale(mesh, dims):
    """PCA-align in XY, center on the origin, floor to Z=0, scale."""
    xy = mesh.vertices[:, :2] - mesh.vertices[:, :2].mean(axis=0)
    evals, evecs = np.linalg.eigh(np.cov(xy.T))
    major = evecs[:, np.argmax(evals)]
    mesh.apply_transform(trimesh.transformations.rotation_matrix(
        -np.arctan2(major[1], major[0]), [0, 0, 1]))
    mesh.apply_translation([-(mesh.bounds[0][0] + mesh.bounds[1][0]) / 2,
                            -(mesh.bounds[0][1] + mesh.bounds[1][1]) / 2,
                            -mesh.bounds[0][2]])
    if dims:
        mesh.apply_scale([d / e for d, e in zip(dims, mesh.extents)])
    return mesh


def max_section_outline(mesh, zmax, step=1.0, simplify=0.25):
    """Union of horizontal sections from Z=step/2 up to zmax."""
    polys = []
    for z in np.arange(step / 2, zmax + 0.01, step):
        sec = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
        if sec is None:
            continue
        for loop in sec.discrete:
            if len(loop) < 10:
                continue
            p = Polygon(loop[:, :2])
            if p.is_valid and p.area > 500:
                polys.append(p)
    u = unary_union(polys)
    if u.geom_type == "MultiPolygon":
        u = max(u.geoms, key=lambda g: g.area)
    return Polygon(u.exterior.coords).simplify(simplify)


def rotate_min_square(poly, clearance):
    """Angle (deg) minimizing the bounding square of poly + clearance."""
    buf = poly.buffer(clearance, join_style=1)
    best = None
    for tenth in range(0, 1800):
        a = tenth / 10
        b = affinity.rotate(buf, a, origin="centroid").bounds
        m = max(b[2] - b[0], b[3] - b[1])
        if best is None or m < best[1]:
            best = (a, m)
    return best


def recentered(poly):
    minx, miny, maxx, maxy = poly.bounds
    return affinity.translate(poly, -(minx + maxx) / 2, -(miny + maxy) / 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mesh", help="STL/mesh scan of the object")
    ap.add_argument("--dims", help="real LxWxH in mm, e.g. 128.2x88.4x50.8; "
                                   "omit to trust the scan's scale")
    ap.add_argument("--zmax", type=float, required=True,
                    help="pocket depth: outline covers Z 0..zmax mm")
    ap.add_argument("--step", type=float, default=1.0)
    ap.add_argument("--simplify", type=float, default=0.25)
    ap.add_argument("--rotate-min-square", action="store_true",
                    help="rotate outline to minimize its bounding square")
    ap.add_argument("--clearance", type=float, default=1.3,
                    help="pocket clearance used for the rotation search")
    ap.add_argument("--out", help="write points as JSON (default: stdout)")
    args = ap.parse_args()

    dims = ([float(v) for v in args.dims.split("x")] if args.dims else None)
    mesh = align_and_scale(trimesh.load(args.mesh), dims)
    print(f"aligned extents: {np.round(mesh.extents, 2)}")

    outline = recentered(max_section_outline(mesh, args.zmax, args.step,
                                             args.simplify))
    if args.rotate_min_square:
        angle, side = rotate_min_square(outline, args.clearance)
        outline = recentered(affinity.rotate(outline, angle,
                                             origin="centroid"))
        print(f"rotated {angle} deg; bounding square incl. clearance: "
              f"{side:.1f}mm")

    pts = [[round(x, 2), round(y, 2)]
           for x, y in list(outline.exterior.coords)[:-1]]
    minx, miny, maxx, maxy = outline.bounds
    print(f"{len(pts)} points, bbox {maxx - minx:.1f} x {maxy - miny:.1f} mm")
    if args.out:
        json.dump(pts, open(args.out, "w"))
        print(f"written: {args.out}")
    else:
        print(json.dumps(pts))


if __name__ == "__main__":
    main()
