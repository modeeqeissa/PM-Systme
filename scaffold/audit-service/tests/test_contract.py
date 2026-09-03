"""The generated FastAPI schema must match audit-service/openapi.yaml."""
import os

import yaml

from app.main import app

_CONTRACT = os.path.join(os.path.dirname(__file__), os.pardir, "openapi.yaml")


def _contract():
    with open(_CONTRACT) as fh:
        return yaml.safe_load(fh)


def test_paths_and_methods_served():
    contract = _contract()
    generated = app.openapi()
    prefix = contract["servers"][0]["url"]
    for path, item in contract["paths"].items():
        full = f"{prefix}{path}"
        assert full in generated["paths"], f"{full} missing"
        for method in item:
            assert method in generated["paths"][full]


def test_no_undocumented_operations():
    contract = _contract()
    generated = app.openapi()
    documented = {
        (f"/api/v1{p}", m) for p, item in contract["paths"].items() for m in item
    }
    for path, item in generated["paths"].items():
        for method in item:
            assert (path, method) in documented, f"{method.upper()} {path} undocumented"


def test_every_op_is_bearer_secured_and_documents_401_403():
    contract = _contract()
    generated = app.openapi()
    assert contract["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"
    gen_schemes = generated["components"].get("securitySchemes", {})
    assert any(s.get("scheme") == "bearer" for s in gen_schemes.values())
    for path, item in contract["paths"].items():
        for method, op in item.items():
            assert op.get("security")
            assert {"401", "403"} <= set(op["responses"])
            g = generated["paths"][f"/api/v1{path}"][method]
            assert g.get("security") and "401" in g["responses"]


def test_audit_entry_schema_matches():
    contract = _contract()
    generated = app.openapi()
    want = set(contract["components"]["schemas"]["AuditEntry"]["properties"])
    got = set(generated["components"]["schemas"]["AuditEntry"]["properties"])
    assert got == want


def test_chain_verification_schema_matches():
    contract = _contract()
    generated = app.openapi()
    want = set(contract["components"]["schemas"]["ChainVerification"]["properties"])
    got = set(generated["components"]["schemas"]["ChainVerification"]["properties"])
    assert got == want
