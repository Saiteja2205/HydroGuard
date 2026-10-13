"""The deployed hostel is one building, one block and one water tank.

These tests pin the canonical configuration end to end: the topology module,
the seed scripts, the student node listing and the configuration endpoint must
all describe the same single-tank deployment rather than the retired
"Overhead Tank B" / "Mess Ground Water" examples that used to ship.
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient

from app.core.auth import authenticated_principal
from app.core.hostel_config import (
    BLOCKS,
    BUILDINGS,
    CANONICAL_NODE_ID,
    TANKS,
    block_name,
    canonical_node_location,
    canonical_node_name,
    configuration_payload,
    tank_node_ids,
    validate,
)
from app.db.database import get_db_context, init_db
from app.db.repositories import NodeRepository
from app.db.seed import seed_devices
from app.main import app

#: Example tanks the old demo seeder created for blocks that do not exist here.
RETIRED_NODE_IDS = {"node_overhead_b", "node_mess_ground"}
RETIRED_LABELS = {"Overhead Tank B", "Mess Ground Water", "Hostel Block B", "Mess Area"}


def _client(monkeypatch, uid: str = "hostel-config", role: str = "STUDENT") -> TestClient:
    init_db()
    monkeypatch.setitem(
        app.dependency_overrides,
        authenticated_principal,
        lambda: {"uid": uid, "role": role},
    )
    return TestClient(app)


def test_deployment_is_one_building_one_block_one_tank():
    """The configuration module must not drift into a multi-block layout."""
    validate()  # raises on a dangling block/building/tank reference
    assert len(BUILDINGS) == 1, BUILDINGS
    assert len(BLOCKS) == 1, BLOCKS
    assert len(TANKS) == 1, TANKS
    assert len(tank_node_ids()) == 1, tank_node_ids()


def test_tank_uses_the_approved_display_name():
    """Sensible display names, with the node id that keeps history intact."""
    assert canonical_node_name() == "Hostel Water Tank"
    assert canonical_node_location() == BLOCKS[0]["name"]
    # Renaming the node id would orphan 201 readings and 62 forecasts.
    assert TANKS[0]["node_id"] == "node_overhead_a"


def test_every_tank_resolves_its_block_and_building():
    """A tank must never resolve to a block that does not exist."""
    block_ids = {block["id"] for block in BLOCKS}
    building_ids = {building["id"] for building in BUILDINGS}

    for tank in TANKS:
        assert tank["block_id"] in block_ids, tank
    for block in BLOCKS:
        assert block["building_id"] in building_ids, block

    payload = configuration_payload()
    assert payload["counts"] == {"buildings": 1, "blocks": 1, "tanks": 1}
    assert payload["tanks"][0]["location"] == block_name(TANKS[0]["block_id"])
    assert payload["tanks"][0]["building_id"] in building_ids
    assert payload["blocks"][0]["building_name"] == BUILDINGS[0]["name"]


def test_seed_creates_only_the_deployed_tank():
    """The seed scripts must reflect the real hostel, not three examples."""
    init_db()
    with get_db_context() as db:
        seeded = seed_devices(db)
    assert list(seeded) == tank_node_ids(), seeded

    with get_db_context() as db:
        node = NodeRepository.get_by_node_id(db, CANONICAL_NODE_ID)
        assert node is not None, "the deployed tank must exist after seeding"
        assert node.name == canonical_node_name(), node.name
        assert node.location == canonical_node_location(), node.location


def test_node_listing_never_shows_the_retired_example_tanks(monkeypatch):
    """Students pick from the deployed tank only."""
    client = _client(monkeypatch)
    with get_db_context() as db:
        seed_devices(db)

    listed = client.get("/api/v1/nodes")
    assert listed.status_code == 200, listed.text
    nodes = listed.json()["nodes"]

    ids = {node["node_id"] for node in nodes}
    assert CANONICAL_NODE_ID in ids, ids
    assert not ids & RETIRED_NODE_IDS, ids

    labels = {node["name"] for node in nodes} | {node["location"] for node in nodes}
    assert not labels & RETIRED_LABELS, labels


def test_configuration_endpoint_requires_authentication():
    """Deployment details are only served to a signed-in principal."""
    init_db()
    response = TestClient(app).get("/api/v1/hostel/configuration")
    assert response.status_code == 401, (
        f"unauthenticated configuration request returned {response.status_code}: {response.text}"
    )


def test_configuration_endpoint_returns_the_deployment(monkeypatch):
    """Backend responses describe one building, one block, one tank."""
    client = _client(monkeypatch)
    with get_db_context() as db:
        seed_devices(db)

    response = client.get("/api/v1/hostel/configuration")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["counts"] == {"buildings": 1, "blocks": 1, "tanks": 1}
    assert [building["name"] for building in payload["buildings"]] == ["Main Hostel Building"]
    assert [block["name"] for block in payload["blocks"]] == ["Hostel Block"]

    tank = payload["tanks"][0]
    assert tank["node_id"] == CANONICAL_NODE_ID
    assert tank["name"] == "Hostel Water Tank"
    assert tank["location"] == "Hostel Block"
    assert tank["block_id"] == payload["blocks"][0]["id"]
    assert tank["building_id"] == payload["buildings"][0]["id"]
    assert tank["status"] in {"online", "offline", "maintenance"}, tank["status"]
    assert "last_seen" in tank, "the screen renders connectivity from this field"
