"""Numbered-callout drawing of a model, for agreeing on part names.

Once a model has more than a handful of features, "the back wall" stops being
a name. The user means one wall and you mean another, you both think you agree,
and a dozen messages later a wrong face has been edited twice. Giving every
feature a number fixes that: the user says "lower (7)" and there is nothing
left to misread.

Two rules make the difference between a drawing that settles an argument and
one that starts another:

1.  **Every outline is ray-cast from the mesh.** Nothing here is drawn from the
    parameter values. If the drawing and the solid disagree, the drawing is
    wrong and visibly so, which is the only way a figure can be trusted as
    evidence about a part.

2.  **Numbers in circles with a key, never text on leader lines.** Leaders
    cross the drawing, collide with each other and obscure the geometry they
    are pointing at. A circled number is 4 mm wide wherever it lands.

Usage:

    python3 callout.py model.stl --out annotated.pdf \\
        --callout "82,-55:Keyboard pocket - the ErgoDox half sits here" \\
        --callout "105,-8:Rear wire notch, for the TRRS and USB cables"

    python3 callout.py model.stl --spec callouts.json --out annotated.pdf

The JSON spec takes the same callouts plus a title, a view and overlays:

    {
      "title": "Fused keyboard tray, LEFT hand",
      "view": "top",
      "above": 17.1,
      "callouts": [{"at": [82, -55], "label": "Keyboard pocket"}],
      "overlays": [{"points": [[0, 0], [70, 0]], "label": "keyboard front edge",
                    "color": "#c02020", "style": "-"}]
    }

Writes the PDF and a PNG beside it. Prints the numbered table so the numbers
can be quoted back to the user in the same message as the drawing.

Deps: trimesh, numpy, matplotlib, Pillow.
"""

import argparse
import json
import os
import sys
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import PIL.Image

import mesh_io

# right, up, and the direction we look along. Callout coordinates and the
# drawing axes are both in the (right, up) frame, so what the user reads off
# the sheet is what they type back.
VIEWS = {
    "top":   (np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
              np.array([0, 0, -1.0]), "x", "y"),
    "bottom": (np.array([1.0, 0, 0]), np.array([0, -1.0, 0]),
               np.array([0, 0, 1.0]), "x", "-y"),
    "front": (np.array([1.0, 0, 0]), np.array([0, 0, 1.0]),
              np.array([0, 1.0, 0]), "x", "z"),
    "right": (np.array([0, -1.0, 0]), np.array([0, 0, 1.0]),
              np.array([-1.0, 0, 0]), "-y", "z"),
}
BIG = 1.0e4         # ray origins well outside any printable part
PLOT_IN = 7.6       # height of the drawing itself, inches
KEY_LINE_IN = 0.21  # one wrapped line of key text
KEY_HEAD_IN = 0.34  # the word KEY
KEY_PAD_IN = 0.22
KEY_WRAP = 108      # characters per key line before wrapping


def occupancy(mesh, view, step, above=None):
    """Ray-cast a silhouette, and optionally a second tier of tall material.

    Returns (a, b, solid, tall). `solid` marks where the part has any
    material at all; `tall` marks where its highest point is above `above`,
    which is what separates a rim from the floor it stands on.
    """
    r, u, d, _, _ = VIEWS[view]
    pa = mesh.vertices @ r
    pb = mesh.vertices @ u
    a = np.arange(pa.min() - step, pa.max() + 2 * step, step)
    b = np.arange(pb.min() - step, pb.max() + 2 * step, step)
    solid = np.zeros((len(b), len(a)))
    tall = np.zeros((len(b), len(a)))
    dirs = np.tile(d, (len(a), 1))
    for j, bv in enumerate(b):
        origins = np.array([r * av + u * bv - d * BIG for av in a])
        loc, idx, _ = mesh.ray.intersects_location(origins, dirs)
        for p, i in zip(loc, idx):
            solid[j, i] = 1.0
            if above is not None and p[2] > above:
                tall[j, i] = 1.0
    return a, b, solid, tall


def load_spec(args):
    """Merge a JSON spec with the command line; the command line wins."""
    spec = {}
    if args.spec:
        with open(args.spec) as fh:
            spec = json.load(fh)
    for flag in ("title", "subtitle", "view", "above"):
        if getattr(args, flag) is not None:
            spec[flag] = getattr(args, flag)
    if args.callout:
        spec["callouts"] = [_parse_callout(c) for c in args.callout]
    spec.setdefault("view", "top")
    spec.setdefault("callouts", [])
    spec.setdefault("overlays", [])
    if spec["view"] not in VIEWS:
        raise ValueError(f"unknown view {spec['view']!r}; "
                         f"choose from {sorted(VIEWS)}")
    if not spec["callouts"]:
        raise ValueError("no callouts given - a drawing with no numbers on it "
                         "is just a preview, and preview.py already does that")
    for i, c in enumerate(spec["callouts"], start=1):
        c.setdefault("n", i)
    return spec


def _parse_callout(text):
    """"x,y:label" -> {"at": [x, y], "label": label}"""
    try:
        at, label = text.split(":", 1)
        x, y = (float(v) for v in at.split(","))
    except ValueError:
        raise ValueError(f"callout {text!r} is not in the form "
                         f'"x,y:label text"') from None
    return {"at": [x, y], "label": label.strip()}


def draw(mesh, spec, out, step=1.2, dpi=130):
    view = spec["view"]
    above = spec.get("above")
    a, b, solid, tall = occupancy(mesh, view, step, above)
    _, _, _, alab, blab = VIEWS[view]

    callouts = spec["callouts"]
    # The key is laid out in INCHES, not axes fractions: with a fraction per
    # entry the block silently ran off the bottom of its axes past about
    # eight callouts, and a key you cannot read is a drawing you cannot use.
    for c in callouts:
        c["lines"] = textwrap.wrap(c["label"], KEY_WRAP) or [""]
    n_lines = sum(len(c["lines"]) for c in callouts)
    key_in = KEY_PAD_IN * 2 + KEY_HEAD_IN + KEY_LINE_IN * n_lines
    fig = plt.figure(figsize=(11.0, PLOT_IN + key_in + 0.9))
    gs = fig.add_gridspec(2, 1, height_ratios=[PLOT_IN, key_in], hspace=0.12)
    ax = fig.add_subplot(gs[0])
    axk = fig.add_subplot(gs[1])
    axk.axis("off")

    ax.contourf(a, b, solid, levels=[0.5, 1.5], colors=["#dcdcdc"])
    if above is not None:
        ax.contourf(a, b, tall, levels=[0.5, 1.5], colors=["#9a9a9a"])
        ax.contour(a, b, tall, levels=[0.5], colors=["#404040"], linewidths=0.9)
    ax.contour(a, b, solid, levels=[0.5], colors=["#202020"], linewidths=1.6)

    for ov in spec["overlays"]:
        pts = np.asarray(ov["points"], dtype=float)
        ax.plot(pts[:, 0], pts[:, 1], color=ov.get("color", "#1050a0"),
                lw=ov.get("width", 2.2), ls=ov.get("style", "-"),
                label=ov.get("label"), zorder=5)
    if any(ov.get("label") for ov in spec["overlays"]):
        ax.legend(loc="lower right", fontsize=9, framealpha=0.92)

    # Frame the PART, never autoscale to the callouts. A single callout typed
    # in the wrong frame used to drag the limits out and shrink the part to a
    # smudge - and then the blank-output guard fired, blaming the drawing.
    ma = (a[-1] - a[0]) * 0.06
    mb = (b[-1] - b[0]) * 0.06
    xlim = (a[0] - ma, a[-1] + ma)
    ylim = (b[0] - mb, b[-1] + mb)

    span = max(a[-1] - a[0], b[-1] - b[0])
    rad = span * 0.022
    off, outside = [], []
    for c in callouts:
        cx, cy = float(c["at"][0]), float(c["at"][1])
        if not (xlim[0] <= cx <= xlim[1] and ylim[0] <= cy <= ylim[1]):
            outside.append(c["n"])
        elif not _on_material(a, b, solid, cx, cy, rad):
            off.append(c["n"])
    if outside:
        raise ValueError(
            f"callouts {outside} fall outside the drawing entirely "
            f"({alab} {xlim[0]:.1f}..{xlim[1]:.1f}, "
            f"{blab} {ylim[0]:.1f}..{ylim[1]:.1f}). They would be invisible, "
            f"so the coordinates are almost certainly in the wrong frame or "
            f"the wrong view.")

    # The marker is a fixed-size circle in DATA units, so it stays legible
    # without a leader line and cannot drift off what it points at.
    for c in callouts:
        cx, cy = float(c["at"][0]), float(c["at"][1])
        ax.add_patch(plt.Circle((cx, cy), rad, fc="white", ec="black",
                                lw=1.5, zorder=20))
        ax.text(cx, cy, str(c["n"]), ha="center", va="center", fontsize=11.5,
                fontweight="bold", zorder=21)

    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_aspect("equal")
    ax.set_title(spec.get("title", os.path.basename(out)) + "\n"
                 + spec.get("subtitle",
                            f"{view} view, outlines ray-cast from the solid"),
                 fontsize=13, fontweight="bold")
    ax.set_xlabel(f"{alab}  (mm)", fontsize=10.5)
    ax.set_ylabel(f"{blab}  (mm)", fontsize=10.5)
    ax.grid(alpha=0.2, lw=0.5)

    def at(inches_from_top):
        return 1.0 - inches_from_top / key_in

    axk.text(0.0, at(KEY_PAD_IN), "KEY", fontsize=13, fontweight="bold",
             va="top", transform=axk.transAxes)
    cur = KEY_PAD_IN + KEY_HEAD_IN
    for c in callouts:
        axk.text(0.012, at(cur), f"({c['n']})", fontsize=10.8,
                 fontweight="bold", va="top", transform=axk.transAxes)
        for ln in c["lines"]:
            axk.text(0.062, at(cur), ln, fontsize=10.3, va="top",
                     transform=axk.transAxes)
            cur += KEY_LINE_IN
    assert at(cur) >= -0.01, "key block overflowed its axes"
    shade = ("Shading: light grey = silhouette"
             + ("; mid grey = material standing above "
                f"z = {above:g}." if above is not None else "."))
    axk.text(0.0, 0.0, shade, fontsize=9.6, va="bottom", color="#333",
             transform=axk.transAxes)

    png = os.path.splitext(out)[0] + ".png"
    fig.savefig(out, bbox_inches="tight")
    fig.savefig(png, dpi=dpi, bbox_inches="tight")
    plt.close(fig)

    # A figure that produced nothing still saves without complaint. This has
    # happened: a section plane built with its normal the wrong way round cut
    # nothing, and the result was a clean, blank, confident drawing.
    px = np.asarray(PIL.Image.open(png).convert("L"), dtype=float)
    ink = float((px < 200).mean())
    if ink < 0.02:
        raise RuntimeError(f"drawing looks blank - only {ink * 100:.2f}% of "
                           f"pixels have ink; the plot produced nothing")
    return png, ink, off


def _on_material(a, b, solid, cx, cy, rad):
    """Is a callout sitting on the part, or pointing into empty space?"""
    ja = np.abs(a - cx) <= rad
    jb = np.abs(b - cy) <= rad
    if not ja.any() or not jb.any():
        return False
    return bool(solid[np.ix_(jb, ja)].any())


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("stl")
    p.add_argument("--out", default="annotated.pdf",
                   help="PDF to write; a PNG is written beside it")
    p.add_argument("--spec", help="JSON spec (see the module docstring)")
    p.add_argument("--callout", action="append",
                   help='"x,y:label text", repeatable')
    p.add_argument("--view", choices=sorted(VIEWS))
    p.add_argument("--above", type=float,
                   help="shade material standing above this world z "
                        "separately, to tell a rim from its floor")
    p.add_argument("--title")
    p.add_argument("--subtitle")
    p.add_argument("--step", type=float, default=1.2,
                   help="ray-cast grid pitch in mm (default 1.2)")
    args = p.parse_args()

    try:
        mesh = mesh_io.load_mesh(args.stl)
        mesh.merge_vertices()
        spec = load_spec(args)
        png, ink, off = draw(mesh, spec, args.out, step=args.step)
    except (ValueError, RuntimeError) as e:
        sys.exit(f"callout.py: {e}")

    print(f"wrote {args.out} and {png}")
    print(f"  {spec['view']} view, ink coverage {ink * 100:.1f}% "
          f"(blank-output check passed)")
    for c in spec["callouts"]:
        print(f"  ({c['n']})  {c['label']}")
    if off:
        print(f"  WARNING: callouts {off} sit on a gap, not on material. "
              f"That is right for an aperture, a notch or a slot, and wrong "
              f"for anything else - check them before quoting the numbers.")


if __name__ == "__main__":
    main()
