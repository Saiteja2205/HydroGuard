"""Authenticated student hostel services backed by SQLite records."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import authenticated_principal, require_roles, require_student_or_admin
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
from app.schemas.hostel import (
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
    LostFoundRecord,
    NoticeCreate,
    NoticeRecord,
)

router = APIRouter(prefix="/hostel", tags=["hostel-services"])
ISSUE_TRANSITIONS = {
    "SUBMITTED": {"ACKNOWLEDGED"},
    "ACKNOWLEDGED": {"ASSIGNED", "IN_PROGRESS"},
    "ASSIGNED": {"IN_PROGRESS"},
    "IN_PROGRESS": {"RESOLVED"},
    "RESOLVED": {"CLOSED"},
    "CLOSED": set(),
    "REOPENED": {"ACKNOWLEDGED", "ASSIGNED", "IN_PROGRESS"},
}


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
    if payload.status not in ISSUE_TRANSITIONS.get(issue.status, set()):
        raise HTTPException(status_code=409, detail=f"Invalid issue transition: {issue.status} → {payload.status}.")
    if payload.status == "ASSIGNED" and not payload.assigned_uid:
        raise HTTPException(status_code=422, detail="assigned_uid is required when assigning an issue.")
    if payload.status == "RESOLVED" and not payload.resolution:
        raise HTTPException(status_code=422, detail="A resolution summary is required to resolve an issue.")
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
    _must_own(issue, principal)
    if issue.status not in {"RESOLVED", "CLOSED"}:
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
    row = LostFoundItem(**payload.model_dump(), reporter_uid=str(principal["uid"]), moderation_status="PENDING")
    db.add(row); db.commit(); db.refresh(row)
    return row


@router.patch("/lost-found/{item_id}/moderation", response_model=LostFoundRecord)
def moderate_lost_found(payload: LostFoundModeration, item_id: str, _: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)) -> LostFoundItem:
    row = db.get(LostFoundItem, item_id)
    if row is None: raise HTTPException(404, "Lost and found item not found.")
    row.moderation_status = payload.moderation_status
    db.commit(); db.refresh(row)
    return row


@router.post("/feedback", response_model=HostelFeedbackRecord, status_code=201)
def create_hostel_feedback(payload: HostelFeedbackCreate, principal: dict = Depends(require_student_or_admin), db: Session = Depends(get_db)) -> HostelFeedback:
    row = HostelFeedback(**payload.model_dump(), reporter_uid=str(principal["uid"]))
    db.add(row); db.commit(); db.refresh(row)
    return row


@router.get("/admin/feedback", response_model=list[HostelFeedbackRecord])
def list_hostel_feedback(_: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)) -> list[HostelFeedback]:
    return db.query(HostelFeedback).order_by(HostelFeedback.created_at.desc()).limit(1000).all()
