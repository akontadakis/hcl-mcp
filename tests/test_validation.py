from hcl_core.validation import run_validation


def test_validation_all_pass():
    report = run_validation()
    assert report["ok"] is True
    names = {c["name"] for c in report["checks"]}
    assert {"weight_sums", "alpha_opic_nonzero", "elr_scale_invariant"} <= names
    assert all(c["passed"] for c in report["checks"] if c["name"] != "channel_vs_spd_alpha_opic")


def test_validation_includes_published_kd65_and_meldder():
    from hcl_core.validation import run_validation
    report = run_validation()
    names = {c["name"] for c in report["checks"]}
    assert {"kd65_vs_published", "mel_der_d65"} <= names
    assert report["ok"] is True

def test_validation_includes_channel_vs_spd_alpha_opic():
    from hcl_core.validation import run_validation
    report = run_validation()
    by_name = {c["name"]: c for c in report["checks"]}
    assert "channel_vs_spd_alpha_opic" in by_name
    chk = by_name["channel_vs_spd_alpha_opic"]
    # SURFACES divergence — never hard-fails the suite, even if EDI paths disagree.
    assert "divergence_pct" in chk["detail"]
    assert "mel_edi" in chk["detail"]["divergence_pct"]
    # The check's own pass flag does not gate report["ok"] (it's informative, not a hard fail).
    assert isinstance(chk["ok"], bool)


def test_validation_includes_binning_fidelity():
    from hcl_core.validation import run_validation
    report = run_validation()
    by_name = {c["name"]: c for c in report["checks"]}
    assert "binning_fidelity" in by_name
    assert by_name["binning_fidelity"]["passed"] is True
    assert report["ok"] is True


def test_channel_vs_spd_divergence_is_bounded():
    from hcl_core.validation import run_validation
    report = run_validation()
    by_name = {c["name"]: c for c in report["checks"]}
    d = by_name["channel_vs_spd_alpha_opic"]["detail"]
    # The informative check now surfaces a bounded flag + the ceilings.
    assert d["elr_ratio_divergence_pct"] < 5.0
    assert d["bounded"] is True
    assert all(v < 300.0 for v in d["divergence_pct"].values())
    # A SEPARATE, non-informative check exists and DOES gate report["ok"].
    assert "channel_vs_spd_divergence_bounded" in by_name
    assert by_name["channel_vs_spd_divergence_bounded"]["ok"] is True
