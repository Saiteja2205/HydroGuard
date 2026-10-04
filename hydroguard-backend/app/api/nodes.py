"""Nodes API endpoints for HydroGuard."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.auth import require_roles
from app.db.repositories import NodeRepository
from app.schemas.nodes import Node, NodeCreate, NodeListResponse

router = APIRouter(tags=["nodes"])


@router.get("/nodes", response_model=NodeListResponse)
def list_nodes(
    limit: Optional[int] = Query(None, ge=1, le=1000, description="Maximum number of nodes to return"),
    db: Session = Depends(get_db),
) -> NodeListResponse:
    """List all nodes."""
    nodes = NodeRepository.list_all(db)
    if limit:
        nodes = nodes[:limit]
    return NodeListResponse(nodes=nodes, count=len(nodes))


@router.get("/nodes/{node_id}", response_model=Node)
def get_node(
    node_id: str = Path(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Node identifier",
    ),
    db: Session = Depends(get_db),
) -> Node:
    """Get a node by ID."""
    node = NodeRepository.get_by_node_id(db, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    return node


@router.post("/nodes", response_model=Node)
def create_node(node_data: NodeCreate, db: Session = Depends(get_db), principal: dict = Depends(require_roles("ADMIN"))) -> Node:
    """Create a new node."""
    # Check if node already exists
    existing = NodeRepository.get_by_node_id(db, node_data.node_id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Node {node_data.node_id} already exists")

    node = NodeRepository.create(
        db=db,
        node_id=node_data.node_id,
        name=node_data.name,
        location=node_data.location,
        status=node_data.status,
    )
    return node


@router.patch("/nodes/{node_id}/status")
def update_node_status(
    node_id: str = Path(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Node identifier",
    ),
    status: str = Query(..., regex="^(online|offline|maintenance)$", description="New status"),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles("ADMIN")),
) -> dict:
    """Update node status."""
    node = NodeRepository.update_status(db, node_id, status)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    return {"node_id": node_id, "status": status, "updated": True}
