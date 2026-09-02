"""Bridge the canonical SpectralSkyRecord into the legacy reconstruction pipeline (Track A).

to_channels() bins the record for colored_sky; to_reference() yields the sky+sun 401-value reference
SPDs for reconstruct_spectrum — replacing the D-series/air-mass templates with physical spectra.
The Radiance transport still provides the per-channel TOTALS; these only supply the reshaping SHAPE.
"""
from dataclasses import asdict, is_dataclass

from hcl_core.spd import bin_average
from hcl_core.spectral_reconstruct import reconstruct_spectrum


def record_to_spd_dict(grid_nm, values):
    """{int_nm: value} from a record component and its grid (caller supplies the 380..780 grid; no range filtering)."""
    return {int(round(w)): v for w, v in zip(grid_nm, values)}


def to_channels(record, channel_type):
    """(diffuse_channels, direct_channels) for colored_sky. 3 or 9 values each, per channel_type."""
    diffuse = bin_average(record_to_spd_dict(record.grid_nm, record.sky_diffuse_horizontal), channel_type)
    direct = bin_average(record_to_spd_dict(record.grid_nm, record.direct_normal), channel_type)
    return diffuse, direct


def to_reference(record):
    """(sky_spd, sun_spd) 401-value reference SPDs for reconstruct_spectrum (sky=diffuse, sun=direct)."""
    return list(record.sky_diffuse_horizontal), list(record.direct_normal)


def reconstruct_from_record(record, sky_channels, sun_channels, channel_type=1, method="reference"):
    """Reconstruct a 401-value spectrum using the record's PHYSICAL sky/sun references (colored sun).

    The Radiance transport supplies sky_channels/sun_channels (per-bin totals); the record supplies the
    reshaping shapes. This replaces the D-series/air-mass templates with physics for this timestep.
    """
    sky_spd, sun_spd = to_reference(record)
    return reconstruct_spectrum(sky_channels, sun_channels, channel_type, method=method,
                                sky_spd=sky_spd, sun_spd=sun_spd, sun_spectral="colored")


def _obj_to_dict(o):
    return asdict(o) if is_dataclass(o) and not isinstance(o, type) else o


def record_to_dict(record):
    """JSON-able view of a SpectralSkyRecord."""
    return {
        "timestamp": list(record.timestamp),
        "broadband": dict(record.broadband),
        "provenance": dict(record.provenance),
        "direct_normal": list(record.direct_normal),
        "sky_diffuse_horizontal": list(record.sky_diffuse_horizontal),
        "atmosphere": _obj_to_dict(getattr(record, "atmosphere", None)),
        "geometry": _obj_to_dict(getattr(record, "geometry", None)),
    }


def emit_spd_set(record, ground=None):
    """CSV: wavelength_nm, direct_normal, sky_diffuse_horizontal[, ground] — 401 rows."""
    header = "wavelength_nm,direct_normal,sky_diffuse_horizontal"
    if ground is not None:
        header += ",ground"
    lines = [header]
    for i in range(len(record.grid_nm)):
        wl = int(round(record.grid_nm[i]))
        # raw float repr (NOT :.6g): this is the lossless 1nm archival form — keep full precision
        row = f"{wl},{record.direct_normal[i]},{record.sky_diffuse_horizontal[i]}"
        if ground is not None:
            row += f",{ground[i]}"
        lines.append(row)
    return "\n".join(lines) + "\n"


# 20-band hcl grid (380–780 @20nm). Exact reconciliation with gensdaymtx WLPART is a Phase-7 task.
BAND_EDGES_20 = [380 + 20 * k for k in range(21)]


def band_average(values_401):
    """Mean of the 1nm values (380..780) within each of the 20 bands."""
    out = []
    for k in range(20):
        lo, hi = BAND_EDGES_20[k] - 380, BAND_EDGES_20[k + 1] - 380
        # last band includes the 780nm endpoint (index 400): the 401st sample folds into band 19 by design
        seg = values_401[lo:hi + 1] if k == 19 else values_401[lo:hi]
        out.append(sum(seg) / len(seg))
    return out


def _band_centers():
    return [(BAND_EDGES_20[k] + BAND_EDGES_20[k + 1]) / 2 for k in range(20)]


def emit_band_matrix(records):
    """Per-record row: month day hour + 20 diffuse band means + 20 direct band means."""
    centers = _band_centers()
    header = "# month day hour | diffuse[" + ",".join(str(c) for c in centers) + "] direct[same]"
    lines = [header]
    for r in records:
        diff = band_average(r.sky_diffuse_horizontal)
        direct = band_average(r.direct_normal)
        m, d, h = r.timestamp
        lines.append(" ".join([str(m), str(d), str(h)]
                              + [f"{v:.6g}" for v in diff] + [f"{v:.6g}" for v in direct]))
    return "\n".join(lines) + "\n"


def emit_spectral_wea(records):
    """.wea-style spectral sky matrix: header + per-record (month day hour + 20 diffuse band means)."""
    lines = ["# spectral .wea (20-band diffuse, 380-780nm @20nm)", f"# records {len(records)}"]
    for r in records:
        m, d, h = r.timestamp
        diff = band_average(r.sky_diffuse_horizontal)
        lines.append(" ".join([str(m), str(d), str(h)] + [f"{v:.6g}" for v in diff]))
    return "\n".join(lines) + "\n"


def emit_augmented_epw_sidecar(records):
    """CSV sidecar (complete archive): month,day,hour, + 401 DIRECT then 401 DIFFUSE values per record.

    An archival sidecar must be lossless, so it carries BOTH components (direct_normal and
    sky_diffuse_horizontal), columns prefixed dir_<nm> / dif_<nm>. (The 20-band .wea above is the
    sky-DIFFUSE matrix by design — the standard daylight-coefficient sky input — and stays diffuse-only.)
    """
    cols = ([f"dir_{380 + i}" for i in range(401)] + [f"dif_{380 + i}" for i in range(401)])
    header = "month,day,hour," + ",".join(cols)
    lines = [header]
    for r in records:
        m, d, h = r.timestamp
        lines.append(",".join([str(m), str(d), str(h)]
                              + [f"{v:.6g}" for v in r.direct_normal]
                              + [f"{v:.6g}" for v in r.sky_diffuse_horizontal]))
    return "\n".join(lines) + "\n"
