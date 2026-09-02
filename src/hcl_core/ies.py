"""IESNA LM-63-1995/2002 parser + photometric analysis. PURE Python, no deps.

Imports nothing from hcl_radiance/hcl_mcp. The parser is whitespace/newline tolerant: after
data line 2 it reads angles + candela as a single flat number stream (LM-63 lets the candela
grid wrap across lines arbitrarily). TILT=INCLUDE consumes its embedded tilt block so the
data-line-1 index does not shift (a naive 'read two lines after TILT=' scanner breaks here).
"""
import math
from dataclasses import dataclass, field, replace


@dataclass
class IESData:
    header: dict = field(default_factory=dict)
    tilt: str = "NONE"
    tilt_block: dict | None = None        # populated (un-applied) for TILT=INCLUDE
    num_lamps: int = 0
    lumens_per_lamp: float = 0.0
    candela_multiplier: float = 1.0
    num_vert_angles: int = 0
    num_horiz_angles: int = 0
    photometric_type: int = 1             # 1=C, 2=B, 3=A
    units_type: int = 2                   # 1=feet, 2=meters
    width: float = 0.0
    length: float = 0.0
    height: float = 0.0
    ballast_factor: float = 1.0
    pfactor: float = 1.0                  # ballast_lamp_photometric_factor (NOT "future_use")
    input_watts: float = 0.0
    vertical_angles: list[float] = field(default_factory=list)
    horizontal_angles: list[float] = field(default_factory=list)
    candela: list[list[float]] = field(default_factory=list)  # candela[num_horiz][num_vert]


def _read_text(text_or_path):
    if "\n" in text_or_path or text_or_path.lstrip().upper().startswith("IESNA"):
        return text_or_path
    with open(text_or_path) as fh:
        return fh.read()


def _numbers(tokens):
    """Yield floats from a token list, raising a structured error on a non-numeric token."""
    for t in tokens:
        try:
            yield float(t)
        except ValueError as exc:
            raise ValueError(f"IES parse error: expected a number, got {t!r}") from exc


def parse_ies(text_or_path):
    """Parse an IESNA LM-63 luminaire into an IESData. Accepts raw text or a file path."""
    text = _read_text(text_or_path)
    lines = [ln.rstrip("\r") for ln in text.split("\n")]

    header = {}
    i = 0
    # Keyword block (everything before the TILT= line).
    while i < len(lines):
        ln = lines[i].strip()
        if ln.upper().startswith("TILT="):
            break
        if ln.startswith("[") and "]" in ln:
            key = ln[1:ln.index("]")].strip()
            val = ln[ln.index("]") + 1:].strip()
            header[key] = val
        i += 1
    if i >= len(lines):
        raise ValueError("IES parse error: no TILT= line found")

    tilt_value = lines[i].strip()[len("TILT="):].strip()
    i += 1
    tilt_block = None
    if tilt_value.upper() == "INCLUDE":
        # Consume the embedded tilt block so data-line-1 indexing does not shift.
        geom = float(lines[i].strip())
        i += 1
        npairs = int(float(lines[i].strip()))
        i += 1
        nums = []
        while len(nums) < 2 * npairs:
            if i >= len(lines):
                raise ValueError("IES parse error: truncated TILT=INCLUDE block")
            nums.extend(float(t) for t in lines[i].split()); i += 1
        angles = nums[:npairs]
        mults = nums[npairs:2 * npairs]
        tilt_block = {"lamp_to_lumin_geometry": geom, "num_tilt_pairs": npairs,
                      "angles": angles, "multipliers": mults}
        tilt = "INCLUDE"
    else:
        tilt = tilt_value  # NONE or a filename (un-applied)

    # Everything from here is a flat whitespace-tolerant number stream.
    stream = []
    for ln in lines[i:]:
        stream.extend(ln.split())
    nums = list(_numbers(stream))
    k = 0

    def take(n):
        nonlocal k
        chunk = nums[k:k + n]
        if len(chunk) < n:
            raise ValueError(f"IES parse error: truncated data (needed {n - len(chunk)} more numbers)")
        k += n
        return chunk

    d1 = take(10)
    num_lamps = int(d1[0])
    lumens_per_lamp = d1[1]
    candela_multiplier = d1[2]
    num_vert = int(d1[3])
    num_horiz = int(d1[4])
    photometric_type = int(d1[5])
    units_type = int(d1[6])
    width, length, height = d1[7], d1[8], d1[9]

    d2 = take(3)
    ballast_factor = d2[0]
    pfactor = d2[1]
    input_watts = d2[2]

    vertical_angles = take(num_vert)
    horizontal_angles = take(num_horiz)
    flat = take(num_vert * num_horiz)
    candela = [flat[h * num_vert:(h + 1) * num_vert] for h in range(num_horiz)]

    return IESData(
        header=header, tilt=tilt, tilt_block=tilt_block,
        num_lamps=num_lamps, lumens_per_lamp=lumens_per_lamp,
        candela_multiplier=candela_multiplier, num_vert_angles=num_vert,
        num_horiz_angles=num_horiz, photometric_type=photometric_type,
        units_type=units_type, width=width, length=length, height=height,
        ballast_factor=ballast_factor, pfactor=pfactor, input_watts=input_watts,
        vertical_angles=vertical_angles, horizontal_angles=horizontal_angles,
        candela=candela,
    )


def _candela_at_vert(ies, v):
    """Mean candela across horizontal planes at vertical angle v (linear interpolation)."""
    va = ies.vertical_angles
    planes = ies.candela
    if v <= va[0]:
        idx = (0, 0, 0.0)
    elif v >= va[-1]:
        idx = (len(va) - 1, len(va) - 1, 0.0)
    else:
        lo = max(j for j in range(len(va)) if va[j] <= v)
        hi = lo + 1
        frac = (v - va[lo]) / (va[hi] - va[lo])
        idx = (lo, hi, frac)
    lo, hi, frac = idx
    vals = [plane[lo] + (plane[hi] - plane[lo]) * frac for plane in planes]
    return sum(vals) / len(vals)


def _full_angle_at_fraction(ies, frac_of_peak):
    """Full vertical angle (deg) spanning candela >= frac_of_peak * peak, in the peak's horiz plane.

    Symmetric one-sided extension: the half-angle is interpolated where the plane crosses the
    threshold; the full angle is 2 * half-angle (matches a luminaire symmetric about nadir).
    """
    # Peak plane = the horizontal plane containing max candela.
    peak = max(max(plane) for plane in ies.candela)
    if peak == 0:
        return 0.0
    thresh = frac_of_peak * peak
    h = max(range(len(ies.candela)), key=lambda j: max(ies.candela[j]))
    plane = ies.candela[h]
    va = ies.vertical_angles
    # Walk outward from the angle of peak until the plane drops below the threshold.
    peak_i = max(range(len(plane)), key=lambda j: plane[j])
    half = va[peak_i]
    for j in range(peak_i, len(plane) - 1):
        c0, c1 = plane[j], plane[j + 1]
        if c0 >= thresh >= c1 and c0 != c1:
            half = va[j] + (c0 - thresh) / (c0 - c1) * (va[j + 1] - va[j])
            break
        else:
            half = va[j + 1]
    half = min(half, 90.0)  # half-angle cannot exceed 90 deg (full cannot exceed 180)
    return 2.0 * half


def _beam_field_reliable(ies):
    """True only when the peak is at nadir and the peak plane is monotonically non-increasing
    outward — the conditions under which the symmetric 2x-half-angle beam/field model is valid.
    Off-nadir (wall-washer) or non-monotonic (batwing) distributions violate it."""
    h = max(range(len(ies.candela)), key=lambda j: max(ies.candela[j]))
    plane = ies.candela[h]
    peak_i = max(range(len(plane)), key=lambda j: plane[j])
    nadir_peaked = (peak_i == 0)
    monotonic = all(plane[j] >= plane[j + 1] for j in range(peak_i, len(plane) - 1))
    return nadir_peaked and monotonic


def analyze_ies(ies):
    """Derived photometrics. Returns a structured report dict.

    Type-C only for beam/field/flux; for type B/A the flux fields are flagged unsupported.
    Absolute photometry (lumens_per_lamp == -1): candela are already absolute luminaire output,
    rated_lumens = integrated zonal flux, LOR = None, never negative.

    Effective candela = raw * candela_multiplier * ballast_factor * pfactor (the same product
    ies2rad applies internally, and what hcl://reference/ies documents). All derived intensities
    and fluxes use the effective grid; rated_lumens is the lamp's rated output (not scaled), so LOR
    correctly reflects effective-output / rated-lamp.
    """
    type_c = (ies.photometric_type == 1)
    absolute = (ies.lumens_per_lamp == -1)

    # Apply the LM-63 intensity multipliers once, then analyse the effective distribution.
    scale = ies.candela_multiplier * ies.ballast_factor * ies.pfactor
    eff = replace(ies, candela=[[c * scale for c in plane] for plane in ies.candela])

    # max candela + location (on the effective grid)
    max_candela = 0.0
    max_at = {"vert": 0.0, "horiz": 0.0}
    for h, plane in enumerate(eff.candela):
        for j, c in enumerate(plane):
            if c > max_candela:
                max_candela = c
                max_at = {"vert": eff.vertical_angles[j], "horiz": eff.horizontal_angles[h]}

    report = {
        "input_watts": ies.input_watts,
        "max_candela": max_candela,
        "max_candela_at": max_at,
        "photometric_type": ies.photometric_type,
        "units_type": ies.units_type,
        "absolute_photometry": absolute,
        "candela_scale_applied": scale,   # candela_multiplier * ballast_factor * pfactor
    }

    if not type_c:
        report.update({
            "flux_supported": False,
            "flux_note": "unsupported photometric type for flux (type B/A); "
                         "the 2*pi*(cos v1 - cos v2) zonal solid angle assumes type C",
            "beam_angle": None, "field_angle": None,
            "beam_field_reliable": None, "beam_field_note": None,
            "flux_azimuth_note": None,
            "flux_down": None, "flux_up": None, "total_flux": None, "LOR": None,
            "rated_lumens": None if absolute else ies.num_lamps * ies.lumens_per_lamp,
            "efficacy": None,
            "flux_down_fraction": None,
            "flux_up_fraction": None,
            "sanity_flux_to_rated_ratio": None,
        })
        return report

    # Zonal flux over the file's ACTUAL vertical extent (effective candela). A zone that straddles
    # the 90deg hemisphere boundary is split at 90 so its flux is apportioned to the correct
    # hemisphere (otherwise the whole zone would follow its midpoint). cos is additive across the
    # split, so total_flux is preserved (and slightly more accurate).
    va = eff.vertical_angles
    flux_down = flux_up = 0.0
    for j in range(len(va) - 1):
        v1, v2 = va[j], va[j + 1]
        segments = [(v1, 90.0), (90.0, v2)] if v1 < 90.0 < v2 else [(v1, v2)]
        for a, b in segments:
            mid = 0.5 * (a + b)
            i_bar = _candela_at_vert(eff, mid)
            dphi = i_bar * 2.0 * math.pi * (math.cos(math.radians(a)) - math.cos(math.radians(b)))
            if mid <= 90.0:
                flux_down += dphi
            else:
                flux_up += dphi
    total_flux = flux_down + flux_up

    if absolute:
        rated_lumens = abs(total_flux)
        lor = None
    else:
        rated_lumens = ies.num_lamps * ies.lumens_per_lamp
        lor = (total_flux / rated_lumens) if rated_lumens else None

    efficacy = (rated_lumens / ies.input_watts) if ies.input_watts else None
    sanity_ratio = (total_flux / rated_lumens) if rated_lumens else None

    # Surface the modelling limitations rather than report confident-but-wrong numbers.
    beam_field_reliable = _beam_field_reliable(eff)
    beam_field_note = None if beam_field_reliable else (
        "beam/field angle assumes a nadir-peaked, monotonic, symmetric lobe (full = 2 x half-angle "
        "from nadir); this distribution is off-nadir and/or non-monotonic (e.g. wall-washer/batwing), "
        "so beam_angle/field_angle are approximate")
    flux_azimuth_note = None if eff.num_horiz_angles <= 1 else (
        "zonal flux averages candela across horizontal planes with a flat mean; for files storing a "
        "partial azimuth (quarter/half) or unequally-spaced planes this is approximate (boundary "
        "planes should be azimuth-weighted)")

    report.update({
        "rated_lumens": rated_lumens,
        "efficacy": efficacy,
        "beam_angle": _full_angle_at_fraction(eff, 0.5),
        "field_angle": _full_angle_at_fraction(eff, 0.1),
        "beam_field_reliable": beam_field_reliable,
        "beam_field_note": beam_field_note,
        "flux_supported": True,
        "flux_note": None,
        "flux_azimuth_note": flux_azimuth_note,
        "flux_down": flux_down,
        "flux_up": flux_up,
        "total_flux": total_flux,
        "LOR": lor,
        "flux_down_fraction": (flux_down / total_flux) if total_flux else None,
        "flux_up_fraction": (flux_up / total_flux) if total_flux else None,
        "sanity_flux_to_rated_ratio": sanity_ratio,
    })
    return report
