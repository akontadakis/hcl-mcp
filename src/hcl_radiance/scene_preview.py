"""matplotlib PNG scene previews (plan + 3D). Geometry extraction is pure stdlib; only the
two render functions use matplotlib. Works in the POST-north final frame so it aligns with
.pts files written by the sensor tools (already north-rotated)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from hcl_radiance.geometry_import import _to_world, _glass_groups
from hcl_radiance.footprint import floor_polygons
from hcl_radiance.sensor_methodology import floor_top_z, _ceiling_z

# name -> (colour, matplotlib marker, legend label)
_STYLE = {
    "grid": ("#e8820c", "o", "grid @0.8 m"),
    "photosensors": ("#1a9850", "D", "daylight sensor"),
    "observers": ("#d73027", "o", "observer"),
}
_LUM_FACE, _LUM_EDGE, _WIN = "#f4c430", "#d4a017", "#00b0d0"


def object_xy_bbox(parsed, name, scale, up_axis, north_angle_deg=None):
    pts = []
    for f in parsed["faces"]:
        if f.get("object") == name or f.get("group") == name:
            for vi in f["verts"]:
                wx, wy, _ = _to_world(parsed["vertices"][vi - 1], up_axis, north_angle_deg, scale)
                pts.append((wx, wy))
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys)), (max(xs), max(ys))


def build_scene(parsed, material_map, scale, up_axis, north_angle_deg, luminaire_groups=None):
    polys = floor_polygons(parsed, material_map, scale, up_axis, north_angle_deg=north_angle_deg)
    z_floor = floor_top_z(parsed, material_map, scale, up_axis)
    cz = _ceiling_z(parsed, material_map, scale, up_axis, z_floor)
    if cz is None:
        allz = [_to_world(v, up_axis, None, scale)[2] for v in parsed["vertices"]]
        cz = max(allz) if allz else z_floor + 3.0
    # windows: XY extent + Z extent of each glass face
    glass = _glass_groups(material_map)
    windows = []
    for f in parsed["faces"]:
        if f["group"] in glass:
            wp = [_to_world(parsed["vertices"][vi - 1], up_axis, north_angle_deg, scale)
                  for vi in f["verts"]]
            xs = [p[0] for p in wp]
            ys = [p[1] for p in wp]
            zs = [p[2] for p in wp]
            windows.append((min(xs), min(ys), max(xs), max(ys), min(zs), max(zs)))
    luminaires = []
    for g in (luminaire_groups or []):
        bb = object_xy_bbox(parsed, g, scale, up_axis, north_angle_deg)
        if bb:
            (x0, y0), (x1, y1) = bb
            luminaires.append((x0, y0, x1, y1))
    return {"footprint": polys, "windows": windows, "luminaires": luminaires,
            "z_floor": z_floor, "z_ceiling": cz}


def _box_aspect(scene):
    """Relative (x, y, z) proportions for the 3D view, derived from the room's real
    footprint bounds and floor/ceiling height — so ANY room shape renders true, rather
    than a hardcoded office proportion. Every component is clamped >0 so matplotlib's
    set_box_aspect never sees a zero (degenerate/empty footprint -> unit cube)."""
    xy = [pt for ring in scene["footprint"] for pt in ring]
    if xy:
        dx = max(p[0] for p in xy) - min(p[0] for p in xy)
        dy = max(p[1] for p in xy) - min(p[1] for p in xy)
    else:
        dx = dy = 0.0
    dz = scene["z_ceiling"] - scene["z_floor"]
    return (dx or 1.0, dy or 1.0, dz or 1.0)


def render_plan(scene, layers, out_path, *, size_in=6.0, dpi=150):
    fig, ax = plt.subplots(figsize=(size_in, size_in))
    for ring in scene["footprint"]:
        xs = [p[0] for p in ring] + [ring[0][0]]
        ys = [p[1] for p in ring] + [ring[0][1]]
        ax.plot(xs, ys, color="#333", lw=1.5)
    lum_label = "luminaire"
    for (x0, y0, x1, y1) in scene["luminaires"]:
        ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor=_LUM_FACE,
                                   edgecolor=_LUM_EDGE, alpha=0.7, label=lum_label))
        lum_label = None
    win_label = "window"
    for w in scene["windows"]:
        x0, y0, x1, y1 = w[:4]
        ax.plot([x0, x1], [y0, y1], color=_WIN, lw=3, label=win_label)
        win_label = None
    for name, pts in layers.items():
        color, marker, label = _STYLE.get(name, ("#333", "o", name))
        ax.scatter([p[0] for p in pts], [p[1] for p in pts], c=color, marker=marker,
                   s=45, edgecolors="k", linewidths=0.4, zorder=3, label=label)
        if name == "observers":
            for p in pts:
                if len(p) >= 6 and (p[3] or p[4]):
                    ax.annotate("", xy=(p[0] + p[3] * 0.6, p[1] + p[4] * 0.6),
                                xytext=(p[0], p[1]),
                                arrowprops=dict(arrowstyle="->", color=color, lw=1.5))
    ax.set_aspect("equal")
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.grid(True, ls=":", alpha=0.4)
    ax.set_title("Plan — sensor points + luminaires")
    handles, _ = ax.get_legend_handles_labels()
    if handles:
        ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)


def render_3d(scene, layers, out_path, *, size_in=6.0, dpi=150):
    fig = plt.figure(figsize=(size_in, size_in))
    ax = fig.add_subplot(111, projection="3d")
    zf, zc = scene["z_floor"], scene["z_ceiling"]
    for ring in scene["footprint"]:
        xs = [p[0] for p in ring] + [ring[0][0]]
        ys = [p[1] for p in ring] + [ring[0][1]]
        ax.plot(xs, ys, [zf] * len(xs), color="#888", lw=1.0)
        ax.plot(xs, ys, [zc] * len(xs), color="#bbb", lw=1.0)
        for (x, y) in ring:
            ax.plot([x, x], [y, y], [zf, zc], color="#bbb", lw=0.6)
    for (x0, y0, x1, y1) in scene["luminaires"]:
        quad = [[(x0, y0, zc), (x1, y0, zc), (x1, y1, zc), (x0, y1, zc)]]
        ax.add_collection3d(Poly3DCollection(quad, facecolor=_LUM_FACE,
                                             edgecolor=_LUM_EDGE, alpha=0.85))
    win_label = "window"
    for w in scene["windows"]:
        x0, y0, x1, y1 = w[:4]
        z0, z1 = (w[4], w[5]) if len(w) >= 6 else (zf, zc)
        # Quad spans the glazing's diagonal XY corners (x0,y0)->(x1,y1); exact only for
        # axis-aligned wall openings (one of the XY spans ~0), which wall glazing always is.
        quad = [[(x0, y0, z0), (x1, y1, z0), (x1, y1, z1), (x0, y0, z1)]]
        ax.add_collection3d(Poly3DCollection(quad, facecolor=_WIN, edgecolor=_WIN, alpha=0.3))
        ax.plot([x0, x1], [y0, y1], [z1, z1], color=_WIN, lw=2, label=win_label)
        win_label = None
    for name, pts in layers.items():
        color, marker, label = _STYLE.get(name, ("#333", "o", name))
        ax.scatter([p[0] for p in pts], [p[1] for p in pts],
                   [p[2] if len(p) > 2 else zf for p in pts],
                   c=color, marker=marker, s=35, edgecolors="k", linewidths=0.3, label=label)
        for p in pts:
            if len(p) >= 6 and (p[3] or p[4] or p[5]):
                z = p[2] if len(p) > 2 else zf
                ax.quiver(p[0], p[1], z, p[3], p[4], p[5], length=0.6, color=color, lw=1.2)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_zlabel("Z (m)")
    ax.set_box_aspect(_box_aspect(scene))
    ax.set_title("3D — points at their heights + luminaires")
    # Poly3DCollection luminaires don't register legend handles; add a proxy so they show.
    handles, _ = ax.get_legend_handles_labels()
    if scene["luminaires"]:
        handles.append(Patch(facecolor=_LUM_FACE, edgecolor=_LUM_EDGE, label="luminaire"))
    if handles:
        ax.legend(handles=handles, loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)
