#!/usr/bin/env python3
"""
Render preview images of a CadQuery model for visual inspection.

Usage:
    python3 preview.py model.stl [output.png]
    python3 preview.py model.stl --views multi   # 4-view technical sheet
    python3 preview.py model.stl --views iso      # single isometric (default)

Dependencies:
    pip install numpy-stl matplotlib
"""
import sys
import os
import argparse
import numpy as np
from stl import mesh
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


def load_stl(path):
    """Load STL and return mesh object. Exits on failure."""
    try:
        stl_mesh = mesh.Mesh.from_file(path)
    except Exception as e:
        print(f"ERROR: Failed to load STL: {e}")
        sys.exit(1)
    if len(stl_mesh.vectors) == 0:
        print("ERROR: STL file contains no triangles")
        sys.exit(1)
    return stl_mesh


def get_bounds(stl_mesh):
    """Get bounding box of mesh."""
    mins = np.array([stl_mesh.x.min(), stl_mesh.y.min(), stl_mesh.z.min()])
    maxs = np.array([stl_mesh.x.max(), stl_mesh.y.max(), stl_mesh.z.max()])
    center = (mins + maxs) / 2
    size = maxs - mins
    return mins, maxs, center, size


def set_equal_aspect(ax, mins, maxs):
    """Force equal aspect ratio on 3D axes so the model isn't distorted."""
    ranges = maxs - mins
    max_range = ranges.max()
    center = (mins + maxs) / 2
    margin = max_range * 0.15
    half = max_range / 2 + margin
    ax.set_xlim(center[0] - half, center[0] + half)
    ax.set_ylim(center[1] - half, center[1] + half)
    ax.set_zlim(center[2] - half, center[2] + half)


def setup_3d_axes(ax, stl_mesh, elev, azim, title=None):
    """Configure a 3D axes with the mesh rendered."""
    polygons = Poly3DCollection(stl_mesh.vectors, alpha=0.85)
    polygons.set_facecolor([0.55, 0.70, 0.88])
    polygons.set_edgecolor([0.3, 0.3, 0.3])
    polygons.set_linewidth(0.1)
    ax.add_collection3d(polygons)

    mins, maxs, center, size = get_bounds(stl_mesh)
    set_equal_aspect(ax, mins, maxs)
    ax.view_init(elev=elev, azim=azim)

    ax.set_xlabel('X (mm)', fontsize=8)
    ax.set_ylabel('Y (mm)', fontsize=8)
    ax.set_zlabel('Z (mm)', fontsize=8)
    ax.tick_params(labelsize=7)

    ax.xaxis.pane.fill = False
    ax.yaxis.pane.fill = False
    ax.zaxis.pane.fill = False

    if title:
        ax.set_title(title, fontsize=10, fontweight='bold')


def get_volume_text(stl_mesh):
    """Safely compute volume string, returning empty on failure."""
    try:
        volume = stl_mesh.get_mass_properties()[0]
        return f"  |  Volume: ~{abs(volume):.0f} mm\u00b3"
    except Exception:
        return ""


def render_single(stl_mesh, output_path, title="Model Preview"):
    """Render a single isometric view."""
    fig = plt.figure(figsize=(10, 8), dpi=120)
    ax = fig.add_subplot(111, projection='3d')
    setup_3d_axes(ax, stl_mesh, elev=25, azim=-60, title=title)

    mins, maxs, center, size = get_bounds(stl_mesh)
    dim_text = f"Bounding box: {size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm"
    dim_text += get_volume_text(stl_mesh)
    fig.text(0.5, 0.02, dim_text, ha='center', fontsize=9, style='italic',
             color='gray')

    plt.tight_layout()
    plt.savefig(output_path, dpi=120, bbox_inches='tight',
                facecolor='white', pad_inches=0.3)
    plt.close()
    return output_path


def render_multi_view(stl_mesh, output_path, title="Model Preview"):
    """Render 4-view technical preview: iso, front, top, right."""
    fig = plt.figure(figsize=(14, 11), dpi=120)
    fig.suptitle(title, fontsize=14, fontweight='bold', y=0.98)

    views = [
        (221, 25, -60, "Isometric"),
        (222, 5,  -90, "Front (Y-)"),
        (223, 90, -90, "Top (Z+)"),
        (224, 5,    0, "Right (X+)"),
    ]

    for subplot, elev, azim, view_title in views:
        ax = fig.add_subplot(subplot, projection='3d')
        setup_3d_axes(ax, stl_mesh, elev, azim, title=view_title)

    mins, maxs, center, size = get_bounds(stl_mesh)
    dim_text = f"Bounding box: {size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm"
    dim_text += get_volume_text(stl_mesh)
    fig.text(0.5, 0.01, dim_text, ha='center', fontsize=9, style='italic',
             color='gray')

    plt.tight_layout(rect=[0, 0.03, 1, 0.96])
    plt.savefig(output_path, dpi=120, bbox_inches='tight',
                facecolor='white', pad_inches=0.3)
    plt.close()
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Preview a 3D model STL file")
    parser.add_argument("stl_file", help="Path to STL file")
    parser.add_argument("output", nargs="?", default=None,
                        help="Output PNG path (default: <stl_name>_preview.png)")
    parser.add_argument("--views", choices=["iso", "multi"], default="multi",
                        help="View mode: iso (single) or multi (4-view)")
    parser.add_argument("--title", default=None, help="Title for the preview")
    args = parser.parse_args()

    if not os.path.exists(args.stl_file):
        print(f"ERROR: File not found: {args.stl_file}")
        sys.exit(1)

    if args.output is None:
        base = os.path.splitext(args.stl_file)[0]
        args.output = f"{base}_preview.png"

    if args.title is None:
        args.title = os.path.splitext(os.path.basename(args.stl_file))[0].replace("_", " ").title()

    stl_mesh = load_stl(args.stl_file)
    mins, maxs, center, size = get_bounds(stl_mesh)

    print(f"Model: {args.stl_file}")
    print(f"Bounding box: {size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm")
    print(f"Triangles: {len(stl_mesh.vectors)}")

    if args.views == "multi":
        render_multi_view(stl_mesh, args.output, args.title)
    else:
        render_single(stl_mesh, args.output, args.title)

    print(f"Preview saved: {args.output} ({os.path.getsize(args.output)} bytes)")


if __name__ == "__main__":
    main()
