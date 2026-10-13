"""Student-facing node lists must exclude development test/contract fixtures."""

from fastapi.testclient import TestClient

from app.db.database import get_db_context, init_db
from app.db.repositories import NodeRepository
from app.main import app


def test_list_nodes_hides_test_and_contract_fixtures(authenticated_client):
    init_db()
    with get_db_context() as db:
        NodeRepository.get_or_create(db, "node_overhead_a", "Overhead Tank A", "Hostel Block A")
        NodeRepository.get_or_create(db, "test_node_9", "Test Node 9", "Test Location")
        NodeRepository.get_or_create(db, "contract_deadbeef", "Contract node", "Test")

    client = authenticated_client

    listed = client.get("/api/v1/nodes")
    assert listed.status_code == 200
    ids = {node["node_id"] for node in listed.json()["nodes"]}
    assert "node_overhead_a" in ids
    assert not any(node_id.startswith(("test_", "contract_")) for node_id in ids), ids

    with_fixtures = client.get("/api/v1/nodes?include_fixtures=true")
    fixture_ids = {node["node_id"] for node in with_fixtures.json()["nodes"]}
    assert "test_node_9" in fixture_ids
    assert "contract_deadbeef" in fixture_ids
