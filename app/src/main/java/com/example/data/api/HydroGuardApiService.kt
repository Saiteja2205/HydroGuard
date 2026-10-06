package com.example.data.api

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.PATCH
import retrofit2.http.Path
import retrofit2.http.Query
import retrofit2.http.PUT
import retrofit2.http.DELETE

interface HydroGuardApiService {
    @GET("api/v1/nodes/{node_id}")
    suspend fun getNodeHealth(@Path("node_id") nodeId: String): Response<NodeHealthResponse>


    @GET("api/v1/nodes/{node_id}/readings/latest")
    suspend fun getLatestReading(
        @Path("node_id") nodeId: String
    ): Response<LatestReadingResponse>

    @GET("api/v1/nodes/{node_id}/readings/history")
    suspend fun getHistoricalReadings(
        @Path("node_id") nodeId: String,
        @Query("limit") limit: Int? = null
    ): Response<HistoryResponse>

    @POST("api/v1/forecast")
    suspend fun generateForecast(
        @Body request: ForecastRequest
    ): Response<ForecastResponse>

    @GET("api/v1/nodes/{node_id}/alerts")
    suspend fun getAlerts(
        @Path("node_id") nodeId: String
    ): Response<AlertListResponse>

    @GET("api/v1/hostel/issues")
    suspend fun getHostelIssues(): Response<List<HostelIssueResponse>>

    @POST("api/v1/hostel/issues")
    suspend fun createHostelIssue(@Body request: CreateIssueRequest): Response<HostelIssueResponse>

    @GET("api/v1/hostel/issues/{issue_id}/timeline")
    suspend fun getIssueTimeline(@Path("issue_id") issueId: String): Response<List<IssueEventResponse>>

    @POST("api/v1/hostel/issues/{issue_id}/feedback")
    suspend fun submitResolutionFeedback(
        @Path("issue_id") issueId: String,
        @Body request: IssueFeedbackRequest
    ): Response<Unit>

    @POST("api/v1/hostel/issues/{issue_id}/reopen")
    suspend fun reopenIssue(
        @Path("issue_id") issueId: String,
        @Body request: IssueReopenRequest
    ): Response<HostelIssueResponse>

    @PATCH("api/v1/hostel/issues/{issue_id}/status")
    suspend fun updateIssueStatus(
        @Path("issue_id") issueId: String,
        @Body request: IssueStatusRequest
    ): Response<HostelIssueResponse>

    @GET("api/v1/hostel/notices")
    suspend fun getHostelNotices(): Response<List<HostelNoticeResponse>>

    @GET("api/v1/hostel/emergency-contacts")
    suspend fun getEmergencyContacts(): Response<List<EmergencyContactResponse>>

    @GET("api/v1/hostel/lost-found")
    suspend fun getLostFoundItems(): Response<List<LostFoundResponse>>

    @POST("api/v1/hostel/lost-found")
    suspend fun createLostFoundItem(@Body request: CreateLostFoundRequest): Response<LostFoundResponse>

    @PATCH("api/v1/hostel/lost-found/{item_id}/moderation")
    suspend fun moderateLostFoundItem(@Path("item_id") itemId: String, @Body request: Map<String, String>): Response<LostFoundResponse>

    @POST("api/v1/hostel/feedback")
    suspend fun submitHostelFeedback(@Body request: HostelFeedbackRequest): Response<Unit>

    @GET("api/v1/hostel/admin/issues/summary")
    suspend fun getIssueSummary(): Response<IssueSummaryResponse>

    @GET("api/v1/hostel/admin/feedback")
    suspend fun getAdminFeedback(): Response<List<HostelFeedbackRecord>>

    @GET("api/v1/hostel/admin/resolution-feedback")
    suspend fun getAdminResolutionFeedback(): Response<List<IssueFeedbackResponse>>

    @POST("api/v1/hostel/notices")
    suspend fun createNotice(@Body request: NoticeCreateRequest): Response<HostelNoticeResponse>

    @PUT("api/v1/hostel/notices/{notice_id}")
    suspend fun updateNotice(@Path("notice_id") noticeId: Int, @Body request: NoticeCreateRequest): Response<HostelNoticeResponse>

    @DELETE("api/v1/hostel/notices/{notice_id}")
    suspend fun deleteNotice(@Path("notice_id") noticeId: Int): Response<Unit>

    @POST("api/v1/hostel/emergency-contacts")
    suspend fun createEmergencyContact(@Body request: EmergencyContactCreateRequest): Response<EmergencyContactResponse>

    @PUT("api/v1/hostel/emergency-contacts/{contact_id}")
    suspend fun updateEmergencyContact(@Path("contact_id") contactId: Int, @Body request: EmergencyContactCreateRequest): Response<EmergencyContactResponse>

    @DELETE("api/v1/hostel/emergency-contacts/{contact_id}")
    suspend fun deleteEmergencyContact(@Path("contact_id") contactId: Int): Response<Unit>

}
