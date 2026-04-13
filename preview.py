#!/usr/bin/env python3
"""
Render preview images of a CadQuery model for visual inspection.

Usage:
    python3 preview.py model.stl [output.png]
    python3 preview.py model.stl --views multi       # 4-view technical sheet
    python3 preview.py model.stl --views iso          # single isometric
    python3 preview.py model.stl --resolution 800     # higher-res per view

Dependencies:
    pip install trimesh pyrender Pillow
"""
import sys
import os
import argparse
import math
import numpy as np

# Pyrender needs an OpenGL context for offscreen rendering.
# On Linux set PYOPENGL_PLATFORM=egl (GPU) or osmesa (CPU) before import.
# On macOS the default CGL/pyglet backend works — do NOT set egl/osmesa.
import platform as _plat
if _plat.system() == "Linux" and "PYOPENGL_PLATFORM" not in os.environ:
    os.environ["PYOPENGL_PLATFORM"] = "egl"

import trimesh
import pyrender
from PIL import Image, ImageDraw, ImageFont

from mesh_io import load_mesh  # re-exported: preview's public surface for mesh loading


# ---------------------------------------------------------------------------
# Scene + camera helpers
# ---------------------------------------------------------------------------

def _rotation_matrix(elev_deg, azim_deg):
    """Build a camera-pose matrix from elevation and azimuth (degrees).

    Convention:
        azim  = rotation around Z (world up)
        elev  = rotation above the XY plane
    Returns a 4x4 camera pose (OpenGL: -Z forward, +Y up).
    """
    elev = math.radians(elev_deg)
    azim = math.radians(azim_deg)

    # Camera position on a unit sphere
    cx = math.cos(elev) * math.cos(azim)
    cy = math.cos(elev) * math.sin(azim)
    cz = math.sin(elev)
    eye = np.array([cx, cy, cz])

    # Look-at
    target = np.array([0.0, 0.0, 0.0])
    up = np.array([0.0, 0.0, 1.0])

    forward = target - eye
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, up)
    if np.linalg.norm(right) < 1e-6:
        # Degenerate case (looking straight down/up)
        up = np.array([0.0, 1.0, 0.0])
        right = np.cross(forward, up)
    right /= np.linalg.norm(right)
    cam_up = np.cross(right, forward)

    # Build OpenGL camera matrix (-Z forward)
    pose = np.eye(4)
    pose[0:3, 0] = right
    pose[0:3, 1] = cam_up
    pose[0:3, 2] = -forward
    pose[0:3, 3] = eye
    return pose


def _nice_spacing(extent):
    """Pick a human-friendly grid spacing that gives ~8-12 lines."""
    target = extent / 10
    for s in [1, 2, 5, 10, 20, 50, 100, 200]:
        if s >= target:
            return s
    return 200


def _build_grid(tm):
    """Create a ground-plane grid mesh at the bottom of the object.

    Returns (ground_plane_trimesh, grid_lines_trimesh).
    """
    bounds = tm.bounds  # shape (2, 3): [[min_x,y,z], [max_x,y,z]]
    z_floor = bounds[0][2]
    cx, cy = tm.bounding_box.centroid[:2]

    extent = max(bounds[1][0] - bounds[0][0], bounds[1][1] - bounds[0][1])
    spacing = _nice_spacing(extent)
    pad = extent * 0.5

    # Snap grid bounds to spacing multiples
    x0 = math.floor((cx - extent / 2 - pad) / spacing) * spacing
    x1 = math.ceil((cx + extent / 2 + pad) / spacing) * spacing
    y0 = math.floor((cy - extent / 2 - pad) / spacing) * spacing
    y1 = math.ceil((cy + extent / 2 + pad) / spacing) * spacing

    lw = max(0.4, spacing * 0.02)  # line half-width

    # --- Ground plane (slightly below grid lines to avoid z-fighting) ---
    ground = trimesh.creation.box(
        extents=[x1 - x0, y1 - y0, 0.01],
        transform=trimesh.transformations.translation_matrix(
            [(x0 + x1) / 2, (y0 + y1) / 2, z_floor - 0.02]
        ),
    )

    # --- Grid lines as thin quads at z_floor ---
    verts = []
    faces = []

    def _add_quad(v0, v1, v2, v3):
        n = len(verts)
        verts.extend([v0, v1, v2, v3])
        faces.extend([[n, n + 1, n + 2], [n, n + 2, n + 3]])

    # Lines parallel to X axis (one per Y tick)
    y = y0
    while y <= y1 + 0.001:
        _add_quad(
            [x0, y - lw, z_floor], [x1, y - lw, z_floor],
            [x1, y + lw, z_floor], [x0, y + lw, z_floor],
        )
        y += spacing

    # Lines parallel to Y axis (one per X tick)
    x = x0
    while x <= x1 + 0.001:
        _add_quad(
            [x - lw, y0, z_floor], [x + lw, y0, z_floor],
            [x + lw, y1, z_floor], [x - lw, y1, z_floor],
        )
        x += spacing

    grid_lines = trimesh.Trimesh(
        vertices=np.array(verts), faces=np.array(faces)
    )
    return ground, grid_lines


def _build_scene(tm, include_ground=True):
    """Create a pyrender scene containing the mesh, lights, and optionally ground.

    Returns (scene, bounding_sphere_radius, center, ground_node, grid_node).
    ground_node/grid_node are None if include_ground is False.
    """
    # Compute smooth vertex normals so Phong shading looks good
    tm.fix_normals()

    mesh = pyrender.Mesh.from_trimesh(
        tm,
        smooth=True,
        material=pyrender.MetallicRoughnessMaterial(
            baseColorFactor=[0.42, 0.62, 0.92, 1.0],  # medium blue
            metallicFactor=0.1,
            roughnessFactor=0.6,
            doubleSided=True,
        ),
    )

    scene = pyrender.Scene(
        bg_color=[0.90, 0.90, 0.92, 1.0],  # neutral light gray
        ambient_light=[0.3, 0.3, 0.3],
    )
    scene.add(mesh)

    # Ground grid (skipped for below-horizon views to avoid occluding the model)
    ground_node = None
    grid_node = None
    if include_ground:
        ground, grid_lines = _build_grid(tm)
        ground_mat = pyrender.MetallicRoughnessMaterial(
            baseColorFactor=[0.82, 0.82, 0.84, 1.0],
            metallicFactor=0.0,
            roughnessFactor=0.9,
        )
        grid_mat = pyrender.MetallicRoughnessMaterial(
            baseColorFactor=[0.68, 0.68, 0.72, 1.0],
            metallicFactor=0.0,
            roughnessFactor=0.9,
        )
        ground_node = scene.add(pyrender.Mesh.from_trimesh(ground, material=ground_mat, smooth=False))
        grid_node = scene.add(pyrender.Mesh.from_trimesh(grid_lines, material=grid_mat, smooth=False))

    # Four-point lighting: three from above + one from below so the
    # bottom view (Z-) isn't in total shadow.
    for direction in ([1, 1, 1], [-1, 0.5, 0.5], [0, -1, 1], [0, 0.5, -1]):
        light = pyrender.DirectionalLight(color=[1.0, 1.0, 1.0], intensity=2.5)
        d = np.array(direction, dtype=float)
        d /= np.linalg.norm(d)
        pose = np.eye(4)
        pose[0:3, 2] = -d  # pyrender light shines along -Z of its frame
        scene.add(light, pose=pose)

    # Bounding sphere for camera framing
    center = tm.bounding_box.centroid
    radius = np.linalg.norm(tm.bounding_box.extents) / 2.0

    return scene, radius, center, ground_node, grid_node


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

DEFAULT_VIEW_SIZE = 600  # width/height of each sub-view (multi-view)
_SINGLE_WIDTH = 900      # single isometric view defaults
_SINGLE_HEIGHT = 750


def _add_edges(color, depth, strength=0.6):
    """Overlay edge lines detected from the depth buffer onto the color image."""
    valid = depth > 0
    if not valid.any():
        return color

    # Normalise depth into 0-1 range for gradient detection
    d = np.zeros_like(depth)
    d_min, d_max = depth[valid].min(), depth[valid].max()
    if d_max - d_min > 0:
        d[valid] = (depth[valid] - d_min) / (d_max - d_min)

    # Sobel-style gradient magnitude
    dy = np.zeros_like(d)
    dx = np.zeros_like(d)
    dy[1:, :] = np.abs(d[1:, :] - d[:-1, :])
    dx[:, 1:] = np.abs(d[:, 1:] - d[:, :-1])
    edges = np.sqrt(dx ** 2 + dy ** 2)

    # Object-boundary edges (depth jumps from 0 to non-zero)
    boundary = np.zeros_like(valid)
    boundary[1:, :] |= (valid[1:, :] != valid[:-1, :])
    boundary[:, 1:] |= (valid[:, 1:] != valid[:, :-1])

    # Normalise to 0-1 and apply threshold
    p = np.percentile(edges[valid], 97) if valid.sum() > 100 else 1.0
    if p > 0:
        edges = np.clip(edges / p, 0, 1)
    edge_alpha = np.clip(edges * strength, 0, strength)
    edge_alpha[boundary] = np.maximum(edge_alpha[boundary], strength * 0.8)

    # Darken colour at edge pixels
    result = color.astype(np.float32)
    result *= (1 - edge_alpha[:, :, np.newaxis])
    return np.clip(result, 0, 255).astype(np.uint8)


def _render_frame(scene, radius, center, elev, azim, renderer):
    """Render one frame from an existing scene.

    Adds a camera, renders, then removes the camera so the scene can be
    reused for additional views without rebuilding.
    """
    yfov = math.radians(35)
    cam = pyrender.PerspectiveCamera(yfov=yfov)
    distance = radius / math.sin(yfov / 2) * 1.15  # slight padding

    cam_pose = _rotation_matrix(elev, azim)
    cam_pose[0:3, 3] = center + cam_pose[0:3, 2] * distance

    cam_node = scene.add(cam, pose=cam_pose)
    try:
        color, depth = renderer.render(scene)
    except Exception as e:
        scene.remove_node(cam_node)
        raise RuntimeError(
            f"Rendering failed: {e}\n"
            "On Linux without GPU, try: PYOPENGL_PLATFORM=osmesa python3 preview.py ..."
        ) from e
    scene.remove_node(cam_node)

    color = _add_edges(color, depth)
    return Image.fromarray(color)


def render_view(tm, elev, azim, width=DEFAULT_VIEW_SIZE, height=DEFAULT_VIEW_SIZE):
    """Render the mesh from a specific angle. Returns a PIL Image."""
    scene, radius, center, _, _ = _build_scene(tm)
    renderer = None
    try:
        renderer = pyrender.OffscreenRenderer(width, height)
        img = _render_frame(scene, radius, center, elev, azim, renderer)
    finally:
        if renderer is not None:
            renderer.delete()
    return img


def _get_font(size=14):
    """Try to load a nice sans-serif font, falling back to PIL default."""
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _info_lines(tm):
    """Two-line footer with dimensions, volume, triangle count, and status."""
    extents = tm.bounding_box.extents
    line1 = f"Bounding box: {extents[0]:.1f} x {extents[1]:.1f} x {extents[2]:.1f} mm"
    try:
        vol = abs(tm.volume)
        line1 += f"  |  Volume: {vol/1000:.1f} cm\u00b3"
    except Exception:
        pass

    line2 = f"Triangles: {len(tm.faces):,}"
    line2 += f"  |  {'Watertight' if tm.is_watertight else 'NOT watertight'}"
    try:
        vol = abs(tm.volume)
        weight_g = vol / 1000 * 1.24  # PLA density ~1.24 g/cm3
        line2 += f"  |  PLA estimate: ~{weight_g:.0f} g"
    except Exception:
        pass
    return line1, line2


def render_single(tm, output_path, title="Model Preview", width=_SINGLE_WIDTH, height=_SINGLE_HEIGHT):
    """Render a single isometric view with title and footer."""
    img = render_view(tm, elev=25, azim=-60, width=width, height=height)

    # Add title + footer
    canvas = Image.new("RGB", (img.width, img.height + 100), "white")
    canvas.paste(img, (0, 40))
    draw = ImageDraw.Draw(canvas)

    title_font = _get_font(20)
    info_font = _get_font(13)
    line1, line2 = _info_lines(tm)

    draw.text((canvas.width // 2, 10), title, fill="black", font=title_font, anchor="mt")
    draw.text((canvas.width // 2, canvas.height - 30), line1,
              fill="gray", font=info_font, anchor="mb")
    draw.text((canvas.width // 2, canvas.height - 10), line2,
              fill="gray", font=info_font, anchor="mb")

    canvas.save(output_path)
    return output_path


def render_multi_view(tm, output_path, title="Model Preview", subtitle=None, view_size=DEFAULT_VIEW_SIZE):
    """Render 6-view technical preview in a 3x2 grid.

    Views: isometric, front, right (top row), back-iso, top, bottom (bottom row).
    Builds the scene once and reuses a single renderer for all views.
    """
    views = [
        (25,  -60, "Isometric"),
        (5,   -90, "Front (Y-)"),
        (5,     0, "Right (X+)"),
        (25,  120, "Back Isometric"),
        (90,  -90, "Top (Z+)"),
        (-90, -90, "Bottom (Z-)"),
    ]

    scene, radius, center, _, _ = _build_scene(tm, include_ground=True)
    scene_bottom, _, _, _, _ = _build_scene(tm, include_ground=False)
    renderer = None
    try:
        renderer = pyrender.OffscreenRenderer(view_size, view_size)
        images = []
        for elev, azim, label in views:
            s = scene_bottom if elev < 0 else scene
            img = _render_frame(s, radius, center, elev, azim, renderer)
            images.append((img, label))
    finally:
        if renderer is not None:
            renderer.delete()

    # Compose 3x2 grid
    cols = 3
    rows = 2
    gap = 4
    header_h = 40 + (20 if subtitle else 0)
    footer_h = 55
    label_h = 24
    w = view_size * cols + gap * (cols - 1)
    h = view_size * rows + gap * (rows - 1) + header_h + footer_h + label_h * rows

    canvas = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(canvas)

    title_font = _get_font(20)
    subtitle_font = _get_font(14)
    label_font = _get_font(14)
    info_font = _get_font(13)

    # Title + optional subtitle
    draw.text((w // 2, 12), title, fill="black", font=title_font, anchor="mt")
    if subtitle:
        draw.text((w // 2, 34), subtitle, fill="#666666", font=subtitle_font, anchor="mt")

    for idx, (img, label) in enumerate(images):
        col = idx % cols
        row = idx // cols
        px = col * (view_size + gap)
        py = header_h + label_h + row * (view_size + gap + label_h)
        canvas.paste(img, (px, py))
        draw.text((px + view_size // 2, py - 4), label,
                  fill="#444444", font=label_font, anchor="mb")

    # Footer (two lines)
    line1, line2 = _info_lines(tm)
    draw.text((w // 2, h - 30), line1, fill="gray", font=info_font, anchor="mb")
    draw.text((w // 2, h - 10), line2, fill="gray", font=info_font, anchor="mb")

    canvas.save(output_path)
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Preview a 3D model STL file")
    parser.add_argument("stl_file", help="Path to STL file")
    parser.add_argument("output", nargs="?", default=None,
                        help="Output PNG path (default: <stl_name>_preview.png)")
    parser.add_argument("--views", choices=["iso", "multi"], default="multi",
                        help="View mode: iso (single) or multi (4-view)")
    parser.add_argument("--title", default=None, help="Title for the preview")
    parser.add_argument("--resolution", type=int, default=DEFAULT_VIEW_SIZE,
                        help=f"Pixels per view (default: {DEFAULT_VIEW_SIZE})")
    parser.add_argument("--subtitle", default=None,
                        help="Subtitle shown below the title (e.g. model description or usage)")
    parser.add_argument("--strict", action="store_true",
                        help="Fail with exit code 2 if the mesh is not watertight")
    args = parser.parse_args()

    if args.output is None:
        base = os.path.splitext(args.stl_file)[0]
        args.output = f"{base}_preview.png"

    if args.title is None:
        args.title = os.path.splitext(os.path.basename(args.stl_file))[0].replace("_", " ").title()

    try:
        tm = load_mesh(args.stl_file)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    extents = tm.bounding_box.extents
    print(f"Model: {args.stl_file}")
    print(f"Bounding box: {extents[0]:.1f} x {extents[1]:.1f} x {extents[2]:.1f} mm")
    print(f"Triangles: {len(tm.faces)}")

    if tm.is_watertight:
        print("Mesh: watertight (good)")
    else:
        print("WARNING: Mesh is NOT watertight. May cause slicing issues.",
              file=sys.stderr)
        if args.strict:
            print("ERROR: --strict set, aborting before render.",
                  file=sys.stderr)
            sys.exit(2)

    if args.views == "multi":
        render_multi_view(tm, args.output, args.title, subtitle=args.subtitle,
                          view_size=args.resolution)
    else:
        scale = args.resolution / DEFAULT_VIEW_SIZE
        render_single(tm, args.output, args.title,
                      width=int(_SINGLE_WIDTH * scale), height=int(_SINGLE_HEIGHT * scale))

    print(f"Preview saved: {args.output} ({os.path.getsize(args.output)} bytes)")


if __name__ == "__main__":
    main()
