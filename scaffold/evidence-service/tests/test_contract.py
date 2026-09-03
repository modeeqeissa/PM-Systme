"""The generated FastAPI schema must match evidence-service/openapi.yaml."""
import os

import yaml

from app.main import app

_CONTRACT_PATH = os.path.join(os.path.dirname(__file__), os.pardir, "openapi.yaml")


def _contract():
    with open(_CONTRACT_PATH) as fh:
        return yaml.safe_load(fh)


def test_documented_paths_and_methods_are_served():
    contract = _contract()
    generated = app.openapi()
    prefix = contract["servers"][0]["url"]
    for path, item in contract["paths"].items():
        full = f"{prefix}{path}"
        assert full in generated["paths"], f"{full} missing from app"
        for method in item:
            assert method in generated["paths"][full], f"{method.upper()} {full} missing"


def test_no_undocumented_operations():
    contract = _contract()
    generated = app.openapi()
    documented = {
        (f"/api/v1{p}", m) for p, item in contract["paths"].items() for m in item
    }
    for path, item in generated["paths"].items():
        for method in item:
            assert (path, method) in documented, f"{method.upper()} {path} not in openapi.yaml"


def test_every_operation_requires_bearer_and_documents_401_403():
    contract = _contract()
    generated = app.openapi()
    assert contract["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"
    gen_schemes = generated["components"].get("securitySchemes", {})
    assert any(s.get("scheme") == "bearer" for s in gen_schemes.values())

    for path, item in contract["paths"].items():
        for method, op in item.items():
            assert op.get("security"), f"{method} {path} missing security in contract"
            assert "401" in op["responses"], f"{method} {path} missing 401 in contract"
            assert "403" in op["responses"], f"{method} {path} missing 403 in contract"
            g_op = generated["paths"][f"/api/v1{path}"][method]
            assert g_op.get("security"), f"{method} {path} not secured in generated schema"
            assert "401" in g_op["responses"], f"{method} {path} missing 401 (generated)"


def test_evidence_item_schema_fields_match():
    contract = _contract()
    generated = app.openapi()
    want = set(contract["components"]["schemas"]["EvidenceItem"]["properties"])
    got = set(generated["components"]["schemas"]["EvidenceItemOut"]["properties"])
    assert got == want


def test_custody_event_schema_fields_match():
    contract = _contract()
    generated = app.openapi()
    want = set(contract["components"]["schemas"]["CustodyEvent"]["properties"])
    got = set(generated["components"]["schemas"]["CustodyEventOut"]["properties"])
    assert got == want


def test_hash_verification_schema_fields_match():
    contract = _contract()
    generated = app.openapi()
    want = set(contract["components"]["schemas"]["HashVerification"]["properties"])
    got = set(generated["components"]["schemas"]["HashVerification"]["properties"])
    assert got == want


def test_custody_action_enum_matches_contract():
    contract = _contract()
    generated = app.openapi()
    want = set(
        contract["components"]["schemas"]["CustodyEventCreate"]["properties"]["action"][
            "enum"
        ]
    )
    gen_schemas = generated["components"]["schemas"]
    node = gen_schemas["CustodyEventCreate"]["properties"]["action"]
    if "$ref" in node:
        node = gen_schemas[node["$ref"].split("/")[-1]]
    elif "allOf" in node:
        node = gen_schemas[node["allOf"][0]["$ref"].split("/")[-1]]
    assert set(node["enum"]) == want
