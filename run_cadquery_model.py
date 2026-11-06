#!/usr/bin/env python3
"""
Run a generated CadQuery model script in a subprocess and emit a structured
JSON result so Claude can parse success/failure without the user copy-pasting
tracebacks.

Usage:
    python3 run_cadquery_model.py path/to/model.py
    python3 run_cadquery_model.py path/to/model.py --preview            # also render
    python3 run_cadquery_model.py path/to/model.py --preview --strict   # fail on non-watertight
    python3 run_cadquery_model.py path/to/model.py --bed a1             # fail if it won't fit the printer

3MF and STEP files produced by the script (via cq.exporters.export(result,
"name.3mf") / cq.exporters.export(result, "name.step")) are discovered
automatically and reported alongside the STLs.

Emits a single JSON object to stdout (key order matches the emitted JSON):
    {
      "success": true/false,
      "script": "model.py",
      "stls": ["a.stl", "b.stl"],          # every .stl written during this run
      "stl": "a.stl",                       # newest, for single-file convenience
      "previews": ["a_preview.png", ...],   # one per STL when --preview is set
      "preview": "a_preview.png",           # newest, for single-file convenience
      "threemfs": ["a.3mf", "b.3mf"],       # every .3mf produced by the script
      "threemf": "a.3mf",                   # newest, for single-file convenience
      "steps": ["a.step", "b.step"],        # every .step produced by the script
      "step": "a.step",                     # newest, for single-file convenience
      "watertight": true/false/null,        # true only if ALL meshes are watertight
      "bboxes": [[x, y, z], ...],           # mm, one per STL (after --preview/--strict/--bed)
      "fits_bed": true/false/null,          # null unless --bed is set
      "stdout": "...",
      "stderr": "...",
      "returncode": 0,                      # -1 on timeout / spawn failure
    }

Exit codes:
    0  success
    1  CadQuery script failed, preview failed, --strict rejected output,
       or a part does not fit the --bed build volume
    2  interpreter / script path could not be launched, or bad arguments
       (e.g. an unknown --bed printer)
    3  subprocess timed out
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time


def _sibling(path, suffix):
    return os.path.splitext(path)[0] + suffix


def _append_stderr(result, msg):
    result["stderr"] = (result["stderr"] or "") + msg + "\n"


def _new_files_by_ext(script_dir, after_mtime, exts):
    """Return {ext: [paths]} in script_dir matching each *.{ext}
    (case-insensitive) strictly newer than after_mtime, newest first.
    Dedupes case-variant hits that macOS's case-insensitive filesystem
    returns from both glob patterns.

    The threshold is strict (>=) rather than with a slack window because
    a backward slack would pull in stale files from a previous run started
    less than a second ago, silently reporting them as this run's output.
    Modern filesystems (APFS, ext4, NTFS) have sub-second mtimes, so a
    file written at exactly `after_mtime` is a valid hit.
    """
    buckets = {ext: {} for ext in exts}
    for ext in exts:
        for case in (ext.lower(), ext.upper()):
            for path in glob.glob(os.path.join(script_dir, f"*.{case}")):
                real = os.path.realpath(path)
                if real in buckets[ext]:
                    continue
                try:
                    mtime = os.path.getmtime(path)
                except OSError:
                    continue
                if mtime >= after_mtime:
                    buckets[ext][real] = (mtime, path)
    return {
        ext: [p for _, p in sorted(entries.values(), reverse=True)]
        for ext, entries in buckets.items()
    }


def _process_stls(stls, views, strict, want_preview, bed=None):
    """Load each STL once and optionally render a preview + check watertightness.

    Single pass so an STL is never loaded twice when both outputs are
    requested, and so --strict's watertight check runs on every mesh.

    `mesh_io` is imported lazily because the wrapper's common case (bare
    run, no --preview, no --strict) doesn't touch meshes at all. `preview`
    is imported only inside the rendering branch so that --strict by itself
    stays headless-safe (no pyrender / PyOpenGL required).

    With `bed` (an (x, y, z) build volume), every STL must fit it. Each
    part is its own print, so they are checked one by one; a misfit still
    gets its preview, and every misfit is listed in the error.

    Returns a dict with previews, watertights, bboxes (lists), fits_bed
    (bool or None) and error (str or None). The caller surfaces the error
    into result["stderr"].
    """
    import mesh_io  # trimesh + numpy only

    out = {"previews": [], "watertights": [], "bboxes": [],
           "fits_bed": None, "error": None}
    misfits = []

    for stl in stls:
        try:
            tm = mesh_io.load_mesh(stl)
        except ValueError as e:
            out["error"] = f"Mesh load failed ({stl}): {e}"
            return out

        watertight = bool(tm.is_watertight)
        out["watertights"].append(watertight)
        extents = tm.bounding_box.extents
        out["bboxes"].append([round(float(v), 2) for v in extents])

        if bed is not None:
            fits, msg = mesh_io.bed_fit(extents, bed)
            if not fits:
                misfits.append(f"{os.path.basename(stl)}: {msg}")

        if strict and not watertight:
            out["error"] = f"Mesh {stl} is not watertight (--strict set)."
            return out

        if want_preview:
            import preview  # heavy: trimesh + pyrender, only here
            preview_path = _sibling(stl, "_preview.png")
            title = preview.title_from_path(stl)
            try:
                if views == "multi":
                    preview.render_multi_view(tm, preview_path, title)
                else:
                    preview.render_single(tm, preview_path, title)
            except Exception as e:
                out["error"] = f"Preview render failed ({stl}): {e}"
                return out
            out["previews"].append(preview_path)

    if bed is not None:
        out["fits_bed"] = not misfits
        if misfits:
            out["error"] = (
                "Does not fit the bed: " + "; ".join(misfits) + ". Rotate "
                "the geometry in the script, shrink it, or split it into "
                "parts that join after printing."
            )
    return out


def main():
    parser = argparse.ArgumentParser(
        description="Run a CadQuery model script and report a JSON result",
        epilog="Exit codes: 0 success, 1 script/preview/--strict/--bed failure, "
               "2 interpreter not launchable or bad arguments, 3 timeout.",
    )
    parser.add_argument("script", help="Path to the CadQuery .py file")
    parser.add_argument("--preview", action="store_true",
                        help="Render a multi-view preview PNG for every STL the script wrote")
    parser.add_argument("--strict", action="store_true",
                        help="Fail with exit code 1 if any STL is not watertight, "
                             "or if the script produced no STL at all")
    parser.add_argument("--views", choices=["iso", "multi"], default="multi",
                        help="Preview layout: 'iso' (single isometric) or 'multi' (6-view) (default: multi)")
    parser.add_argument("--bed", default=None, metavar="PRINTER|WxDxH",
                        help="Fail if any STL exceeds this build volume, e.g. 'a1', "
                             "'mk4' or '256x256x256' (5 mm kept free per side)")
    parser.add_argument("--timeout", type=int, default=180,
                        help="Seconds before killing the model script (default: 180)")
    args = parser.parse_args()

    bed = None
    if args.bed:
        import mesh_io
        try:
            bed = mesh_io.parse_bed(args.bed)
        except ValueError as e:
            parser.error(str(e))

    script_path = os.path.abspath(args.script)
    script_dir = os.path.dirname(script_path) or "."

    result = {
        "success": False,
        "script": args.script,
        "stls": [],
        "stl": None,
        "previews": [],
        "preview": None,
        "threemfs": [],
        "threemf": None,
        "steps": [],
        "step": None,
        "watertight": None,
        "bboxes": [],
        "fits_bed": None,
        "stdout": "",
        "stderr": "",
        "returncode": -1,
    }

    started = time.time()

    try:
        proc = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=args.timeout,
            cwd=script_dir,
        )
    except subprocess.TimeoutExpired as e:
        _append_stderr(result, f"Timeout after {args.timeout}s: {e}")
        print(json.dumps(result, indent=2))
        sys.exit(3)
    except FileNotFoundError as e:
        _append_stderr(result, f"Cannot launch interpreter: {e}")
        print(json.dumps(result, indent=2))
        sys.exit(2)

    result["stdout"] = proc.stdout
    result["stderr"] = proc.stderr
    result["returncode"] = proc.returncode
    result["success"] = proc.returncode == 0

    if result["success"]:
        found = _new_files_by_ext(script_dir, started, ("stl", "3mf", "step", "stp"))
        result["stls"] = found["stl"]
        result["threemfs"] = found["3mf"]
        # CadQuery writes .step by convention; .stp is accepted too. Both
        # are merged into one list (newest-first within each extension).
        result["steps"] = found["step"] + found["stp"]

    # --strict implies the run must produce at least one STL. A script that
    # exits 0 but forgot to call cq.exporters.export() would otherwise slip
    # through with an empty stls list and a null watertight claim.
    if (args.strict or bed is not None) and result["success"] and not result["stls"]:
        flag = "--strict" if args.strict else "--bed"
        _append_stderr(result, f"No STL files produced by the script ({flag} set).")
        result["success"] = False

    needs_mesh_pass = args.preview or args.strict or bed is not None
    if needs_mesh_pass and result["success"] and result["stls"]:
        processed = _process_stls(
            result["stls"], args.views, args.strict,
            want_preview=args.preview, bed=bed,
        )
        result["previews"] = processed["previews"]
        result["bboxes"] = processed["bboxes"]
        result["fits_bed"] = processed["fits_bed"]
        if processed["watertights"]:
            result["watertight"] = all(processed["watertights"])
        if processed["error"]:
            _append_stderr(result, processed["error"])
            result["success"] = False

    result["stl"] = result["stls"][0] if result["stls"] else None
    result["preview"] = result["previews"][0] if result["previews"] else None
    result["threemf"] = result["threemfs"][0] if result["threemfs"] else None
    result["step"] = result["steps"][0] if result["steps"] else None

    print(json.dumps(result, indent=2))
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
