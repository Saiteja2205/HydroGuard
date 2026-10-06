package com.example.data.api

import com.squareup.moshi.Json

data class CreateIssueRequest(
    val category: String,
    val location: String,
    val description: String,
    val severity: String,
    @Json(name = "image_url") val imageUrl: String? = null
)

data class HostelIssueResponse(
    val id: String,
    @Json(name = "reporter_uid") val reporterUid: String,
    val category: String,
    val location: String,
    val description: String,
    val severity: String,
    @Json(name = "image_url") val imageUrl: String?,
    val status: String,
    @Json(name = "assigned_uid") val assignedUid: String?,
    val resolution: String?,
    @Json(name = "created_at") val createdAt: String,
    @Json(name = "updated_at") val updatedAt: String
)

data class IssueEventResponse(
    val id: Int,
    @Json(name = "issue_id") val issueId: String,
    @Json(name = "actor_uid") val actorUid: String,
    @Json(name = "from_status") val fromStatus: String?,
    @Json(name = "to_status") val toStatus: String,
    val comment: String?,
    @Json(name = "created_at") val createdAt: String
)

data class IssueFeedbackRequest(val stars: Int, val comment: String? = null)
data class IssueFeedbackResponse(
    val id: Int,
    @Json(name = "issue_id") val issueId: String,
    @Json(name = "reporter_uid") val reporterUid: String,
    val stars: Int,
    val comment: String?,
    @Json(name = "created_at") val createdAt: String
)
data class IssueReopenRequest(val reason: String)
data class IssueStatusRequest(
    val status: String,
    val comment: String? = null,
    @Json(name = "assigned_uid") val assignedUid: String? = null,
    val resolution: String? = null
)

data class HostelNoticeResponse(
    val id: Int,
    val title: String,
    val body: String,
    val category: String,
    val priority: String,
    @Json(name = "expires_at") val expiresAt: String?,
    @Json(name = "author_uid") val authorUid: String,
    @Json(name = "created_at") val createdAt: String
)

data class EmergencyContactResponse(
    val id: Int,
    val category: String,
    val name: String,
    val phone: String,
    val details: String?,
    val active: Boolean,
    val verified: Boolean = false,
    @Json(name = "updated_by") val updatedBy: String,
    @Json(name = "updated_at") val updatedAt: String
)

data class HostelEventResponse(
    val id: Int,
    val name: String,
    @Json(name = "starts_at") val startsAt: String,
    val location: String,
    val description: String,
    val organizer: String,
    @Json(name = "author_uid") val authorUid: String,
    @Json(name = "created_at") val createdAt: String
)

data class CreateLostFoundRequest(
    val kind: String,
    val title: String,
    val description: String,
    val category: String,
    @Json(name = "image_url") val imageUrl: String? = null,
    val location: String,
    @Json(name = "item_date") val itemDate: String
)

data class LostFoundResponse(
    val id: String,
    @Json(name = "reporter_uid") val reporterUid: String,
    val kind: String,
    val title: String,
    val description: String,
    val category: String,
    @Json(name = "image_url") val imageUrl: String?,
    val location: String,
    @Json(name = "item_date") val itemDate: String,
    @Json(name = "moderation_status") val moderationStatus: String,
    @Json(name = "created_at") val createdAt: String
)

data class HostelFeedbackRequest(val category: String, val rating: Int, val comment: String? = null)
data class HostelFeedbackRecord(
    val id: Int,
    @Json(name = "reporter_uid") val reporterUid: String,
    val category: String,
    val rating: Int,
    val comment: String?,
    @Json(name = "created_at") val createdAt: String
)

data class EventCreateRequest(
    val name: String,
    @Json(name = "starts_at") val startsAt: String,
    val location: String,
    val description: String,
    val organizer: String
)

data class NoticeCreateRequest(
    val title: String,
    val body: String,
    val category: String,
    val priority: String,
    @Json(name = "expires_at") val expiresAt: String? = null
)

data class EmergencyContactCreateRequest(
    val category: String,
    val name: String,
    val phone: String,
    val details: String? = null,
    val active: Boolean = true,
    val verified: Boolean = false
)

data class IssueSummaryResponse(
    val total: Int,
    @Json(name = "by_status") val byStatus: Map<String, Int>,
    @Json(name = "by_category") val byCategory: Map<String, Int>
)
