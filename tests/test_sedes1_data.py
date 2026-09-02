import csv
import os

from hcl_core import _sedes1_data as S


def _coeff_rows(path):
    """The data rows of a Fig.11 CCM CSV as tuples of stripped string cells
    (rows whose first cell is numeric — skips `# ...` comment/provenance lines
    and any header). String cells lock exact content, including blank B/C fields
    such as the 320 nm row, without float-rounding ambiguity."""
    rows = []
    with open(path, newline="") as fh:
        for row in csv.reader(fh):
            if not row:
                continue
            try:
                float(row[0])
            except ValueError:
                continue  # comment / header line
            rows.append(tuple(c.strip() for c in row))
    return rows


def test_runtime_csv_locked_to_docs_provenance():
    """The bundled runtime coefficients MUST stay identical to the digitized
    provenance in docs/ — re-digitizing one without syncing the other is a drift
    bug this guard catches. (Two copies exist by design: runtime data ships with
    the package; the provenance record lives with the docs.)"""
    runtime = S._CSV  # src/hcl_core/_sedes1_fig11.csv
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    provenance = os.path.join(
        repo_root, "docs", "Coefficient provenance", "fig11_CCM_coefficients.csv"
    )
    assert os.path.exists(provenance), f"provenance CSV missing: {provenance}"

    rt = _coeff_rows(runtime)
    pv = _coeff_rows(provenance)
    assert rt == pv, (
        "runtime _sedes1_fig11.csv has drifted from docs provenance "
        "fig11_CCM_coefficients.csv — re-sync the two copies"
    )
    # sanity: the lock is over real content, not two empty parses
    assert len(rt) > 50
    assert ("400", "1.556", "-2.037", "1.433", "0.116") in rt  # faithful B(400)


def test_faithful_fig11_loaded():
    assert len(S.FIG11_WL) > 50
    assert S.FIG11_WL[0] == 330.0           # B present from 330nm (320 has blank B)
    a, b, c = S.ccm_coeffs(400.0)
    assert abs(a - 1.556) < 0.02
    assert abs(b - (-2.037)) < 0.02         # faithful blue B — NOT the seed's -3.55
    assert abs(c - 1.433) < 0.02
    assert abs(S.ccm_sigma(400.0) - 0.116) < 0.02


def test_faithful_B_blue_negative_but_not_seed_steep():
    _, b4, _ = S.ccm_coeffs(400.0)
    _, b8, _ = S.ccm_coeffs(800.0)
    assert -2.5 < b4 < -1.5                  # faithful blue (the seed was < -3.5)
    assert b8 > b4                           # rises toward 0 in the NIR


def test_blue_exceeds_red_at_overcast_verbatim():
    a4, b4, c4 = S.ccm_coeffs(400.0); blue = a4 + 0.25*b4 + 0.0625*c4
    a7, b7, c7 = S.ccm_coeffs(700.0); red = a7 + 0.25*b7 + 0.0625*c7
    assert blue > red                        # cloud-blueing direction preserved


def test_passthrough_outside_digitized_range():
    assert S.ccm_coeffs(300.0) == (1.0, 0.0, 0.0)
    assert S.ccm_coeffs(2000.0) == (1.0, 0.0, 0.0)
    assert S.ccm_sigma(2000.0) == 0.0


def test_legacy_seed_retained():
    _, b4, _ = S.seed_coeffs(400.0)
    assert abs(b4 - (-3.55)) < 0.01          # the eyeballed seed is still available (for the 'seed' variant)
