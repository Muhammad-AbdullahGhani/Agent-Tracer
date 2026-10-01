import pytest
from fastapi.testclient import TestClient
from agenttrace.api.server import app
from agenttrace.db import init_db

@pytest.fixture(autouse=True)
def setup_db():
    init_db()

@pytest.fixture
def client():
    return TestClient(app)

def test_api_stats(client):
    res = client.get("/api/stats")
    assert res.status_code == 200
    data = res.json()
    assert "total_traces" in data
    assert "deterministic_count" in data
    assert "failure_buckets" in data

def test_api_traces_list(client):
    res = client.get("/api/traces")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

def test_api_incidents_list(client):
    res = client.get("/api/incidents")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

def test_api_regression_fixtures(client):
    res = client.get("/api/regression/fixtures")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
