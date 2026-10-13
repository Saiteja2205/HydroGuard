"""Canonical configuration for the deployed HydroGuard hostel.

The deployment has exactly **one building, one hostel block and one water
tank**. Every producer of building/block/tank data (seeding, the nodes API,
the configuration endpoint, the Android screens) reads this module instead of
repeating literals, so a future multi-building deployment is a change here
rather than a handful of hardcoded lists scattered across the app.

The structures are expressed as ordered lists with explicit ids and
references precisely so that extension stays a configuration change:

* add an entry to :data:`BUILDINGS` / :data:`BLOCKS` / :data:`TANKS`;
* a tank points at its block, a block at its building;
* :func:`validate` fails loudly on a dangling reference instead of quietly
  rendering a tank under the wrong block.
"""

from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------------
# The deployed campus. Edit these lists to change the topology.
# --------------------------------------------------------------------------

BUILDINGS: list[dict[str, str]] = [
    {"id": "main-building", "name": "Main Hostel Building"},
]

BLOCKS: list[dict[str, str]] = [
    {"id": "main-block", "name": "Hostel Block", "building_id": "main-building"},
]

#: ``node_id`` deliberately matches the existing sensor-node primary key, so
#: the 200-observation development dataset, its forecasts, model errors and
#: ensemble weights keep their foreign keys. Only display metadata changes.
TANKS: list[dict[str, str]] = [
    {
        "id": "main-tank",
        "node_id": "node_overhead_a",
        "name": "Hostel Water Tank",
        "block_id": "main-block",
    },
]

#: The one sensor node that represents the deployed hostel.
CANONICAL_NODE_ID: str = TANKS[0]["node_id"]


def validate() -> None:
    """Reject a configuration that would render the wrong topology."""
    if not BUILDINGS:
        raise ValueError("At least one hostel building must be configured.")
    if not BLOCKS:
        raise ValueError("At least one hostel block must be configured.")
    if not TANKS:
        raise ValueError("At least one water tank must be configured.")

    building_ids = {building["id"] for building in BUILDINGS}
    block_ids = {block["id"] for block in BLOCKS}
    node_ids = [tank["node_id"] for tank in TANKS]

    if len(building_ids) != len(BUILDINGS):
        raise ValueError("Hostel building ids must be unique.")
    if len(block_ids) != len(BLOCKS):
        raise ValueError("Hostel block ids must be unique.")
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("Each water tank must map to a distinct sensor node.")

    for block in BLOCKS:
        if block.get("building_id") not in building_ids:
            raise ValueError(
                f"Hostel block {block['id']!r} references unknown building "
                f"{block.get('building_id')!r}."
            )
    for tank in TANKS:
        if tank.get("block_id") not in block_ids:
            raise ValueError(
                f"Water tank {tank['id']!r} references unknown block {tank.get('block_id')!r}."
            )


def tank_node_ids() -> list[str]:
    """Sensor node ids that represent the deployed hostel tanks."""
    return [tank["node_id"] for tank in TANKS]


def block_name(block_id: str) -> str:
    """Display name of a configured block."""
    for block in BLOCKS:
        if block["id"] == block_id:
            return block["name"]
    raise KeyError(f"Unknown hostel block {block_id!r}.")


def building_name(building_id: str) -> str:
    """Display name of a configured building."""
    for building in BUILDINGS:
        if building["id"] == building_id:
            return building["name"]
    raise KeyError(f"Unknown hostel building {building_id!r}.")


def canonical_node_name() -> str:
    """Display name to use for the deployed sensor node."""
    return TANKS[0]["name"]


def canonical_node_location() -> str:
    """Location label to use for the deployed sensor node."""
    return block_name(TANKS[0]["block_id"])


def configuration_payload(live_nodes: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build the API payload describing the deployed campus.

    ``live_nodes`` optionally maps a tank's ``node_id`` to live fields from the
    nodes table (``status``, ``last_seen``) so a client can render connectivity
    from a single response.
    """
    validate()
    live_nodes = live_nodes or {}

    tanks = []
    for tank in TANKS:
        record: dict[str, Any] = dict(tank)
        record["location"] = block_name(tank["block_id"])
        record["building_id"] = next(
            block["building_id"] for block in BLOCKS if block["id"] == tank["block_id"]
        )
        record.update(live_nodes.get(tank["node_id"], {}))
        tanks.append(record)

    return {
        "buildings": [dict(building) for building in BUILDINGS],
        "blocks": [
            {**block, "building_name": building_name(block["building_id"])}
            for block in BLOCKS
        ],
        "tanks": tanks,
        "counts": {
            "buildings": len(BUILDINGS),
            "blocks": len(BLOCKS),
            "tanks": len(TANKS),
        },
    }


validate()
