"""Authenticated student hostel services backed by SQLite records."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import authenticated_principal, require_roles, require_student_or_admin
from app.core.hostel_config import configuration_payload, tank_node_ids
from app.core.storage import (
    MAX_IMAGE_BYTES,
    StorageConfigurationError,
    UnsupportedImageError,
    create_storage_driver,
    detect_image_type,
)
from app.db import get_db
from app.db.hostel_models import (
    EmergencyContact,
    HostelFeedback,
    HostelIssue,
    HostelNotice,
    IssueEvent,
    IssueFeedback,
    LostFoundItem,
)
from app.db.repositories import NodeRepository
from app.schemas.hostel import (
    HOSTEL_PHOTO_PATH_PREFIX,
    EmergencyContactCreate,
    EmergencyContactRecord,
    HostelFeedbackCreate,
    HostelFeedbackRecord,
    IssueCreate,
    IssueEventRecord,
    IssueFeedbackCreate,
    IssueFeedbackRecord,
    IssueRecord,
    IssueReopen,
    IssueStatusChange,
    LostFoundCreate,
    LostFoundModeration,
    LostFoundPhotoUpload,
    LostFoundRecord,
    NoticeCreate,
    NoticeRecord,
)

router = APIRouter(prefix="/hostel", tags=["hostel-services"])

# The complete issue lifecycle. SUBMITTED is the initial "open" state created by
# POST /issues; WAITING parks an issue while an admin waits on a resident, a
# spare part or a clarification; CLOSED is reopenable through the dedicated
# reopen endpoint as well as the PATCH transition below.
ISSUE_TRANSITIONS: dict[str, set[str]] = {
    "SUBMITTED": {"ACKNOWLEDGED", "IN_PROGRESS", "WAITING"},
    "ACKNOWLEDGED": {"ASSIGNED", "IN_PROGRESS", "WAITING"},
    "ASSIGNED": {"IN_PROGRESS", "WAITING"},
    "IN_PROGRESS": {"RESOLVED", "WAITING"},
    "WAITING": {"ACKNOWLEDGED", "ASSIGNED", "IN_PROGRESS", "RESOLVED"},
    "RESOLVED": {"CLOSED", "REOPENED"},
    "CLOSED": {"REOPENED"},
    "REOPENED": {"ACKNOWLEDGED", "ASSIGNED", "IN_PROGRESS", "WAITING"},
}

# Statuses from which a fresh issue can be re-opened by the reporter/admin.
REOPENABLE_STATUSES = frozenset({"RESOLVED", "CLOSED"})

# Presentation order used when offering the admin the next actions to take.
# The productive next step comes before the parked/exceptional one, so an
# in-progress issue offers "Resolve" before "Wait".
ISSUE_STATUS_ORDER = (
    "ACKNOWLEDGED",
    "ASSIGNED",
    "IN_PROGRESS",
    "RESOLVED",
    "WAITING",
    "CLOSED",
    "REOPENED",
)

# Human-readable labels. SUBMITTED is the persisted name for an opened issue;
# clients display it as "Open" so the lifecycle reads the way staff speak.
ISSUE_STATUS_LABELS = {
    "SUBMITTED": "Open",
    "ACKNOWLEDGED": "Acknowledged",
    "ASSIGNED": "Assigned",
    "IN_PROGRESS": "In progress",
    "WAITING": "Waiting",
    "RESOLVED": "Resolved",
    "CLOSED": "Closed",
    "REOPENED": "Reopened",
}


def valid_next_statuses(current: str) -> list[str]:
    """Ordered list of statuses reachable from ``current``."""
    return [status for status in ISSUE_STATUS_ORDER if status in ISSUE_TRANSITIONS.get(current, set())]


def _issue_or_404(db: Session, issue_id: str) -> HostelIssue:
    issue = db.get(HostelIssue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found.")
    return issue


def _own_or_admin(issue: HostelIssue, principal: dict) -> None:
    if principal.get("role", "").upper() != "ADMIN" and issue.reporter_uid != principal.get("uid"):
        raise HTTPException(status_code=404, detail="Issue not found.")


def _must_own(issue: HostelIssue, principal: dict) -> None:
    if issue.reporter_uid != principal.get("uid"):
        raise HTTPException(status_code=404, detail="Issue not found.")


def _event(db: Session, issue: HostelIssue, principal: dict, to_status: str, comment: str | None = None) -> None:
    db.add(IssueEvent(
        issue_id=issue.id,
        actor_uid=str(principal["uid"]),
        from_status=issue.status,
        to_status=to_status,
        comment=comment,
    ))
    issue.status = to_status
    issue.updated_at = datetime.now(timezone.utc)


@router.get("/configuration")
def hostel_configuration(
    _: dict = Depends(authenticated_principal),
    db: Session = Depends(get_db),
) -> dict:
    """Describe the deployed campus: one building, one block, one water tank.

    This is the single authoritative answer to "what is deployed", so student
    screens, admin screens and other clients all render the same topology
    instead of each carrying its own list of example tanks.
    """
    live_nodes = {}
    for node_id in tank_node_ids():
        node = NodeRepository.get_by_node_id(db, node_id)
        if node is not None:
            live_nodes[node_id] = {"status": node.status, "last_seen": node.last_seen}
    return configuration_payload(live_nodes)


@router.get("/issues/workflow")
def issue_workflow(
    _: dict = Depends(authenticated_principal),
) -> dict:
    """Authoritative issue lifecycle: statuses, transition graph and labels.

    Clients render their next-action buttons from this payload so the UI can
    never offer a transition the backend would reject with 409.
    """
    return {
        "initial_status": "SUBMITTED",
        "statuses": [*(s for s in ISSUE_STATUS_ORDER if s != "REOPENED"), "REOPENED"],
        "transitions": {status: sorted(targets) for status, targets in ISSUE_TRANSITIONS.items()},
        "labels": ISSUE_STATUS_LABELS,
        "open_label": "SUBMITTED",
        "reopenable": sorted(REOPENABLE_STATUSES),
        "requires": {
            "resolution": ["RESOLVED"],
            "assigned_uid": ["ASSIGNED"],
        },
        "optional_comment": ["WAITING", "REOPENED", "ACKNOWLEDGED", "IN_PROGRESS", "CLOSED"],
    }


@router.post("/issues", response_model=IssueRecord, status_code=201)
def create_issue(
    payload: IssueCreate,
    principal: dict = Depends(require_student_or_admin),
    db: Session = Depends(get_db),
) -> HostelIssue:
    issue = HostelIssue(**payload.model_dump(), reporter_uid=str(principal["uid"]))
    db.add(issue)
    db.flush()
    db.add(IssueEvent(issue_id=issue.id, actor_uid=str(principal["uid"]), to_status="SUBMITTED", comment="Report submitted"))
    db.commit()
    db.refresh(issue)
    return issue


@router.get("/issues", response_model=list[IssueRecord])
def list_issues(
    status: str | None = Query(default=None, max_length=24),
    principal: dict = Depends(authenticated_principal),
    db: Session = Depends(get_db),
) -> list[HostelIssue]:
    query = db.query(HostelIssue)
    if principal.get("role", "").upper() != "ADMIN":
        query = query.filter(HostelIssue.reporter_uid == str(principal["uid"]))
    if status:
        query = query.filter(HostelIssue.status == status.upper())
    return query.order_by(HostelIssue.created_at.desc()).limit(500).all()


@router.get("/issues/{issue_id}", response_model=IssueRecord)
def get_issue(
    issue_id: str = Path(..., min_length=36, max_length=36),
    principal: dict = Depends(authenticated_principal),
    db: Session = Depends(get_db),
) -> HostelIssue:
    issue = _issue_or_404(db, issue_id)
    _own_or_admin(issue, principal)
    return issue


@router.get("/issues/{issue_id}/timeline", response_model=list[IssueEventRecord])
def get_issue_timeline(
    issue_id: str = Path(..., min_length=36, max_length=36),
    principal: dict = Depends(authenticated_principal),
    db: Session = Depends(get_db),
) -> list[IssueEvent]:
    issue = _issue_or_404(db, issue_id)
    _own_or_admin(issue, principal)
    return db.query(IssueEvent).filter_by(issue_id=issue_id).order_by(IssueEvent.created_at.asc()).all()


@router.patch("/issues/{issue_id}/status", response_model=IssueRecord)
def update_issue_status(
    payload: IssueStatusChange,
    issue_id: str = Path(..., min_length=36, max_length=36),
    principal: dict = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
) -> HostelIssue:
    issue = _issue_or_404(db, issue_id)
    observed = issue.status
    if payload.status == observed:
        # A repeated tap of the same action is a no-op, not a new event.
        raise HTTPException(
            status_code=409,
            detail=f"Issue is already {observed}; no status change to apply.",
        )
    if payload.status not in ISSUE_TRANSITIONS.get(observed, set()):
        raise HTTPException(status_code=409, detail=f"Invalid issue transition: {observed} → {payload.status}.")
    if payload.status == "ASSIGNED" and not payload.assigned_uid:
        raise HTTPException(status_code=422, detail="assigned_uid is required when assigning an issue.")
    if payload.status == "RESOLVED" and not payload.resolution:
        raise HTTPException(status_code=422, detail="A resolution summary is required to resolve an issue.")
    # Optimistic concurrency guard: another request may have moved the issue
    # between the read above and this write. Re-read before mutating so a
    # duplicate/interleaved request cannot record two conflicting events.
    current = db.query(HostelIssue.status).filter(HostelIssue.id == issue_id).scalar()
    if current != observed:
        raise HTTPException(
            status_code=409,
            detail=f"Issue status changed while saving ({observed} → {current}); reload and try again.",
        )
    if payload.assigned_uid is not None:
        issue.assigned_uid = payload.assigned_uid
    if payload.resolution is not None:
        issue.resolution = payload.resolution
    _event(db, issue, principal, payload.status, payload.comment)
    db.commit()
    db.refresh(issue)
    return issue


@router.post("/issues/{issue_id}/feedback", response_model=IssueFeedbackRecord, status_code=201)
def rate_resolution(
    payload: IssueFeedbackCreate,
    issue_id: str = Path(..., min_length=36, max_length=36),
    principal: dict = Depends(require_student_or_admin),
    db: Session = Depends(get_db),
) -> IssueFeedback:
    issue = _issue_or_404(db, issue_id)
    _must_own(issue, principal)
    if issue.status not in {"RESOLVED", "CLOSED"}:
        raise HTTPException(status_code=409, detail="Resolution feedback is available after an issue is resolved.")
    if db.query(IssueFeedback.id).filter_by(issue_id=issue_id).first():
        raise HTTPException(status_code=409, detail="Resolution feedback has already been submitted.")
    record = IssueFeedback(issue_id=issue_id, reporter_uid=str(principal["uid"]), **payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.post("/issues/{issue_id}/reopen", response_model=IssueRecord)
def reopen_issue(
    payload: IssueReopen,
    issue_id: str = Path(..., min_length=36, max_length=36),
    principal: dict = Depends(require_student_or_admin),
    db: Session = Depends(get_db),
) -> HostelIssue:
    issue = _issue_or_404(db, issue_id)
    # The reporter may reopen their own complaint; an administrator may reopen
    # any complaint. Students still cannot touch someone else's issue.
    _own_or_admin(issue, principal)
    if issue.status not in REOPENABLE_STATUSES:
        raise HTTPException(status_code=409, detail="Only a resolved or closed issue can be reopened.")
    _event(db, issue, principal, "REOPENED", payload.reason)
    db.commit()
    db.refresh(issue)
    return issue


@router.get("/admin/issues/summary")
def issue_summary(
    _: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)
) -> dict:
    totals = dict(db.query(HostelIssue.status, func.count(HostelIssue.id)).group_by(HostelIssue.status).all())
    categories = dict(db.query(HostelIssue.category, func.count(HostelIssue.id)).group_by(HostelIssue.category).all())
    return {"total": sum(totals.values()), "by_status": totals, "by_category": categories}


@router.get("/admin/resolution-feedback", response_model=list[IssueFeedbackRecord])
def list_resolution_feedback(
    _: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)
) -> list[IssueFeedback]:
    return db.query(IssueFeedback).order_by(IssueFeedback.created_at.desc()).limit(1000).all()


@router.get("/notices", response_model=list[NoticeRecord])
def list_notices(_: dict = Depends(authenticated_principal), db: Session = Depends(get_db)) -> list[HostelNotice]:
    now = datetime.now(timezone.utc)
    return db.query(HostelNotice).filter((HostelNotice.expires_at.is_(None)) | (HostelNotice.expires_at > now)).order_by(HostelNotice.created_at.desc()).limit(200).all()


@router.post("/notices", response_model=NoticeRecord, status_code=201)
def create_notice(payload: NoticeCreate, principal: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)) -> HostelNotice:
    row = HostelNotice(**payload.model_dump(), author_uid=str(principal["uid"]))
    db.add(row); db.commit(); db.refresh(row)
    return row


@router.put("/notices/{notice_id}", response_model=NoticeRecord)
def edit_notice(payload: NoticeCreate, notice_id: int, principal: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)) -> HostelNotice:
    row = db.get(HostelNotice, notice_id)
    if row is None: raise HTTPException(404, "Notice not found.")
    for key, value in payload.model_dump().items(): setattr(row, key, value)
    db.commit(); db.refresh(row)
    return row


@router.delete("/notices/{notice_id}", status_code=204)
def delete_notice(notice_id: int, principal: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)) -> Response:
    row = db.get(HostelNotice, notice_id)
    if row is None: raise HTTPException(404, "Notice not found.")
    db.delete(row); db.commit()
    return Response(status_code=204)


@router.get("/emergency-contacts", response_model=list[EmergencyContactRecord])
def list_emergency_contacts(principal: dict = Depends(authenticated_principal), db: Session = Depends(get_db)) -> list[EmergencyContact]:
    query = db.query(EmergencyContact).filter(
        EmergencyContact.active.is_(True),
        func.upper(EmergencyContact.category).in_(("WARDEN", "SECURITY")),
    )
    if principal.get("role", "").upper() != "ADMIN":
        query = query.filter_by(verified=True)
    return query.order_by(EmergencyContact.category.asc()).all()


@router.post("/emergency-contacts", response_model=EmergencyContactRecord, status_code=201)
def create_emergency_contact(payload: EmergencyContactCreate, principal: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)) -> EmergencyContact:
    row = EmergencyContact(**payload.model_dump(), updated_by=str(principal["uid"]))
    db.add(row); db.commit(); db.refresh(row)
    return row


@router.put("/emergency-contacts/{contact_id}", response_model=EmergencyContactRecord)
def edit_emergency_contact(payload: EmergencyContactCreate, contact_id: int, principal: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)) -> EmergencyContact:
    row = db.get(EmergencyContact, contact_id)
    if row is None: raise HTTPException(404, "Emergency contact not found.")
    for key, value in payload.model_dump().items(): setattr(row, key, value)
    row.updated_by = str(principal["uid"])
    db.commit(); db.refresh(row)
    return row


@router.delete("/emergency-contacts/{contact_id}", status_code=204)
def delete_emergency_contact(contact_id: int, principal: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)) -> Response:
    row = db.get(EmergencyContact, contact_id)
    if row is None: raise HTTPException(404, "Emergency contact not found.")
    row.active = False; row.updated_by = str(principal["uid"])
    db.commit()
    return Response(status_code=204)


@router.get("/lost-found", response_model=list[LostFoundRecord])
def list_lost_found(principal: dict = Depends(authenticated_principal), db: Session = Depends(get_db)) -> list[LostFoundItem]:
    query = db.query(LostFoundItem)
    if principal.get("role", "").upper() == "ADMIN":
        query = query.filter(LostFoundItem.moderation_status == "PENDING")
    else:
        query = query.filter((LostFoundItem.moderation_status == "APPROVED") | (LostFoundItem.reporter_uid == str(principal["uid"])))
    return query.order_by(LostFoundItem.created_at.desc()).limit(500).all()


@router.post("/lost-found", response_model=LostFoundRecord, status_code=201)
def create_lost_found(payload: LostFoundCreate, principal: dict = Depends(require_student_or_admin), db: Session = Depends(get_db)) -> LostFoundItem:
    """Create a lost/found report, collapsing an identical repeat submission.

    A double-tapped submit button must not leave two identical cards behind: an
    unchanged duplicate from the same reporter returns the original record.
    """
    fields = payload.model_dump()
    duplicate = (
        db.query(LostFoundItem)
        .filter(
            LostFoundItem.reporter_uid == str(principal["uid"]),
            LostFoundItem.kind == fields["kind"],
            LostFoundItem.title == fields["title"],
            LostFoundItem.location == fields["location"],
            LostFoundItem.item_date == fields["item_date"],
            LostFoundItem.moderation_status != "REMOVED",
        )
        .order_by(LostFoundItem.created_at.desc())
        .first()
    )
    if duplicate is not None:
        return duplicate
    row = LostFoundItem(**fields, reporter_uid=str(principal["uid"]), moderation_status="PENDING")
    db.add(row); db.commit(); db.refresh(row)
    return row


@router.patch("/lost-found/{item_id}/moderation", response_model=LostFoundRecord)
def moderate_lost_found(payload: LostFoundModeration, item_id: str, _: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)) -> LostFoundItem:
    row = db.get(LostFoundItem, item_id)
    if row is None: raise HTTPException(404, "Lost and found item not found.")
    row.moderation_status = payload.moderation_status
    db.commit(); db.refresh(row)
    return row


def _photographs():
    """Resolve the configured photograph driver, surfacing a misconfiguration."""
    try:
        return create_storage_driver()
    except StorageConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def _upload_too_large_detail() -> str:
    return f"Photographs must be {MAX_IMAGE_BYTES // (1024 * 1024)} MB or smaller."


@router.post("/lost-found/photos", response_model=LostFoundPhotoUpload, status_code=201)
async def upload_lost_found_photo(request: Request, _: dict = Depends(require_student_or_admin)):
    """Store one photograph and return the reference to attach to a listing.

    The raw bytes are the request body, so neither the client's filename nor
    its declared Content-Type can influence what is stored: the format is
    decided from the leading magic bytes and the storage key is generated
    server-side as an opaque UUID.
    """
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail=_upload_too_large_detail())

    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail=_upload_too_large_detail())
    data = bytes(payload)

    if not data:
        raise HTTPException(status_code=422, detail="The uploaded photograph was empty.")
    if detect_image_type(data) is None:
        raise HTTPException(
            status_code=415,
            detail=(
                "Only JPEG, PNG, WebP or GIF photographs can be stored; the "
                "uploaded bytes were not one of those formats."
            ),
        )
    try:
        stored = _photographs().store(data)
    except UnsupportedImageError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    return {"image_url": HOSTEL_PHOTO_PATH_PREFIX + stored.key}


@router.get("/lost-found/photos/{key}")
def read_lost_found_photo(key: str, _: dict = Depends(authenticated_principal)):
    """Serve a stored photograph to a signed-in user.

    The key is an unguessable UUID and the route is authenticated, so a
    pending listing's photograph cannot be fetched anonymously or by guessing.
    """
    stored = _photographs().load(key)
    if stored is None:
        raise HTTPException(status_code=404, detail="Photograph not found.")
    return Response(
        content=stored.data,
        media_type=stored.content_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/feedback", response_model=HostelFeedbackRecord, status_code=201)
def create_hostel_feedback(payload: HostelFeedbackCreate, principal: dict = Depends(require_student_or_admin), db: Session = Depends(get_db)) -> HostelFeedback:
    row = HostelFeedback(**payload.model_dump(), reporter_uid=str(principal["uid"]))
    db.add(row); db.commit(); db.refresh(row)
    return row


@router.get("/admin/feedback", response_model=list[HostelFeedbackRecord])
def list_hostel_feedback(_: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)) -> list[HostelFeedback]:
    return db.query(HostelFeedback).order_by(HostelFeedback.created_at.desc()).limit(1000).all()
