from fastapi import FastAPI

from app.openapi import generate_openapi_spec


def test_gen_openapi(fastapi_app: FastAPI):
    spec = generate_openapi_spec(fastapi_app)
    assert "## Available RQL filters" in spec["paths"]["/accounts"]["get"]["description"]
