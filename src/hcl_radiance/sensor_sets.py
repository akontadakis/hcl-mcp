"""Named, persistent sensor-point sets. Each set is a .pts file under <work_dir>/sensors/
plus an entry in <work_dir>/sensors/sensors.json. Grid placement reuses en12464_grid."""
import json
import os

from hcl_platform import write_text
from hcl_radiance.commands import pts_to_text
from hcl_radiance.sensor_methodology import en12464_grid


def _dir(work_dir):
    return os.path.join(work_dir, "sensors")


def _registry_path(work_dir):
    return os.path.join(_dir(work_dir), "sensors.json")


def _load(work_dir):
    p = _registry_path(work_dir)
    if not os.path.isfile(p):
        return {}
    with open(p) as fh:
        return json.load(fh)


def _save(work_dir, reg):
    os.makedirs(_dir(work_dir), exist_ok=True)
    with open(_registry_path(work_dir), "w") as fh:
        json.dump(reg, fh, indent=2)


def create_sensor_set(work_dir, name, *, points=None, grid=None, overwrite=False):
    reg = _load(work_dir)
    if name in reg and not overwrite:
        raise ValueError(f"sensor set {name!r} already exists; pass overwrite=True to replace it")
    if grid is not None:
        pts, methodology = en12464_grid(tuple(grid["interior"]), grid["floor_z"],
                                        workplane_h=grid.get("workplane_h", 0.8),
                                        max_spacing=grid.get("max_spacing"))
        source = "grid"
    elif points is not None:
        pts = [[float(c) for c in p] for p in points]
        methodology = {"count": len(pts)}
        source = "explicit"
    else:
        raise ValueError("provide points=[[x,y,z,dx,dy,dz],...] or grid={interior, floor_z, ...}")
    os.makedirs(_dir(work_dir), exist_ok=True)
    path = os.path.join(_dir(work_dir), f"{name}.pts")
    write_text(path, pts_to_text(pts))  # LF: fed to rtrace
    reg[name] = {"path": path, "count": len(pts), "source": source, "methodology": methodology}
    _save(work_dir, reg)
    return {"name": name, "path": path, "count": len(pts), "points": pts,
            "methodology": methodology, "source": source}


def list_sensor_sets(work_dir):
    reg = _load(work_dir)
    return [{"name": k, "path": v["path"], "count": v["count"], "source": v["source"]}
            for k, v in reg.items()]


def get_sensor_set(work_dir, name):
    reg = _load(work_dir)
    if name not in reg:
        raise ValueError(f"sensor set {name!r} not found; available: {sorted(reg)}")
    v = reg[name]
    with open(v["path"]) as fh:
        pts = [[float(x) for x in ln.split()] for ln in fh if ln.strip()]
    return {"name": name, "path": v["path"], "count": v["count"], "source": v["source"],
            "points": pts, "methodology": v.get("methodology", {})}


def delete_sensor_set(work_dir, name):
    reg = _load(work_dir)
    if name not in reg:
        raise ValueError(f"sensor set {name!r} not found; available: {sorted(reg)}")
    path = reg[name]["path"]
    reg.pop(name)
    _save(work_dir, reg)
    if os.path.isfile(path):
        os.remove(path)
    return {"deleted": name}
