"""Klems angle basis: the 145-bin hemispherical discretisation used by BSDF T matrices.

The LBNL "Klems Full" basis is one polar cap plus seven rings, each split into equal
azimuthal patches. Bin order is cap first, then rings outward, azimuth ascending within
each ring -- the order genBSDF and dctimestep both assume.
"""
import math

#: A Klems Full BSDF has exactly this many bins per hemisphere.
KLEMS_FULL_BINS = 145

#: (lower theta, upper theta, centre theta, number of azimuthal patches) per ring,
#: cap first. Taken from a real genBSDF "LBNL/Klems Full" file, NOT reconstructed:
#: the outer two rings are 16 patches over 65-75 deg and 12 over 75-90 deg, which a
#: plausible-looking 8-ring reconstruction ending in a single 28-patch 65-90 ring also
#: sums to 145 while binning every grazing direction wrongly.
KLEMS_ANGLE_BASIS = (
    (0.0, 5.0, 0.0, 1),
    (5.0, 15.0, 10.0, 8),
    (15.0, 25.0, 20.0, 16),
    (25.0, 35.0, 30.0, 20),
    (35.0, 45.0, 40.0, 24),
    (45.0, 55.0, 50.0, 24),
    (55.0, 65.0, 60.0, 24),
    (65.0, 75.0, 70.0, 16),
    (75.0, 90.0, 82.5, 12),
)

#: dctimestep matches the basis by NAME; "Klems Full" alone is not recognised.
KLEMS_BASIS_NAME = "LBNL/Klems Full"

_SUPPORTED_BASES = {"klems full": KLEMS_FULL_BINS}


def klems_bin_count(basis):
    """Bin count for a named angle basis. Only Klems Full is supported."""
    key = str(basis).strip().lower()
    if key not in _SUPPORTED_BASES:
        raise ValueError(
            f"unsupported angle basis {basis!r}; this build supports Klems Full only")
    return _SUPPORTED_BASES[key]


def _angle_basis_xml(indent="\t\t\t"):
    """The <AngleBasis> block, emitted exactly as genBSDF writes it.

    dctimestep resolves the basis by NAME and needs the per-ring blocks present; a
    bare <AngleBasisName>Klems Full</AngleBasisName> with no blocks yields
    "fatal - Memory error: Empty BSDF matrix request" at multiply time.
    """
    lines = [f"{indent}<AngleBasis>",
             f"{indent}\t<AngleBasisName>{KLEMS_BASIS_NAME}</AngleBasisName>"]
    for lower, upper, centre, n_phis in KLEMS_ANGLE_BASIS:
        lines += [
            f"{indent}\t<AngleBasisBlock>",
            f"{indent}\t\t<Theta>{centre:g}</Theta>",
            f"{indent}\t\t<nPhis>{n_phis}</nPhis>",
            f"{indent}\t\t<ThetaBounds>",
            f"{indent}\t\t\t<LowerTheta>{lower:g}</LowerTheta>",
            f"{indent}\t\t\t<UpperTheta>{upper:g}</UpperTheta>",
            f"{indent}\t\t</ThetaBounds>",
            f"{indent}\t</AngleBasisBlock>",
        ]
    lines.append(f"{indent}</AngleBasis>")
    return "\n".join(lines)


def klems_solid_angles():
    """Solid angle (sr) of each of the 145 bins, in basis order. Sums to 2*pi."""
    out = []
    for lower, upper, _centre, n_patches in KLEMS_ANGLE_BASIS:
        ring = 2.0 * math.pi * (math.cos(math.radians(lower)) - math.cos(math.radians(upper)))
        out.extend([ring / n_patches] * n_patches)
    return out


def lm83_default_blind(shade_type=None, *, vlt=None, openness=None, reflectance=None):
    """LM-83 2.2.7's default blind optics, dispatched on SHADE TYPE.

    2.2.7 has three branches and they are not interchangeable:

      - Nothing known, or fabric with unknown VLT: "If the shade VLT is unknown, model
        the shade using 5% diffuse VLT with no specular transmittance."  -> 0.05
      - Fabric with known VLT: "The specular transmittance should be equal to the
        openness factor of the fabric, while the diffuse transmittance should be the
        total visible light transmission (VLT) minus the openness factor. If the VLT is
        known and the openness factor is not known, model the VLT as diffuse
        transmittance only."
      - White louver blinds (>80% reflectance): "use a 20% VLT diffuse distribution",
        depreciating proportionally to a 10% floor for black blinds.

    The 20% figure is gated on the positive fact that the windows HAVE white louver
    blinds of >80% reflectance. Defaulting that reflectance would let the no-knowledge
    case resolve upward to 20%, overstating transmitted flux fourfold, so an undeclared
    reflectance on the louver branch is an error rather than an assumption.
    """
    if shade_type == "louver":
        if reflectance is None:
            raise ValueError(
                "shade_type='louver' needs an explicit reflectance: LM-83 2.2.7 gates the "
                "20% VLT default on white louver blinds of >80% reflectance and depreciates "
                "darker colours to a 10% floor. Omit shade_type for the 5% unknown-shade "
                "default instead.")
        r = max(0.0, min(1.0, float(reflectance)))
        d = 0.20 if r >= 0.80 else 0.10 + (0.20 - 0.10) * (r / 0.80)
        return {"diffuse_vlt": d, "specular": 0.0, "source": "lm83_2_2_7_white_louver"}
    if shade_type == "fabric" and vlt is not None:
        v = float(vlt)
        if openness is None:
            return {"diffuse_vlt": v, "specular": 0.0,
                    "source": "lm83_2_2_7_fabric_vlt_only"}
        o = float(openness)
        if o > v:
            raise ValueError(
                f"openness factor {o:g} exceeds the shade VLT {v:g}; 2.2.7 defines the "
                "diffuse component as VLT minus openness, which would be negative")
        return {"diffuse_vlt": v - o, "specular": o,
                "source": "lm83_2_2_7_fabric_with_openness"}
    return {"diffuse_vlt": 0.05, "specular": 0.0,
            "source": "lm83_2_2_7_unknown_shade"}


def uniform_diffuse_tmatrix(vlt, *, specular=0.0):
    """A 145x145 Klems T matrix: uniform diffuse transmission, optional specular peak.

    Each incident bin scatters uniformly over the outgoing hemisphere, so every entry is
    vlt / (2*pi) -- a radiance per unit incident flux, integrating back to `vlt` when
    weighted by bin solid angles.

    `specular` adds a forward peak on the diagonal (outgoing bin = incident bin), which
    is how a fabric shade's openness factor transmits DIRECT BEAM. With specular=0 the
    blind is opaque to the beam, which is 2.2.7's "no specular transmittance" default.
    The row then integrates to vlt + specular, so callers pass the DIFFUSE component as
    `vlt` and the openness factor as `specular` for a total of the shade's true VLT.
    """
    v = float(vlt)
    if not 0.0 <= v <= 1.0:
        raise ValueError(f"vlt must be within 0..1, got {vlt}")
    s = float(specular)
    if not 0.0 <= s <= 1.0:
        raise ValueError(f"specular must be within 0..1, got {specular}")
    base = v / (2.0 * math.pi)
    omega = klems_solid_angles()
    matrix = [[base] * KLEMS_FULL_BINS for _ in range(KLEMS_FULL_BINS)]
    if s > 0.0:
        for i in range(KLEMS_FULL_BINS):
            matrix[i][i] += s / omega[i]
    return matrix


def clear_glazing_tmatrix(tvis):
    """T matrix for plain glazing -- the 'blinds open' state.

    Modelled as diffuse at the same total transmittance rather than as a specular delta.
    Within three-phase this is the standard Klems treatment: the basis cannot resolve a
    beam narrower than one bin, so a specular spike would land wholly in one bin and
    mis-place direct sun. LM-83's direct-sun quantities come from the separate
    zero-bounce pass, not from this matrix, so the approximation affects only the
    ambient term -- which is what V.T.D.s computes.

    Carries no angular dependence, which 2.2.9 and the 2.2.6 glossary's "angular
    effects" would require: a recorded departure, not an oversight.
    """
    return uniform_diffuse_tmatrix(tvis)


_XML_HEAD = """<?xml version="1.0" encoding="UTF-8"?>
<WindowElement xmlns="http://windows.lbl.gov" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://windows.lbl.gov/BSDF-v1.4.xsd">
<WindowElementType>System</WindowElementType>
<FileType>BSDF</FileType>
<Optical>
<Layer>
\t<Material>
\t\t<Name>{name}</Name>
\t\t<Manufacturer>hcl-mcp</Manufacturer>
\t\t<DeviceType>Other</DeviceType>
\t</Material>
\t<DataDefinition>
\t\t<IncidentDataStructure>Columns</IncidentDataStructure>
{basis}
\t</DataDefinition>
"""

_XML_BLOCK = """\t<WavelengthData>
\t\t<LayerNumber>System</LayerNumber>
\t\t<Wavelength unit="Integral">Visible</Wavelength>
\t\t<SourceSpectrum>CIE Illuminant D65 1nm.ssp</SourceSpectrum>
\t\t<DetectorSpectrum>ASTM E308 1931 Y.dsp</DetectorSpectrum>
\t\t<WavelengthDataBlock>
\t\t\t<WavelengthDataDirection>{direction}</WavelengthDataDirection>
\t\t\t<ColumnAngleBasis>{basis_name}</ColumnAngleBasis>
\t\t\t<RowAngleBasis>{basis_name}</RowAngleBasis>
\t\t\t<ScatteringDataType>BTDF</ScatteringDataType>
\t\t\t<ScatteringData>
{data}
\t\t\t</ScatteringData>
\t\t</WavelengthDataBlock>
\t</WavelengthData>
"""

_XML_TAIL = """</Layer>
</Optical>
</WindowElement>
"""


def _data_rows(matrix):
    rows = []
    for i, row in enumerate(matrix):
        if len(row) != KLEMS_FULL_BINS:
            raise ValueError(f"row {i} has {len(row)} columns, expected {KLEMS_FULL_BINS}")
        rows.append(",".join(f"{v:.6g}" for v in row) + ",")
    return "\n".join(rows)


def write_klems_xml(matrix, path, *, name, reflectance=0.0):
    """Write a Klems BTDF matrix as the LBNL WindowElement XML dctimestep reads.

    dctimestep needs the transmission block AND both reflection blocks: a file carrying
    only "Transmission Front" is accepted by an XML parser but rejected at multiply time.
    Reflection defaults to a uniform `reflectance`, which for a shade is a reasonable
    stand-in and for clear glazing is near enough zero.
    """
    import os
    if len(matrix) != KLEMS_FULL_BINS:
        raise ValueError(f"expected {KLEMS_FULL_BINS} rows, got {len(matrix)}")
    refl = [[float(reflectance) / (2.0 * math.pi)] * KLEMS_FULL_BINS
            for _ in range(KLEMS_FULL_BINS)]
    trans_rows = _data_rows(matrix)
    refl_rows = _data_rows(refl)
    parts = [_XML_HEAD.format(name=name, basis=_angle_basis_xml())]
    for direction, rows in (("Transmission Front", trans_rows),
                            ("Reflection Front", refl_rows),
                            ("Reflection Back", refl_rows)):
        parts.append(_XML_BLOCK.format(direction=direction,
                                       basis_name=KLEMS_BASIS_NAME, data=rows))
    parts.append(_XML_TAIL)
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write("".join(parts))
    return path
