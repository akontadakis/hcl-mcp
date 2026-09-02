"""P3 gates. Each returns its tallies; tests assert the COUNTS, not just that it passed.

A sweep that silently corrects zero files must fail, so every gate here reports how
much it actually examined.
"""
import ast
import os
import pathlib

import pytest

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"

# sky.py and server.py document the EAST-POSITIVE longitude sign convention with
# "Athens = 23.73" as the worked example — the public IWEC weather file's city, not a
# measured site. A find-and-replace on the number would damage the convention docs
# while fixing nothing. Whitelisted BY LOCATION so a real site claim elsewhere still fails.
LONGITUDE_CONVENTION_SITES = {
    ("hcl_radiance/sky.py", 49),
    ("hcl_radiance/sky.py", 155),
    ("hcl_mcp/server.py", 338),
}


def p3_g1_no_falsified_vt(src=SRC):
    """0.744 appears as a numeric literal in no module under src/."""
    hits = []
    files = sorted(src.rglob("*.py"))
    if not files:
        raise SystemExit("P3-G1: no source files found - measured nothing")
    for path in files:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Constant) and node.value == 0.744:
                hits.append(f"{path.relative_to(src)}:{node.lineno}")
    if hits:
        raise SystemExit(f"P3-G1: the falsified VT 0.744 survives at {hits}")
    return {"n_files_scanned": len(files), "n_hits": 0}


def test_p3_g1_passes_on_the_shipped_tree():
    tally = p3_g1_no_falsified_vt()
    assert tally["n_hits"] == 0
    assert tally["n_files_scanned"] > 20, "gate scanned implausibly few files"


def test_p3_g1_refuses_an_empty_tree(tmp_path):
    with pytest.raises(SystemExit, match="measured nothing"):
        p3_g1_no_falsified_vt(tmp_path)


def test_p3_g1_catches_a_reintroduced_constant(tmp_path):
    (tmp_path / "m.py").write_text("TARGET_VT = 0.744\n")
    with pytest.raises(SystemExit, match="falsified VT 0.744 survives"):
        p3_g1_no_falsified_vt(tmp_path)


CLEARSKY_K = SRC / "hcl_core" / "_clearsky_K_spectrl2.csv"
CLEARSKY_BIAS = SRC / "hcl_core" / "clearsky_bias.py"


def p3_g2_no_deconfound_provenance(k_csv=CLEARSKY_K, bias_py=CLEARSKY_BIAS):
    """K and its provenance no longer claim a deconfound that does not occur.

    The old artifact's own header read "deconfounded (double-Low-E)" and the module
    emitted `"glazing_assumed": "lowE_double"`. Both describe an operation that is
    now known not to apply - the source readings are exterior. The key must be GONE,
    not relabelled: a corrected string describing a retired operation is still a
    claim about something that did not happen.
    """
    if not k_csv.is_file():
        raise SystemExit(f"P3-G2: {k_csv} missing - measured nothing")
    header = "".join(l for l in k_csv.read_text().splitlines() if l.startswith("#")).lower()
    for token in ("deconfound", "low-e", "lowe", "low_e"):
        if token in header:
            raise SystemExit(
                f"P3-G2: the K artifact header still claims {token!r} - the source "
                f"readings never crossed glazing, so no glazing division applies")
    bias = bias_py.read_text()
    if "glazing_assumed" in bias:
        raise SystemExit(
            "P3-G2: clearsky_bias still emits `glazing_assumed` - the key must be "
            "removed, not relabelled; no glazing is assumed any more")
    n_rows = sum(1 for l in k_csv.read_text().splitlines()
                 if l.strip() and not l.startswith("#") and not l.startswith("wavelength"))
    if n_rows < 100:
        raise SystemExit(f"P3-G2: K artifact has {n_rows} rows - implausibly few")
    return {"n_k_rows": n_rows, "glazing_assumed_present": False}


def test_p3_g2_passes_on_the_shipped_tree():
    tally = p3_g2_no_deconfound_provenance()
    assert tally["n_k_rows"] >= 100
    assert tally["glazing_assumed_present"] is False


def test_p3_g2_catches_a_surviving_glazing_claim(tmp_path):
    k = tmp_path / "k.csv"
    k.write_text("# clean header\nwavelength_nm,k\n" + "".join(
        f"{w},1.0\n" for w in range(380, 781)))
    bias = tmp_path / "b.py"
    bias.write_text('return {"glazing_assumed": "lowE_double"}\n')
    with pytest.raises(SystemExit, match="glazing_assumed"):
        p3_g2_no_deconfound_provenance(k, bias)


def test_p3_g2_catches_a_deconfound_header(tmp_path):
    k = tmp_path / "k.csv"
    k.write_text("# Derived: deconfounded (double-Low-E) clear exterior\nwavelength_nm,k\n"
                 + "".join(f"{w},1.0\n" for w in range(380, 781)))
    bias = tmp_path / "b.py"
    bias.write_text("clean\n")
    with pytest.raises(SystemExit, match="still claims"):
        p3_g2_no_deconfound_provenance(k, bias)


def test_p3_g2_refuses_a_missing_artifact(tmp_path):
    with pytest.raises(SystemExit, match="measured nothing"):
        p3_g2_no_deconfound_provenance(tmp_path / "nope.csv", tmp_path / "b.py")


def _read_k_curve(k_csv):
    """{wavelength_nm: k} from the artifact, tolerant of a quoted-comment header.

    The superseded artifact wrote its comment lines quoted; the shipped one does not.
    Both must parse, because this gate's whole job is to tell them apart.
    """
    curve = {}
    for line in k_csv.read_text().splitlines():
        line = line.strip().strip('"')
        if not line or line.startswith("#") or line.lower().startswith("wavelength"):
            continue
        parts = line.split(",")
        try:
            curve[int(parts[0])] = float(parts[1])
        except (ValueError, IndexError):
            continue
    return curve


# The shipped K is a RAW (unsmoothed, un-rescaled) curve rising steeply from the blue
# to the red. The two regressions this gate exists to catch are:
#
#   1. K flattened to all-1.0 - the correction silently becomes a no-op;
#   2. the SUPERSEDED (glazing-divided, falsified) curve restored under the corrected
#      header - P3-G2 checks only the header STRING, so that mutation passes it.
#
# Both are caught by anchors on quantities the header itself documents, not by an
# opaque hash: the blue/red tilt (header line "0.3709"), the endpoint ratio, and the
# absence of the superseded artifact's mean-1 rescale.
#
#   quantity                      shipped    2026-08-04    superseded    all-1.0
#   mean K                        1.2208     1.4308        1.0000        1.0000
#   tilt = <K,400-500>/<K,600-700> 0.5367    0.3709        0.7039        1.0000
#   K(780)/K(380)                 5.63       10.13         3.33          1.0000
#
# The shipped curve is fitted against the clear engine (Kt = 0.70 triple), not against
# SPECTRL2 driven through the cloud bridge at a unit irradiance triple.
#
# IF K IS LEGITIMATELY RE-DERIVED: these bounds are deliberately loose (roughly +-15 %
# around the shipped values), so an honest re-derivation from more or better rows should
# pass unchanged. If it does not, that is the gate asking you to confirm the new curve is
# still raw, still un-rescaled and still blue-suppressing - then update BOTH the numbers
# below and the header comment in _clearsky_K_spectrl2.csv, in the same commit.
K_TILT_SHIPPED = 0.5367
K_ENDPOINT_RATIO_SHIPPED = 5.6264
K_MEAN_SHIPPED = 1.2208


def p3_g2b_k_artifact_is_the_rederived_curve(k_csv=CLEARSKY_K):
    """The shipped K VALUES are the re-derived ones, not a no-op and not the superseded curve.

    P3-G2 gates the provenance STRING. A header can be corrected while the numbers
    underneath it are the falsified ones, which is exactly the regression P3 exists to
    prevent, so the numbers need their own gate. Anchors, not a checksum: a hash fails
    opaquely on any legitimate re-derivation, whereas these say which property broke.
    """
    if not k_csv.is_file():
        raise SystemExit(f"P3-G2b: {k_csv} missing - measured nothing")
    curve = _read_k_curve(k_csv)
    if len(curve) < 100:
        raise SystemExit(f"P3-G2b: K artifact parsed {len(curve)} rows - implausibly few")
    for edge in (380, 780):
        if edge not in curve:
            raise SystemExit(f"P3-G2b: K artifact has no {edge} nm row - shape is wrong")

    def band(lo, hi):
        vals = [curve[w] for w in range(lo, hi + 1) if w in curve]
        return sum(vals) / len(vals)

    mean_k = sum(curve.values()) / len(curve)
    tilt = band(400, 500) / band(600, 700)
    endpoint_ratio = curve[780] / curve[380]

    if abs(mean_k - 1.0) < 1e-6:
        raise SystemExit(
            f"P3-G2b: mean K is {mean_k:.6f} - the shipped curve is RAW and NOT rescaled "
            f"to mean 1. A mean of exactly 1 is the superseded artifact's normalisation "
            f"(or an all-1.0 no-op). Expected mean near {K_MEAN_SHIPPED}.")
    if not 0.456 <= tilt <= 0.617:
        raise SystemExit(
            f"P3-G2b: blue/red tilt is {tilt:.4f}, expected near {K_TILT_SHIPPED} "
            f"(the value the artifact header documents). The superseded glazing-divided "
            f"curve tilts 0.7039, the 2026-08-04 unit-triple curve 0.3709, and a flat K 1.0 - this K is neither re-derived "
            f"nor blue-suppressing enough to be the shipped one.")
    if not 4.78 <= endpoint_ratio <= 6.47:
        raise SystemExit(
            f"P3-G2b: K(780)/K(380) is {endpoint_ratio:.4f}, expected near "
            f"{K_ENDPOINT_RATIO_SHIPPED}. The superseded curve spans 3.33, the 2026-08-04 curve 10.13, and a flat K "
            f"spans 1.0.")
    return {"n_k_rows": len(curve), "mean_k": mean_k, "tilt": tilt,
            "endpoint_ratio": endpoint_ratio}


def test_p3_g2b_passes_on_the_shipped_artifact():
    tally = p3_g2b_k_artifact_is_the_rederived_curve()
    assert tally["n_k_rows"] == 401
    assert tally["tilt"] == pytest.approx(K_TILT_SHIPPED, abs=0.005)
    assert tally["endpoint_ratio"] == pytest.approx(K_ENDPOINT_RATIO_SHIPPED, abs=0.2)
    assert tally["mean_k"] == pytest.approx(K_MEAN_SHIPPED, abs=0.01)


def test_p3_g2b_kills_an_all_ones_k(tmp_path):
    k = tmp_path / "k.csv"
    k.write_text("# clean header\nwavelength_nm,k\n"
                 + "".join(f"{w},1.0\n" for w in range(380, 781)))
    with pytest.raises(SystemExit, match="RAW and NOT rescaled"):
        p3_g2b_k_artifact_is_the_rederived_curve(k)


def test_p3_g2b_kills_the_superseded_curve_under_a_clean_header(tmp_path):
    """The named regression: falsified VALUES under the corrected HEADER.

    Built from the real superseded artifact recovered from git (eb73789), not a
    synthetic stand-in - a synthetic curve can pass a gate the real one would fail.
    """
    import subprocess
    repo = pathlib.Path(__file__).resolve().parents[1]
    old = subprocess.run(
        ["git", "show", "eb73789:src/hcl_core/_clearsky_K_spectrl2.csv"],
        cwd=repo, capture_output=True, text=True)
    if old.returncode != 0:
        pytest.skip("superseded artifact not reachable in this checkout")
    body = [l for l in old.stdout.splitlines()
            if not l.strip().strip('"').startswith("#")]
    k = tmp_path / "k.csv"
    k.write_text("# Derived: measured clear readings vs SPECTRL2 clear.\n"
                 "# NO glazing division.\n" + "\n".join(body) + "\n")
    with pytest.raises(SystemExit) as e:
        p3_g2b_k_artifact_is_the_rederived_curve(k)
    assert "RAW and NOT rescaled" in str(e.value) or "tilt" in str(e.value)


def test_p3_g2b_refuses_a_missing_artifact(tmp_path):
    with pytest.raises(SystemExit, match="measured nothing"):
        p3_g2b_k_artifact_is_the_rederived_curve(tmp_path / "nope.csv")


def _module_graph(src=SRC):
    """{module: (path, {imported hcl_* modules})} by AST, not by importing anything.

    The path is carried rather than reconstructed from the module name: a package
    `__init__.py` maps to the bare package name, whose reconstructed `<pkg>.py` does
    not exist on disk. Reconstructing would crash the gate on any tree with packages
    in it - which is every real tree - so the gate would never measure anything.
    """
    graph = {}
    for path in sorted(src.rglob("*.py")):
        mod = str(path.relative_to(src)).replace("/", ".")[:-3].replace(".__init__", "")
        pkg = mod.rsplit(".", 1)[0] if "." in mod else mod
        deps = set()
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.level:
                # `from . import sky_radiance` / `from .receiver import x` carry level>0 and
                # often module=None, so the absolute branch below never sees them. Resolve
                # against the containing package, else a relative-import style spreading
                # through src/ would silently erase edges from the reachability walk.
                base = pkg
                for _ in range(node.level - 1):
                    base = base.rsplit(".", 1)[0] if "." in base else base
                base = base + "." + node.module if node.module else base
                if base.startswith("hcl_"):
                    deps.add(base)
                    for a in node.names:
                        deps.add(base + "." + a.name)
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("hcl_"):
                # `from hcl_core import sky_radiance` records module="hcl_core" and the
                # SUBMODULE as a name. Recording only node.module would make every edge
                # point at the bare package, and a frontier seeded with dotted module
                # names would match nothing -- the reachability walk would return 0 on
                # every tree, including one where the server imports eta directly.
                deps.add(node.module)
                for a in node.names:
                    deps.add(node.module + "." + a.name)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.startswith("hcl_"):
                        deps.add(a.name)
        graph[mod] = (path, deps)
    return graph


CLEARSKY_CLASS = "ClearSkyBiasCorrection"


def _clearsky_enabled_default(bias_py):
    """The literal default of ClearSkyBiasCorrection.__init__'s `enabled` parameter.

    Parsed, never grepped. A substring scan for "enabled=False" over this file passes on
    the MODULE DOCSTRING, which contains the phrase `enabled=False` by default - so the
    real signature could read `enabled=True` and the scan would still see what it wanted.
    Verified: flipping the actual default in src/hcl_core/clearsky_bias.py left the
    grep-based check green, i.e. it asserted nothing about the thing it named.

    Returns the default value, or a string describing why it could not be established -
    never None-as-success, so an unreadable signature fails loudly instead of passing.
    """
    if not bias_py.is_file():
        raise SystemExit(f"P3-G3: {bias_py} missing - measured nothing")
    for node in ast.walk(ast.parse(bias_py.read_text())):
        if not (isinstance(node, ast.ClassDef) and node.name == CLEARSKY_CLASS):
            continue
        for item in node.body:
            if not (isinstance(item, ast.FunctionDef) and item.name == "__init__"):
                continue
            args = item.args.args[1:]                      # drop self
            defaults = item.args.defaults
            # defaults align to the TAIL of the positional args
            offset = len(args) - len(defaults)
            for i, a in enumerate(args):
                if a.arg != "enabled":
                    continue
                if i < offset:
                    return "<required, no default>"
                d = defaults[i - offset]
                return d.value if isinstance(d, ast.Constant) else "<not a literal>"
            for kw, d in zip(item.args.kwonlyargs, item.args.kw_defaults):
                if kw.arg == "enabled":
                    return d.value if isinstance(d, ast.Constant) else "<not a literal>"
            return "<no `enabled` parameter>"
        return "<no __init__>"
    return f"<no class {CLEARSKY_CLASS}>"


def _enables_clearsky(path):
    """True if this module constructs ClearSkyBiasCorrection with enabled truthy.

    Parsed rather than matched against the exact source text `...(enabled=True)`, which
    misses every realistic spelling: `enabled = True` (spaces), the positional
    `ClearSkyBiasCorrection("spectrl2", True)`, and any call split across lines.
    """
    for node in ast.walk(ast.parse(path.read_text())):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
        if name != CLEARSKY_CLASS:
            continue
        for kw in node.keywords:
            if kw.arg == "enabled" and isinstance(kw.value, ast.Constant) and kw.value.value:
                return True
            if kw.arg is None:                             # **kwargs - cannot rule it out
                return True
        # positional: __init__(self, engine_name, enabled) -> enabled is the 2nd argument
        if len(node.args) >= 2:
            a = node.args[1]
            if not isinstance(a, ast.Constant) or a.value:
                return True
    return False


def p3_g3_blast_radius_unchanged(src=SRC):
    """The two facts that make P3's exposure LOW, asserted so they cannot rot silently.

    Both were measured, not assumed: the clear-sky correction defaults off and no
    production call site enables it, and the eta path is not reachable from the shipped
    server. If a later change wires either in, this gate fails and the blast radius gets
    re-assessed rather than quietly widening.
    """
    graph = _module_graph(src)
    if not graph:
        raise SystemExit("P3-G3: empty module graph - measured nothing")

    default = _clearsky_enabled_default(src / "hcl_core" / "clearsky_bias.py")
    if default is not False:
        raise SystemExit(
            f"P3-G3: ClearSkyBiasCorrection defaults enabled={default!r}, not False - the "
            "correction would apply silently, which its own docstring forbids")

    enablers = sorted(m for m, (path, _) in graph.items() if _enables_clearsky(path))
    if enablers:
        raise SystemExit(
            f"P3-G3: {enablers} construct the correction enabled - re-assess the blast "
            f"radius before shipping a re-derived K")

    reach, frontier = set(), {"hcl_core.sky_radiance", "hcl_core.receiver"}
    while frontier:
        nxt = set()
        for mod, (_, deps) in graph.items():
            if mod not in reach and deps & frontier:
                reach.add(mod); nxt.add(mod)
        frontier = nxt
    if "hcl_mcp.server" in reach:
        raise SystemExit(
            "P3-G3: hcl_mcp.server now reaches sky_radiance/receiver - eta became a "
            "live server constant; re-assess the blast radius")
    return {"n_modules": len(graph), "n_reaching_eta": len(reach),
            "server_reaches_eta": False, "n_enablers": 0}


def test_p3_g3_passes_on_the_shipped_tree():
    tally = p3_g3_blast_radius_unchanged()
    assert tally["server_reaches_eta"] is False
    assert tally["n_enablers"] == 0
    assert tally["n_modules"] > 20
    # Exactly the mutual pair receiver <-> sky_radiance and nothing else. Asserting the
    # COUNT, not just the server fact: a reachability walk that silently returns 0 would
    # satisfy `server_reaches_eta is False` while measuring nothing at all.
    assert tally["n_reaching_eta"] == 2


def test_p3_g3_reads_the_real_signature_not_the_docstring(tmp_path):
    """The regression that shipped: a grep for "enabled=False" hit the module docstring.

    This file reproduces the real one's shape - a docstring mentioning `enabled=False`
    above a signature that says otherwise. A substring scan passes it; the gate must not.
    """
    src = tmp_path / "src"
    (src / "hcl_core").mkdir(parents=True)
    (src / "hcl_core" / "clearsky_bias.py").write_text(
        '"""Never silently on: `enabled=False` by default."""\n'
        "class ClearSkyBiasCorrection:\n"
        '    def __init__(self, engine_name="spectrl2", enabled=True):\n'
        "        pass\n")
    assert _clearsky_enabled_default(src / "hcl_core" / "clearsky_bias.py") is True
    with pytest.raises(SystemExit, match="defaults enabled=True, not False"):
        p3_g3_blast_radius_unchanged(src)


def test_p3_g3_default_check_reads_the_shipped_file():
    """Belt and braces: the real signature parses to literally False, class/init present."""
    assert _clearsky_enabled_default(SRC / "hcl_core" / "clearsky_bias.py") is False


@pytest.mark.parametrize("call", [
    'ClearSkyBiasCorrection(enabled=True)',
    'ClearSkyBiasCorrection(enabled = True)',
    'ClearSkyBiasCorrection("spectrl2", True)',
    'ClearSkyBiasCorrection(\n    engine_name="spectrl2",\n    enabled=True,\n)',
    'bias.ClearSkyBiasCorrection(enabled=True)',
])
def test_p3_g3_enabler_scan_catches_realistic_spellings(tmp_path, call):
    """The literal-substring scan only caught the first of these."""
    m = tmp_path / "m.py"
    m.write_text("x = " + call + "\n")
    assert _enables_clearsky(m) is True


@pytest.mark.parametrize("call", [
    'ClearSkyBiasCorrection()',
    'ClearSkyBiasCorrection(enabled=False)',
    'ClearSkyBiasCorrection("spectrl2", False)',
    'SomethingElse(enabled=True)',
])
def test_p3_g3_enabler_scan_does_not_cry_wolf(tmp_path, call):
    m = tmp_path / "m.py"
    m.write_text("x = " + call + "\n")
    assert _enables_clearsky(m) is False


def test_p3_g3_reachability_walk_sees_relative_imports(tmp_path):
    """`from . import sky_radiance` must create an edge, or the walk silently loses it."""
    src = tmp_path / "src"
    (src / "hcl_core").mkdir(parents=True)
    (src / "hcl_mcp").mkdir(parents=True)
    (src / "hcl_core" / "clearsky_bias.py").write_text(
        "class ClearSkyBiasCorrection:\n    def __init__(self, enabled=False):\n        pass\n")
    (src / "hcl_core" / "sky_radiance.py").write_text("x = 1\n")
    (src / "hcl_core" / "receiver.py").write_text("from . import sky_radiance\n")
    (src / "hcl_mcp" / "server.py").write_text("x = 1\n")
    assert p3_g3_blast_radius_unchanged(src)["n_reaching_eta"] == 1
    (src / "hcl_mcp" / "server.py").write_text("from hcl_core.receiver import oriented\n")
    with pytest.raises(SystemExit, match="now reaches sky_radiance/receiver"):
        p3_g3_blast_radius_unchanged(src)


def test_p3_g3_reachability_walk_is_not_vacuous(tmp_path):
    """A walk that always returns 0 would pass the shipped-tree test for the wrong reason."""
    src = tmp_path / "src"
    (src / "hcl_core").mkdir(parents=True)
    (src / "hcl_mcp").mkdir(parents=True)
    (src / "hcl_core" / "clearsky_bias.py").write_text(
        "class ClearSkyBiasCorrection:\n    def __init__(self, enabled=False):\n        pass\n")
    (src / "hcl_core" / "sky_radiance.py").write_text("x = 1\n")
    (src / "hcl_core" / "receiver.py").write_text("from hcl_core import sky_radiance\n")
    (src / "hcl_mcp" / "server.py").write_text("x = 1\n")
    assert p3_g3_blast_radius_unchanged(src)["n_reaching_eta"] == 1
    # the codebase's own import style -- `from pkg import submodule` -- must be seen
    (src / "hcl_mcp" / "server.py").write_text("from hcl_core import receiver\n")
    with pytest.raises(SystemExit, match="now reaches sky_radiance/receiver"):
        p3_g3_blast_radius_unchanged(src)


def test_p3_g3_refuses_an_empty_tree(tmp_path):
    with pytest.raises(SystemExit, match="measured nothing"):
        p3_g3_blast_radius_unchanged(tmp_path)


# P3-G4 (the ERRATA completeness gate) lives outside this tree, together with the
# document it checks. It still RAISES on a missing file — it was relocated, not
# softened into a skip.


ROOT = SRC.parent

# Docs P3-G5 sweeps, split by whether git actually carries them.
#
# Names are REPO-ROOT-RELATIVE, not docs/-relative. README.md lives at the repo root and
# is one of the swept docs; spelling it "../README.md" against a docs/ base would work by
# accident and would break the moment the base changed, so the base is the repo root and
# every entry says where it actually is.
#
# TRACKED: present in every checkout, so their absence is a real defect (someone
# deleted or renamed a doc without updating this list) and the gate hard-fails.
#
# UNTRACKED: matched by the `/docs/*` rule in .gitignore, which deliberately keeps
# paywalled and draft material out of the repo. They exist in the author's
# working tree but NOT in a fresh clone or in CI. The gate therefore checks them when
# present and REPORTS them as unchecked when absent - it must never hard-fail on their
# absence (that made CI red on every clone) and must never silently count an absent
# file as clean.
TRACKED_SWEPT_DOCS = (
    "docs/technical-reference.md", "docs/hcl-methodology.md",
    "docs/spectral-sky-as-built.md",
    # swept in 655f921; listable only once the ERRATA exemption became proximity-scoped,
    # because under the document-wide exemption listing them registered coverage this
    # gate could not actually provide
    "docs/operating-guide.md", "docs/recalibrating-cloud-ccm.md",
    "docs/spectral-sky-methodology.md", "README.md",
    # the fourth spectral-engine doc. Clean by authorship since P3, but it was outside the
    # sweep list entirely, so nothing stopped a retired claim reappearing in it.
    "docs/spectral-engine-comparison.md",
    "docs/spectral-engine-validation.md",
    "docs/spectral-engine-radiance-deep-dive.md",
)
# Extra local-only documents to sweep — drafts the `/docs/*` rule keeps out of git.
# Colon-separated repo-relative paths in $HCL_EXTRA_SWEPT_DOCS. EMPTY by default: a
# published checkout has none, and their filenames are deliberately not recorded here.
UNTRACKED_SWEPT_DOCS = tuple(
    x for x in os.environ.get("HCL_EXTRA_SWEPT_DOCS", "").split(os.pathsep) if x)
SWEPT_DOCS = TRACKED_SWEPT_DOCS + UNTRACKED_SWEPT_DOCS

# A stand-in used by the tests below, so the untracked-doc machinery is exercised even
# when $HCL_EXTRA_SWEPT_DOCS is unset.
_SYNTHETIC_UNTRACKED = ("docs/_local-draft.md",)

FALSIFIED_TOKENS = ("0.744", "74.4", "low-e")


def _paragraphs(text):
    """(start_line, block_text) for each blank-line-delimited block, 1-indexed.

    The unit of exemption. A fixed line window was the alternative and is wrong for
    these docs: the ERRATA pointers are admonition blocks (`> **⚠️ ERRATA ...**`) that run
    five or six lines, markdown tables put a whole phase log in one block, and several
    claims sit on single unwrapped lines hundreds of characters long. Any fixed N is
    either too tight for the tables or loose enough to reach a pointer under a different
    heading - a paragraph is the unit the author actually writes in.
    """
    blocks, cur, start = [], [], 1
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            if cur:
                blocks.append((start, "\n".join(cur)))
                cur = []
        else:
            if not cur:
                start = i
            cur.append(line)
    if cur:
        blocks.append((start, "\n".join(cur)))
    return blocks


def p3_g5_no_falsified_claim_in_docs(root=ROOT, tracked=TRACKED_SWEPT_DOCS,
                                     untracked=UNTRACKED_SWEPT_DOCS):
    """No swept doc states the falsified glazing claim without an ERRATA pointer BESIDE it.

    THE EXEMPTION IS PARAGRAPH-SCOPED, and that is the whole point of this gate. It used
    to read `if token in text and "errata" not in text`, evaluated over the WHOLE
    document. Every swept doc now contains the word ERRATA somewhere - that is exactly
    what the P3 sweep added - so every doc was unconditionally exempt from every token,
    permanently. Verified: seeding `Low-E ... VT 74.4 %` into tracked
    docs/technical-reference.md left the gate green.

    A token is now exempt only when "errata" appears in the SAME blank-line-delimited
    paragraph. That is the unit the pointers are written in: `> **⚠️ ERRATA ...**`
    admonition blocks, table rows carrying an inline "See ERRATA 1-2", and the long
    unwrapped prose lines these docs use. A pointer one heading away no longer covers a
    claim it is not next to.

    THE ONLY WAY TO CLEAR A HIT IS TO MOVE THE POINTER TO THE CLAIM. Not by widening the
    scope back out, not by an allowlist, not by deleting the claim. A claim that is
    genuinely correct and merely contains the token - `KINDS = ("clear", "lowE_single",
    "lowE_double")`, a legitimate list of glazing kinds a caller may model, retained
    deliberately per ERRATA entry 1 - earns a pointer beside it saying so.

    WHAT THIS GATE CAN PROTECT: the ten TRACKED docs. They are in git, so this gate runs
    against them in every checkout and in CI, and a falsified claim reintroduced into any
    of them fails the build. Their absence is itself a failure.

    WHAT IT CANNOT PROTECT: the local-only docs in UNTRACKED_SWEPT_DOCS. The `/docs/*`
    rule in .gitignore keeps them out of the repo on purpose - the same rule that keeps
    paywalled material out - so a fresh clone does not contain them and no CI run can
    ever check them. They are swept when the working tree has them and reported as
    `n_docs_absent` otherwise. A green gate on a clone therefore means "the tracked docs
    are clean", NOT "every doc is clean"; read the returned `docs_absent` list before
    treating a pass as complete coverage.

    LOCAL-DOC HITS ARE REPORTED, NOT RAISED - and the asymmetry is deliberate. A gate
    may only hard-fail on evidence every checkout can see. Those files are absent from a
    fresh clone and are live drafts in the author's tree, so raising on them would
    make the build's colour depend on the state of files git does not carry: red on one
    machine, green on the next, for the same commit. They come back as `manuscript_hits`
    and drop `complete_coverage`, so a near-miss is visible without being able to fail a
    run it is not evidence for. Anything found there is fixed in the manuscript, by hand.

    The ERRATA is exempt: recording a retired claim is its whole purpose. Scoped to
    NAMED file lists rather than a glob, so a doc added later is not silently assumed
    clean.
    """
    present_tracked, present_untracked, absent = [], [], []
    for name in tracked:
        if not (root / name).is_file():
            raise SystemExit(
                f"P3-G5: tracked doc {name} is missing - the sweep list is stale. "
                f"This doc is in git, so it must exist in every checkout.")
        present_tracked.append(name)
    for name in untracked:
        (present_untracked if (root / name).is_file() else absent).append(name)

    def scan(names):
        found = []
        for name in names:
            for lineno, block in _paragraphs((root / name).read_text()):
                low = block.lower()
                if "errata" in low:
                    continue
                for token in FALSIFIED_TOKENS:
                    if token in low:
                        found.append(f"{name}:{lineno}:{token}")
        return found

    hits = scan(present_tracked)
    manuscript_hits = scan(present_untracked)
    if hits:
        raise SystemExit(
            f"P3-G5: falsified glazing claim survives at {hits} with no ERRATA pointer "
            f"in the same paragraph - move the pointer next to the claim")
    checked = present_tracked + present_untracked
    if len(checked) < len(tracked):
        raise SystemExit(
            f"P3-G5: checked {len(checked)} docs but {len(tracked)} are tracked")
    return {"n_docs_checked": len(checked), "n_hits": 0,
            "n_docs_tracked": len(tracked), "n_docs_absent": len(absent),
            "docs_absent": tuple(absent),
            "n_manuscript_hits": len(manuscript_hits),
            "manuscript_hits": tuple(manuscript_hits),
            "complete_coverage": not absent and not manuscript_hits}


def test_p3_g5_passes_on_the_shipped_docs():
    tally = p3_g5_no_falsified_claim_in_docs()
    assert tally["n_hits"] == 0
    # Every TRACKED doc is checked in any checkout. The untracked manuscripts are
    # checked only when the working tree carries them, so the floor is the tracked set.
    assert tally["n_docs_checked"] >= len(TRACKED_SWEPT_DOCS)
    assert tally["n_docs_checked"] + tally["n_docs_absent"] == len(SWEPT_DOCS)
    # All ten tracked docs are swept, not some subset that happens to be clean.
    assert tally["n_docs_tracked"] == 10


def test_p3_g5_catches_a_stale_sweep_list(tmp_path):
    """A missing TRACKED doc is still a hard failure - the gate is not weakened."""
    with pytest.raises(SystemExit, match="sweep list is stale"):
        p3_g5_no_falsified_claim_in_docs(tmp_path)


def _clean_tracked_tree(tmp_path):
    """A fresh-clone stand-in: every tracked doc present and clean, no manuscripts."""
    for name in TRACKED_SWEPT_DOCS:
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("clean\n")
    return tmp_path


def test_p3_g5_reports_absent_untracked_docs_instead_of_failing(tmp_path):
    """An absent UNTRACKED manuscript degrades coverage; it does not fail the gate.

    This is the fresh-clone case: CI has the tracked docs and none of the manuscripts.
    """
    tally = p3_g5_no_falsified_claim_in_docs(_clean_tracked_tree(tmp_path),
                                             untracked=_SYNTHETIC_UNTRACKED)
    assert tally["n_docs_checked"] == len(TRACKED_SWEPT_DOCS)
    assert tally["n_docs_absent"] == len(_SYNTHETIC_UNTRACKED)
    assert tally["complete_coverage"] is False
    assert set(tally["docs_absent"]) == set(_SYNTHETIC_UNTRACKED)


def test_p3_g5_does_not_count_an_absent_doc_as_clean(tmp_path):
    """An absent doc must never be reported as a checked, clean one."""
    tally = p3_g5_no_falsified_claim_in_docs(_clean_tracked_tree(tmp_path),
                                             untracked=_SYNTHETIC_UNTRACKED)
    assert tally["n_docs_checked"] < len(TRACKED_SWEPT_DOCS) + len(_SYNTHETIC_UNTRACKED)


def test_p3_g5_still_catches_a_claim_in_a_tracked_doc(tmp_path):
    """The gate keeps its teeth on the docs it CAN protect."""
    _clean_tracked_tree(tmp_path)
    (tmp_path / TRACKED_SWEPT_DOCS[0]).write_text("the glazing is Low-E, VT 74.4 %\n")
    with pytest.raises(SystemExit, match="falsified glazing claim survives"):
        p3_g5_no_falsified_claim_in_docs(tmp_path)


def test_p3_g5_reports_a_claim_in_an_untracked_doc_without_failing(tmp_path):
    """A manuscript hit is REPORTED and drops coverage; it does not raise.

    Raising here would make the build's colour depend on git-ignored files: red in the
    author's tree, green in a clone, same commit. It must still be visible, though - an
    unreported hit is indistinguishable from a clean file.
    """
    _clean_tracked_tree(tmp_path)
    p = tmp_path / _SYNTHETIC_UNTRACKED[0]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("photopic VT 0.744\n")
    tally = p3_g5_no_falsified_claim_in_docs(tmp_path, untracked=_SYNTHETIC_UNTRACKED)
    assert tally["n_manuscript_hits"] == 1
    assert tally["manuscript_hits"][0].endswith(":1:0.744")
    assert tally["complete_coverage"] is False


def test_p3_g5_manuscript_hits_never_mask_a_tracked_one(tmp_path):
    """A dirty manuscript must not soften the verdict on a tracked doc."""
    _clean_tracked_tree(tmp_path)
    p = tmp_path / _SYNTHETIC_UNTRACKED[0]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("photopic VT 0.744\n")
    (tmp_path / TRACKED_SWEPT_DOCS[0]).write_text("the glazing is Low-E\n")
    with pytest.raises(SystemExit, match="falsified glazing claim survives"):
        p3_g5_no_falsified_claim_in_docs(tmp_path, untracked=_SYNTHETIC_UNTRACKED)


# --- the proximity rule itself ------------------------------------------------------
#
# The defect this replaced: `"errata" not in text` over the WHOLE document. Every swept
# doc mentions ERRATA somewhere, so every doc was exempt from every token forever. These
# four tests are the ones that would have caught it.

def test_p3_g5_exemption_does_not_reach_across_the_document(tmp_path):
    """THE ROOT-CAUSE TEST. An ERRATA pointer elsewhere in the file exempts nothing.

    Shaped like the real docs: a legitimate ERRATA admonition near the top, and a
    falsified claim far below it under a different heading. The document-wide rule
    passed this; the paragraph-scoped one must not.
    """
    _clean_tracked_tree(tmp_path)
    (tmp_path / TRACKED_SWEPT_DOCS[0]).write_text(
        "# Reference\n"
        "\n"
        "> **⚠️ ERRATA.** See the errata record, entries 1 and 2.\n"
        "\n"
        + "filler paragraph\n\n" * 40
        + "## Windows\n"
        "\n"
        "The glazing is Low-E at a photopic VT of 74.4 % (0.744).\n")
    with pytest.raises(SystemExit, match="falsified glazing claim survives"):
        p3_g5_no_falsified_claim_in_docs(tmp_path)


def test_p3_g5_exemption_still_works_beside_the_claim(tmp_path):
    """The same claim, one paragraph, with the pointer next to it: still exempt.

    The rule must not simply reject the tokens outright - the shipped docs legitimately
    quote the retired figure while retracting it, which is what a correction of record
    looks like.
    """
    _clean_tracked_tree(tmp_path)
    (tmp_path / TRACKED_SWEPT_DOCS[0]).write_text(
        "# Reference\n"
        "\n"
        "> **⚠️ ERRATA (2026-08-04).** The retired `TARGET_VT = 0.744` claimed a Low-E\n"
        "> unit at 74.4 % VT that the campaign never had.\n")
    assert p3_g5_no_falsified_claim_in_docs(tmp_path)["n_hits"] == 0


def test_p3_g5_exemption_covers_an_inline_table_row_pointer(tmp_path):
    """A markdown table is one block, and a row's own `See ERRATA` covers it.

    docs/spectral-sky-as-built.md is exactly this shape: a phase table whose retracted
    row carries an inline pointer, with the admonition block separately below. A rule
    that only recognised `> **ERRATA**` admonitions would fail that real doc.
    """
    _clean_tracked_tree(tmp_path)
    (tmp_path / TRACKED_SWEPT_DOCS[0]).write_text(
        "| Phase | Outcome |\n"
        "|---|---|\n"
        "| P1 | RETRACTED - no Low-E coating. See ERRATA 1-2. |\n"
        "| P2 | unrelated |\n")
    assert p3_g5_no_falsified_claim_in_docs(tmp_path)["n_hits"] == 0


def test_p3_g5_reports_the_line_of_the_offending_paragraph(tmp_path):
    """A hit names the paragraph, not just the file - it must be findable."""
    _clean_tracked_tree(tmp_path)
    (tmp_path / TRACKED_SWEPT_DOCS[0]).write_text(
        "clean\n\nclean\n\nthe window is Low-E\n")
    with pytest.raises(SystemExit) as e:
        p3_g5_no_falsified_claim_in_docs(tmp_path)
    assert ":5:low-e" in str(e.value)


def test_p3_g5_sweeps_the_repo_root_readme_not_a_docs_child(tmp_path):
    """README.md is at the repo ROOT; the gate must look for it there.

    Listed via a root-relative name rather than a `../` escape from docs/. Guard: a
    README seeded under docs/ must NOT satisfy the entry.
    """
    assert "README.md" in TRACKED_SWEPT_DOCS
    _clean_tracked_tree(tmp_path)
    (tmp_path / "README.md").unlink()
    (tmp_path / "docs" / "README.md").write_text("clean\n")
    with pytest.raises(SystemExit, match="README.md is missing"):
        p3_g5_no_falsified_claim_in_docs(tmp_path)


@pytest.mark.parametrize("name", [
    "docs/operating-guide.md", "docs/recalibrating-cloud-ccm.md",
    "docs/spectral-sky-methodology.md", "README.md",
])
def test_p3_g5_covers_the_task_8_docs(name):
    """The four docs swept in 655f921 are now genuinely in the protected set."""
    assert name in TRACKED_SWEPT_DOCS
    assert (ROOT / name).is_file()


TESTS = SRC.parent / "tests"

FIXTURE_SITE_FILES = ("test_receiver.py", "test_sky_radiance.py", "test_atmosphere.py",
                      "test_oriented_diffuse.py", "test_cloud_modifier.py")


def p3_g6_no_test_claims_the_campaign_site(tests=TESTS):
    """A test may USE 37.98/23.73 as a fixture; none may CLAIM it is the campaign site.

    The values stay because they are arbitrary fixtures with pinned expectations. What
    must not survive is a comment or docstring presenting them as the measured site -
    that is the falsified claim, and it is the thing a reader would carry away.
    """
    checked, hits = 0, []
    for name in FIXTURE_SITE_FILES:
        path = tests / name
        if not path.is_file():
            raise SystemExit(f"P3-G6: {name} is missing - the fixture list is stale")
        checked += 1
        for i, line in enumerate(path.read_text().splitlines(), 1):
            low = line.lower()
            if "37.98" in low and ("campaign" in low or "measured site" in low):
                hits.append(f"{name}:{i}")
    if hits:
        raise SystemExit(
            f"P3-G6: {hits} present the fixture coordinates as the campaign site - "
            f"- the fixture coordinates are arbitrary and are not any measured site")
    return {"n_files_checked": checked, "n_hits": 0}


def test_p3_g6_passes_on_the_shipped_tests():
    tally = p3_g6_no_test_claims_the_campaign_site()
    assert tally["n_files_checked"] == len(FIXTURE_SITE_FILES)
    assert tally["n_hits"] == 0


def test_p3_g6_catches_a_campaign_site_claim(tmp_path):
    for n in FIXTURE_SITE_FILES:
        (tmp_path / n).write_text("ok\n")
    (tmp_path / "test_receiver.py").write_text(
        "# 37.98 is the campaign site\ngeo = compute(latitude=37.98)\n")
    with pytest.raises(SystemExit, match="campaign site"):
        p3_g6_no_test_claims_the_campaign_site(tmp_path)
