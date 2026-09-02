import pytest
from hcl_core.compliance import check_compliance

def test_well_l03_points_electric():
    assert check_compliance(mel_edi=200, standard="well_v2_l03")["result_points"] == 1
    assert check_compliance(mel_edi=250, standard="well_v2_l03")["result_points"] == 3
    assert check_compliance(mel_edi=100, standard="well_v2_l03")["result_points"] == 0

def test_well_l03_daylight_met_lowers_threshold():
    assert check_compliance(mel_edi=120, standard="well_v2_l03", daylight_met=True)["result_points"] == 1

def test_well_accepts_eml_and_converts():
    # EML 275.75 -> mel-EDI 250 -> 3 points
    assert check_compliance(eml=275.75, standard="well_v2_l03")["result_points"] == 3

def test_well_stores_literal_published_eml_thresholds():
    # Spec 8.1 "store all": the literal published EML table must be surfaced.
    v = check_compliance(mel_edi=200, standard="well_v2_l03")
    pub = v["published_eml_thresholds"]
    assert pub["1pt"] == {"electric": 150, "daylight": 120}
    # 240/180 EML is the PILOT-ERA 3-point pair, kept for provenance only. Scoring uses the
    # current IWBI criterion (275 EML -> 250 mel-EDI), which is why the key says so.
    assert pub["3pt_pilot"] == {"electric": 240, "daylight": 180}
    assert pub["iwbi_current_noon_eml"] == 275
    assert "verify against live WELL" in v["verify_flag"].lower() or \
           "verify against live well" in v["verify_flag"].lower()

def test_brown_consensus_periods():
    assert check_compliance(mel_edi=300, standard="brown_2022", period="daytime")["result"] == "pass"
    assert check_compliance(mel_edi=8, standard="brown_2022", period="evening")["result"] == "pass"
    assert check_compliance(mel_edi=2, standard="brown_2022", period="sleep")["result"] == "fail"

def test_iso_cie_is_informative():
    v = check_compliance(mel_edi=300, standard="iso_cie_8995_1_2025", period="daytime")
    assert v["result"] == "pass" and "informative" in v["flag"]

def test_en17037_non_circadian():
    v = check_compliance(mel_edi=300, standard="en_17037")
    assert v["flag"] == "non-circadian" and v["result"] == "n/a"

def test_ul24480_unsupported():
    v = check_compliance(mel_edi=300, standard="ul_24480")
    assert v["result"] == "unsupported" and "Circadian Stimulus" in v["notes"]

def test_unknown_standard_raises():
    with pytest.raises(ValueError):
        check_compliance(mel_edi=300, standard="bogus")

def test_en12464_task_table_values():
    # The stored task table must carry the §10 values exactly.
    from hcl_core.compliance import EN_12464_1_TASKS
    assert EN_12464_1_TASKS["office_writing_reading"] == {"em": 500, "ugrl": 19, "uo": 0.60, "ra": 80}
    assert EN_12464_1_TASKS["office_technical_drawing"] == {"em": 750, "ugrl": 16, "uo": 0.70, "ra": 80}
    assert EN_12464_1_TASKS["office_conference"] == {"em": 500, "ugrl": 19, "uo": 0.60, "ra": 80}
    assert EN_12464_1_TASKS["office_filing_copying"] == {"em": 300, "ugrl": 19, "uo": 0.40, "ra": 80}
    assert EN_12464_1_TASKS["office_reception"] == {"em": 300, "ugrl": 22, "uo": 0.60, "ra": 80}
    assert EN_12464_1_TASKS["classroom"] == {"em": 300, "ugrl": 19, "uo": 0.60, "ra": 80}
    assert EN_12464_1_TASKS["classroom_evening_adult"] == {"em": 500, "ugrl": 19, "uo": 0.60, "ra": 80}
    assert EN_12464_1_TASKS["corridor_circulation"] == {"em": 100, "ugrl": 28, "uo": 0.40, "ra": 40}

def test_en12464_pass_example():
    v = check_compliance(standard="en_12464_1", task="office_writing_reading",
                         em=520, ugr=17, uo=0.62, ra=85)
    assert v["standard"].startswith("EN 12464-1")
    assert v["result"] == "pass"
    params = v["parameters"]
    assert params["em"]["met"] is True and params["em"]["required"] == 500
    assert params["ugr"]["met"] is True and params["ugr"]["limit"] == 19
    assert params["uo"]["met"] is True and params["uo"]["required"] == 0.60
    assert params["ra"]["met"] is True and params["ra"]["required"] == 80
    assert "verify against EN 12464-1:2021" in v["flag"]
    assert v["mandatory"] is True

def test_en12464_fail_example_each_parameter():
    v = check_compliance(standard="en_12464_1", task="office_writing_reading",
                         em=400, ugr=22, uo=0.50, ra=70)
    assert v["result"] == "fail"
    params = v["parameters"]
    assert params["em"]["met"] is False     # 400 < 500
    assert params["ugr"]["met"] is False    # 22 > 19
    assert params["uo"]["met"] is False     # 0.50 < 0.60
    assert params["ra"]["met"] is False     # 70 < 80

def test_en12464_surround_background_relationships():
    # task 500 -> surround graded floor 300, surround Uo>=0.40; background >= 1/3 surround, Uo>=0.10.
    v = check_compliance(standard="en_12464_1", task="office_writing_reading", em=520,
                         em_surround=320, uo_surround=0.45, em_background=120, uo_background=0.12)
    rel = v["relationships"]
    assert rel["surround"]["required_em"] == 300 and rel["surround"]["met"] is True
    assert rel["surround"]["uo_required"] == 0.40 and rel["surround"]["uo_met"] is True
    assert rel["background"]["required_em"] == pytest.approx(320 / 3, abs=1e-6)
    assert rel["background"]["met"] is True and rel["background"]["uo_met"] is True

def test_en12464_surround_grading_table():
    # EN 12464-1 Table 3 immediate-surround grading: >=750->500, >=500->300, >=300->200,
    # <=200 -> equal to task.
    from hcl_core.compliance import en_12464_surround_minimum
    assert en_12464_surround_minimum(750) == 500
    assert en_12464_surround_minimum(500) == 300
    assert en_12464_surround_minimum(300) == 200
    assert en_12464_surround_minimum(200) == 200  # <=200 -> equal to task
    assert en_12464_surround_minimum(150) == 150

def test_en12464_wall_ceiling_cylindrical_thresholds():
    v = check_compliance(standard="en_12464_1", task="office_writing_reading", em=520,
                         em_wall=60, uo_wall=0.12, em_ceiling=40, uo_ceiling=0.11,
                         em_cylindrical=160, uo_cylindrical=0.15)
    sr = v["surfaces"]
    assert sr["wall"]["required_em"] == 50 and sr["wall"]["met"] is True
    assert sr["ceiling"]["required_em"] == 30 and sr["ceiling"]["met"] is True
    assert sr["cylindrical"]["required_em"] == 50 and sr["cylindrical"]["met"] is True
    # cylindrical carries the higher >=150 tier as an informative note
    assert "150" in sr["cylindrical"]["note"]

def test_en12464_unknown_task_raises():
    with pytest.raises(ValueError):
        check_compliance(standard="en_12464_1", task="bogus_task", em=500)

def test_en12464_no_parameters_is_incomplete_not_pass():
    # A call supplying no measured values must NOT green-light an empty design.
    v = check_compliance(standard="en_12464_1", task="office_writing_reading")
    assert v["result"] == "incomplete"
    assert v["parameters"] == {} and v["relationships"] == {} and v["surfaces"] == {}


def test_en12464_background_without_surround_is_incomplete_not_silent():
    # em_background supplied but em_surround omitted: the background check needs the surround
    # to define its required Ēm (= em_surround/3). It must surface as an explicit "incomplete"
    # entry rather than being silently dropped, and must not yield a clean pass.
    v = check_compliance(standard="en_12464_1", task="office_writing_reading", em=520,
                         em_background=120, uo_background=0.12)
    rel = v["relationships"]
    assert "background" in rel
    assert rel["background"]["met"] == "incomplete"
    assert rel["background"]["value"] == 120
    assert "surround" in rel["background"]["note"].lower()
    assert v["result"] != "pass"


def test_describe_thresholds_brown_no_scoring():
    from hcl_core.compliance import describe_thresholds
    d = describe_thresholds("brown_2022")
    # raw thresholds, NOT a scored verdict
    assert "result" not in d and "result_points" not in d
    assert d["kind"] == "circadian"
    assert d["thresholds"]["daytime"]["mel_edi_lx"] == 250
    assert d["thresholds"]["daytime"]["operator"] == ">="
    assert "Brown" in d["citation"]

def test_describe_thresholds_well_publishes_eml_table():
    from hcl_core.compliance import describe_thresholds
    d = describe_thresholds("well_v2_l03")
    assert "result_points" not in d
    assert d["published_eml_thresholds"]["1pt"]["electric"] == 150
    # 250, not the pilot-era 218: current WELL v2 L03 tier 2 is 275 EML / 250 mel-EDI.
    assert d["thresholds_mel_edi"]["electric_only"]["3pt"] == 250

def test_describe_thresholds_en_12464_1_tasks_and_relationships():
    from hcl_core.compliance import describe_thresholds
    d = describe_thresholds("en_12464_1")
    assert d["kind"] == "photopic_visual"
    assert d["tasks"]["office_writing_reading"]["em"] == 500
    assert "surround" in d["relationships"]

def test_describe_thresholds_en_17037():
    from hcl_core.compliance import describe_thresholds
    assert describe_thresholds("en_17037")["kind"] == "daylight_provision"

def test_describe_thresholds_ul_24480():
    from hcl_core.compliance import describe_thresholds
    assert describe_thresholds("ul_24480")["kind"] == "unsupported"

def test_describe_thresholds_unknown_raises():
    from hcl_core.compliance import describe_thresholds
    with pytest.raises(ValueError):
        describe_thresholds("bogus_standard")

def test_describe_thresholds_iso_cie_citation_and_flag():
    from hcl_core.compliance import describe_thresholds
    d = describe_thresholds("iso_cie_8995_1_2025")
    assert "ISO/CIE 8995-1:2025" in d["citation"]
    assert "informative" in d["flag"]
    assert d["thresholds"]["daytime"]["mel_edi_lx"] == 250

def test_threshold_standards_constant_matches_accessor():
    from hcl_core.compliance import THRESHOLD_STANDARDS, describe_thresholds
    for s in THRESHOLD_STANDARDS:
        assert describe_thresholds(s)["standard"]  # every listed standard resolves
