#!/usr/bin/env python3
"""
Convert STL files to 3MF via trimesh (Bambu Studio / Orca / PrusaSlicer
prefer 3MF).

WARNING: trimesh's 3MF writer mangles internal cavities. If the input STL
was generated from a CadQuery solid with a cut() cavity (magnet pockets,
enclosed voids, etc.), the cavity's normals get flipped on export and the
slicer will see the cavity as filled. For parametric CadQuery parts,
export 3MF directly from the CadQuery script via
    cq.exporters.export(result, "name.3mf")
which uses CadQuery's native ThreeMFWriter and preserves cavities. This
script is only safe for solid meshes with no enclosed voids.

Usage:
    python3 stl_to_3mf.py model.stl                      # -> model.3mf
    python3 stl_to_3mf.py a.stl b.stl c.stl              # multi-file
    python3 stl_to_3mf.py --out other.3mf model.stl      # explicit output

Requires trimesh + lxml (lxml is needed for the 3MF writer).
"""
import argparse
import os
import sys


def convert(stl_path, out_path=None):
    # Lazy import: loading preview at module level pulls in pyrender (and
    # thus PyOpenGL), which adds ~500 ms of startup for a pure STL->3MF
    # tool that never renders. Import inside the one function that needs it.
    import preview  # reused for "bad STL -> ValueError" consistency

    if out_path is None:
        out_path = os.path.splitext(stl_path)[0] + ".3mf"
    mesh = preview.load_mesh(stl_path)
    mesh.export(out_path)
    return out_path


def main():
    parser = argparse.ArgumentParser(
        description="Convert one or more STL files to 3MF",
        epilog="Exit codes: 0 success, 1 load/export failure, 2 bad arguments.",
    )
    parser.add_argument("stl_files", nargs="+", help="Path(s) to STL file(s)")
    parser.add_argument("--out", default=None,
                        help="Output 3MF path (only valid with a single input; "
                             "multi-file runs write each STL to its sibling .3mf)")
    args = parser.parse_args()

    if args.out and len(args.stl_files) > 1:
        print("ERROR: --out only works with a single input STL", file=sys.stderr)
        sys.exit(2)

    for stl in args.stl_files:
        if not os.path.exists(stl):
            print(f"ERROR: {stl} not found", file=sys.stderr)
            sys.exit(1)
        try:
            out = convert(stl, args.out)
        except ValueError as e:
            print(f"ERROR: {stl}: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"ERROR: failed to write 3MF for {stl}: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"{stl} -> {out}")


if __name__ == "__main__":
    main()
