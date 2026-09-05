"""The generated FastAPI schema must match notification-service/openapi.yaml.

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


def test_documented_paths_are_served_under_api_v1():
    contract = _contract()
    generated = app.openapi()
    server_prefix = contract["servers"][0]["url"]
    for path, item in contract["paths"].items():
        full = f"{server_prefix}{path}"
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


_PROTECTED = [
    ("/notifications", "get"),
    ("/notifications/{notification_id}", "get"),
    ("/notification-preferences", "get"),
    ("/notification-preferences", "put"),
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
