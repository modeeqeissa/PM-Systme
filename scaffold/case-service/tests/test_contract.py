"""The generated FastAPI schema must match case-service/openapi.yaml.

`servers[0].url` in the contract is `/api/v1`, so a documented path P maps to
`/api/v1{P}` in the running app.
"""
import os

import yaml

from app.main import app

_CONTRACT_PATH = os.path.join(os.path.dirname(__file__), os.pardir, "openapi.yaml")


def _contract():
    with open(_CONTRACT_PATH) as fh:
        return yaml.safe_load(fh)


def _resolve(schema: dict, node: dict) -> dict:
    """Flatten a $ref / allOf node into a {properties, required} view."""
    if "$ref" in node:
        name = node["$ref"].split("/")[-1]
        return _resolve(schema, schema["components"]["schemas"][name])
    if "allOf" in node:
        props: dict = {}
        required: list = []
        for part in node["allOf"]:
            resolved = _resolve(schema, part)
            props.update(resolved["properties"])
            required.extend(resolved["required"])
        return {"properties": props, "required": required}
    return {"properties": node.get("properties", {}), "required": node.get("required", [])}


def test_documented_paths_are_served_under_api_v1():
    contract = _contract()
    generated = app.openapi()
    server_prefix = contract["servers"][0]["url"]
    for path, item in contract["paths"].items():
        full = f"{server_prefix}{path}"
        assert full in generated["paths"], f"{full} missing from app"
        for method in item:
            assert method in generated["paths"][full], f"{method.upper()} {full} missing"


def test_incident_response_matches_contract():
    contract = _contract()
    generated = app.openapi()
    want = _resolve(contract, contract["components"]["schemas"]["Incident"])
    got = generated["components"]["schemas"]["IncidentOut"]
    assert set(got["properties"]) == set(want["properties"]), (
        set(want["properties"]).symmetric_difference(got["properties"])
    )


def test_case_response_matches_contract():
    contract = _contract()
    generated = app.openapi()
    want = _resolve(contract, contract["components"]["schemas"]["Case"])
    got = generated["components"]["schemas"]["CaseOut"]
    assert set(got["properties"]) == set(want["properties"])
    status_node = got["properties"]["status"]
    if "$ref" in status_node:
        ref = status_node["$ref"].split("/")[-1]
        status_node = generated["components"]["schemas"][ref]
    elif "allOf" in status_node:
        ref = status_node["allOf"][0]["$ref"].split("/")[-1]
        status_node = generated["components"]["schemas"][ref]
    assert set(status_node["enum"]) == {
        "open", "investigating", "referred_prosecution", "closed", "suspended",
    }


def test_incident_create_required_fields_match_contract():
    contract = _contract()
    generated = app.openapi()
    want = set(contract["components"]["schemas"]["IncidentCreate"]["required"])
    got = set(generated["components"]["schemas"]["IncidentCreate"]["required"])
    assert got == want


def test_patch_case_status_contract_matches_behaviour():
    """Contract documents: 200 returns a Case body, 404 on unknown id, 409 on bad move."""
    contract = _contract()
    responses = contract["paths"]["/cases/{case_id}/status"]["patch"]["responses"]
    assert set(responses) >= {"200", "404", "409"}
    ok_schema = responses["200"]["content"]["application/json"]["schema"]
    assert ok_schema["$ref"].split("/")[-1] == "Case"

    generated = app.openapi()
    gen_responses = generated["paths"]["/api/v1/cases/{case_id}/status"]["patch"]["responses"]
    assert set(gen_responses) >= {"200", "404", "409"}
    gen_schema = gen_responses["200"]["content"]["application/json"]["schema"]
    assert gen_schema["$ref"].split("/")[-1] == "CaseOut"


def test_post_incidents_declares_idempotency_key_header():
    generated = app.openapi()
    params = generated["paths"]["/api/v1/incidents"]["post"]["parameters"]
    header = next((p for p in params if p["name"] == "Idempotency-Key"), None)
    assert header is not None and header["in"] == "header"
    assert header["required"] is True


_PROTECTED = [
    ("/incidents", "post"),
    ("/cases", "get"),
    ("/cases", "post"),
    ("/cases/{case_id}", "get"),
    ("/cases/{case_id}/status", "patch"),
    ("/cases/{case_id}/arrests", "get"),
    ("/cases/{case_id}/arrests", "post"),
]


def test_every_endpoint_requires_bearer_auth_and_documents_401():
    contract = _contract()
    generated = app.openapi()

    assert "bearerAuth" in contract["components"]["securitySchemes"]
    assert contract["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"

    gen_schemes = generated["components"].get("securitySchemes", {})
    assert any(s.get("scheme") == "bearer" for s in gen_schemes.values())

    for path, method in _PROTECTED:
        c_op = contract["paths"][path][method]
        assert c_op.get("security"), f"{method} {path} missing security in contract"
        assert "401" in c_op["responses"], f"{method} {path} missing 401 in contract"

        g_op = generated["paths"][f"/api/v1{path}"][method]
        assert g_op.get("security"), f"{method} {path} not secured in generated schema"
        assert "401" in g_op["responses"], f"{method} {path} missing 401 in generated schema"


def test_no_undocumented_operations():
    contract = _contract()
    generated = app.openapi()
    documented = {
        (f"/api/v1{p}", m) for p, item in contract["paths"].items() for m in item
    }
    for path, item in generated["paths"].items():
        for method in item:
            assert (path, method) in documented, f"{method.upper()} {path} not in openapi.yaml"
