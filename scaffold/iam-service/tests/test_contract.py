"""The generated FastAPI schema must match iam-service/openapi.yaml.

`servers[0].url` is `/api/v1`, so a documented path P is served at `/api/v1{P}`.
"""
import os

import yaml

from app.main import app

_CONTRACT_PATH = os.path.join(os.path.dirname(__file__), os.pardir, "openapi.yaml")


def _contract():
    with open(_CONTRACT_PATH) as fh:
        return yaml.safe_load(fh)


def test_every_documented_path_and_method_is_served():
    contract = _contract()
    generated = app.openapi()
    prefix = contract["servers"][0]["url"]
    for path, item in contract["paths"].items():
        full = f"{prefix}{path}"
        assert full in generated["paths"], f"{full} missing from app"
        for method in item:
            assert method in generated["paths"][full], f"{method.upper()} {full} missing"


def test_no_undocumented_public_paths():
    contract = _contract()
    generated = app.openapi()
    prefix = contract["servers"][0]["url"]
    documented = {f"{prefix}{p}" for p in contract["paths"]}
    for path in generated["paths"]:
        assert path in documented, f"{path} is served but not in openapi.yaml"


def test_token_pair_schema_fields_match():
    contract = _contract()
    generated = app.openapi()
    want = set(contract["components"]["schemas"]["TokenPair"]["properties"])
    got = set(generated["components"]["schemas"]["TokenPair"]["properties"])
    assert got == want


def test_current_user_schema_fields_match():
    contract = _contract()
    generated = app.openapi()
    want = set(contract["components"]["schemas"]["CurrentUser"]["properties"])
    got = set(generated["components"]["schemas"]["CurrentUser"]["properties"])
    assert got == want


def test_user_create_required_fields_match():
    contract = _contract()
    generated = app.openapi()
    want = set(contract["components"]["schemas"]["UserCreate"]["required"])
    got = set(generated["components"]["schemas"]["UserCreate"].get("required", []))
    assert got == want


def test_login_and_mfa_endpoints_declared():
    generated = app.openapi()
    for path in ("/api/v1/auth/login", "/api/v1/auth/mfa/verify", "/api/v1/auth/jwks"):
        assert path in generated["paths"]
