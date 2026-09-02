from hcl_core.dosimetry import hours_above_threshold, daily_profile, dose_summary

def test_hours_above_threshold():
    medi = [100, 300, 260, 50]; hoy = [8, 9, 10, 11]  # 1-hour steps
    assert hours_above_threshold(medi, hoy, threshold=250) == 2.0  # 300 and 260

def test_daily_profile_groups_by_day():
    medi = [300, 260, 400]; days = [1, 1, 2]
    prof = daily_profile(medi, days)
    assert prof[1] == [300, 260] and prof[2] == [400]

def test_dose_summary():
    s = dose_summary([100, 300, 260, 50], [8, 9, 10, 11], threshold=250)
    assert s["hours_above"] == 2.0 and s["max"] == 300 and round(s["mean"], 1) == 177.5

# --- duration edge cases: each sample contributes its OWN step, never the gap that follows ---

def test_hours_above_single_point_high_uses_unit_fallback():
    # single high point, no spacing to infer from -> nominal 1.0 h
    assert hours_above_threshold([300], [8], threshold=250) == 1.0

def test_hours_above_single_point_below_threshold_is_zero():
    assert hours_above_threshold([100], [8], threshold=250) == 0.0

def test_hours_above_single_point_honours_explicit_step():
    # a sub-hourly run's lone sample is 15 min, not the 1.0 h fallback
    assert hours_above_threshold([300], [8], threshold=250, step_hours=0.25) == 0.25

def test_hours_above_last_point_high_counts_one_step_not_a_gap():
    # 2 h spacing -> the final high sample is worth its own 2 h step
    assert hours_above_threshold([100, 100, 300], [8, 10, 12], threshold=250) == 2.0

def test_hours_above_short_tail_interval_is_clamped_to_the_real_gap():
    # nominal step 2.0 h, but the last interval is only 0.5 h -> 2.0 + 0.5, not 2.0 + 2.0.
    # Two samples give two distinct gaps with no repetition, so the step is stated explicitly
    # (production always knows it: run_annual threads timestep_min).
    assert hours_above_threshold([300, 260, 50], [8, 10, 10.5],
                                 threshold=250, step_hours=2.0) == 2.5

def test_hours_above_does_not_charge_a_sample_the_following_gap():
    # REGRESSION: the old forward-difference charged i=2 the 4 h gap (13-9) for a 1 h sample.
    # With a 1 h step the answer is 1.0 (i=0) + 1.0 (i=2) = 2.0, not 5.0.
    assert hours_above_threshold([300, 100, 260], [8, 9, 13],
                                 threshold=250, step_hours=1.0) == 2.0

def test_modal_gap_infers_the_step_when_it_recurs():
    # A recurring 1 h step with one 4 h block gap -> the step is inferred as 1.0, not the outlier.
    # All five samples above threshold -> 5 x 1.0 h.
    hoy = [8, 9, 10, 14, 15]
    assert hours_above_threshold([9999.0] * 5, hoy, threshold=250) == 5.0

def test_hours_above_empty_series_is_zero():
    assert hours_above_threshold([], [], threshold=250) == 0.0


# --- REGRESSION: gapped (daylit-hours-only / multi-month) HOY series ---

def _window_hoy(days, first_hour=8, last_hour=18, day_stride=1):
    """HOY for an occupied window repeated over several days -> gaps at every day boundary."""
    return [d * 24 * day_stride + h
            for d in range(days) for h in range(first_hour, last_hour + 1)]

def test_gapped_multiday_window_counts_only_occupied_hours():
    # 3 days x 11 occupied hours, all above threshold -> 33 h. The forward-difference bug
    # charged each 18:00 sample the 14 h overnight gap and reported 59.0.
    hoy = _window_hoy(3)
    assert len(hoy) == 33
    assert hours_above_threshold([9999.0] * 33, hoy, threshold=250) == 33.0

def test_lone_sample_on_a_day_boundary_is_one_step_not_the_night():
    # only 18:00 of day 0 is above threshold; the next sample is 08:00 next day (14 h later)
    hoy = _window_hoy(3)
    medi = [0.0] * 33
    medi[10] = 9999.0                                  # index 10 == 18:00 on day 0
    assert hours_above_threshold(medi, hoy, threshold=250) == 1.0

def test_multi_month_window_is_not_charged_the_inter_month_gap():
    # weather.decompose repeats a fixed day/hour window across months, so consecutive samples can
    # be ~710 h apart. 3 months x 11 h -> 33 h, not the 1475 h the forward difference reported.
    hoy = [m * 720 + h for m in range(3) for h in range(8, 19)]
    assert hours_above_threshold([9999.0] * 33, hoy, threshold=250) == 33.0

def test_subhourly_gapped_window_uses_the_real_timestep():
    # 15-min steps over one 08:00-18:00 day, plus a second day -> 2 x 11 h = 22 h
    hoy = [d * 24 + 8 + 0.25 * i for d in range(2) for i in range(44)]
    got = hours_above_threshold([9999.0] * len(hoy), hoy, threshold=250, step_hours=0.25)
    assert got == 22.0

def test_contiguous_full_year_is_unchanged():
    # the full-8760 path must be byte-identical to the old behaviour
    hoy = list(range(8760))
    assert hours_above_threshold([9999.0] * 8760, hoy, threshold=250) == 8760.0


# --- REGRESSION: dose_summary must be fed mel-EDI, not melanopic_lux ---

def test_dose_summary_threshold_is_evaluated_on_the_values_given():
    # A mel-EDI series just below threshold must score 0 h. The same physical scene expressed as
    # melanopic_lux (x1.0997) would clear 250 and score 11 h -- the substitution this guards.
    hoy = _window_hoy(1)
    mel_edi = [240.0] * 11
    mel_lux = [v * 1.0997 for v in mel_edi]
    assert dose_summary(mel_edi, hoy, threshold=250)["hours_above"] == 0.0
    assert dose_summary(mel_lux, hoy, threshold=250)["hours_above"] == 11.0
