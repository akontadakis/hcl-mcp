import json
import asyncio
import pytest
from fastmcp import FastMCP
import mcp.types as mt
import hcl_mcp.resources as res
from hcl_core.compliance import THRESHOLD_STANDARDS

ALLOWED_MIME = {"application/json", "text/plain", "text/markdown"}

def _fresh_server():
    m = FastMCP("test")
    res.register_resources(m)
    return m

def test_every_resource_has_complete_metadata():
    seen_names = set()
    for r in res.RESOURCES:
        assert r.name and r.name == r.name.lower() and " " not in r.name, r.name
        assert "_" not in r.name, f"name should be kebab-case: {r.name}"
        assert r.name not in seen_names, f"duplicate name {r.name}"
        seen_names.add(r.name)
        assert r.title and r.description
        assert r.mime_type in ALLOWED_MIME
        assert len(r.tags) >= 1

def test_register_resources_registers_all_static_and_templates():
    m = _fresh_server()
    static_uris = {str(r.uri) for r in asyncio.run(m.list_resources())}
    tpl_uris = {str(t.uri_template) for t in asyncio.run(m.list_resource_templates())}
    all_registered = static_uris | tpl_uris
    for r in res.RESOURCES:
        assert r.uri in all_registered, f"{r.uri} not registered"

def test_templates_are_self_documenting():
    m = _fresh_server()
    for t in asyncio.run(m.list_resource_templates()):
        assert t.title, f"{t.uri_template} missing title"
        assert t.description, f"{t.uri_template} missing description"
        assert t.mime_type, f"{t.uri_template} missing mime_type"

def test_moved_handlers_still_return_expected_payloads():
    assert "0.265" in res.reference_coefficients()
    assert json.loads(res.preset_resource("D65"))["spd"]
    with pytest.raises(ValueError):
        res.action_spectrum_resource("BOGUS")

def test_caveats_resource_markdown_lists_9_3_items():
    txt = res.caveats_resource()
    assert txt.strip() and "float-division" in txt
    assert res.SECTION_9_3_CAVEATS[0] in txt

def test_glossary_resource_defines_key_terms():
    txt = res.glossary_resource()
    for term in ("mel-EDI", "EML", "mel-DER", "CCT", "alpha-opic"):
        assert term in txt

def test_index_lists_every_resource_and_template_arg_values():
    doc = json.loads(res.index_resource())
    uris = {e["uri"] for e in doc["resources"]}
    assert uris == {r.uri for r in res.RESOURCES}
    # every entry carries metadata
    for e in doc["resources"]:
        assert e["name"] and e["title"] and e["mime_type"] and e["tags"]
    # template entries enumerate valid argument values
    preset_entry = next(e for e in doc["resources"] if e["uri"] == "hcl://preset/{name}")
    assert "D65" in preset_entry["arguments"]["name"]

def test_compliance_resource_returns_thresholds_not_verdict():
    for standard in THRESHOLD_STANDARDS:
        out = json.loads(res.compliance_resource(standard))
        assert "result" not in out and "result_points" not in out, standard
        assert out["standard"]
    # spot-check a real stored number survives the JSON round-trip
    brown = json.loads(res.compliance_resource("brown_2022"))
    assert brown["thresholds"]["daytime"]["mel_edi_lx"] == 250

def test_compliance_en_12464_1_static_matches_template_for_that_standard():
    static = json.loads(res.en_12464_1_resource())
    via_tmpl = json.loads(res.compliance_resource("en_12464_1"))
    assert static == via_tmpl

def _ref(uri):
    return mt.ResourceTemplateReference(type="ref/resource", uri=uri)

def _arg(name, value):
    return mt.CompletionArgument(name=name, value=value)


def test_complete_prefix_filters_presets():
    out = asyncio.run(res._complete(_ref("hcl://preset/{name}"), _arg("name", "D"), None))
    assert "D65" in out.values and "D50" in out.values
    assert all(v.lower().startswith("d") for v in out.values)

def test_complete_empty_value_returns_all_action_spectra():
    out = asyncio.run(res._complete(_ref("hcl://action-spectrum/{type}"), _arg("type", ""), None))
    assert set(out.values) == {"S", "M", "L", "rhod", "mel", "V", "D65"}

def test_complete_standards():
    out = asyncio.run(res._complete(_ref("hcl://compliance/{standard}"), _arg("standard", "en"), None))
    assert "en_17037" in out.values and "en_12464_1" in out.values

def test_complete_unmapped_and_prompt_ref_return_none():
    assert asyncio.run(res._complete(_ref("hcl://reference/coefficients"), _arg("x", ""), None)) is None
    pref = mt.PromptReference(type="ref/prompt", name="explain_concept")
    assert asyncio.run(res._complete(pref, _arg("topic", ""), None)) is None

def test_register_resources_wires_completion_handler():
    m = _fresh_server()
    assert mt.CompleteRequest in m._mcp_server.request_handlers
