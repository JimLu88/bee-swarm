from fastapi.testclient import TestClient
from tachikoma_connection_app import app, identity_payload


def test_identity_does_not_claim_business_dependencies():
    payload = identity_payload()
    assert payload["service"] == "ai-swarm"
    assert payload["ready"] is True
    assert payload["dependencies_ready"] is False
    assert payload["scheduler_started"] is False


def test_decision_and_execution_routes_are_blocked():
    client = TestClient(app)
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/status").status_code == 403
    assert client.post("/api/decision/start").status_code == 403
    assert client.post("/api/sandbox/exec").status_code == 403


def test_contract_is_fail_closed():
    payload = TestClient(app).get("/tachikoma/v1/contract").json()
    assert payload["production_execution_enabled"] is False
    assert payload["upgrade_execution_enabled"] is False
    assert payload["business_actions"][0]["execution_enabled"] is False
