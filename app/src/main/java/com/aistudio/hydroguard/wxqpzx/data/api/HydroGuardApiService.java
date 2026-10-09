package com.aistudio.hydroguard.wxqpzx.data.api;

import okhttp3.RequestBody;
import okhttp3.ResponseBody;
import retrofit2.Call;
import retrofit2.http.Body;
import retrofit2.http.DELETE;
import retrofit2.http.GET;
import retrofit2.http.HTTP;
import retrofit2.http.PATCH;
import retrofit2.http.POST;
import retrofit2.http.PUT;
import retrofit2.http.Path;
import retrofit2.http.Query;
import retrofit2.http.Streaming;

public interface HydroGuardApiService {
    @GET("api/v1/health") Call<ResponseBody> health();
    @POST("api/v1/auth/bootstrap") Call<ResponseBody> bootstrapAccount();
    @POST("api/v1/auth/development/demo-student-session") Call<ResponseBody> createDemoStudentSession();
    @POST("api/v1/auth/development/demo-admin-session") Call<ResponseBody> createDemoAdminSession();

    @GET("api/v1/nodes/{node_id}") Call<ResponseBody> getNode(@Path("node_id") String nodeId);
    @GET("api/v1/nodes/{node_id}/readings/latest") Call<ResponseBody> getLatestReading(@Path("node_id") String nodeId);
    @GET("api/v1/nodes/{node_id}/readings/history") Call<ResponseBody> getReadingHistory(
            @Path("node_id") String nodeId, @Query("limit") int limit);
    @GET("api/v1/nodes/{node_id}/alerts") Call<ResponseBody> getAlerts(@Path("node_id") String nodeId);
    @PATCH("api/v1/alerts/{alert_id}") Call<ResponseBody> updateAlertStatus(
            @Path("alert_id") int alertId, @Query("status") String status);
    @GET("api/v1/nodes/{node_id}/model-performance") Call<ResponseBody> getModelPerformance(@Path("node_id") String nodeId);
    @POST("api/v1/forecast") Call<ResponseBody> generateForecast(@Body RequestBody body);

    @GET("api/v1/hostel/issues") Call<ResponseBody> getHostelIssues();
    @POST("api/v1/hostel/issues") Call<ResponseBody> createHostelIssue(@Body RequestBody body);
    @GET("api/v1/hostel/issues/{issue_id}/timeline") Call<ResponseBody> getIssueTimeline(@Path("issue_id") String issueId);
    @PATCH("api/v1/hostel/issues/{issue_id}/status") Call<ResponseBody> updateIssueStatus(
            @Path("issue_id") String issueId, @Body RequestBody body);
    @POST("api/v1/hostel/issues/{issue_id}/feedback") Call<ResponseBody> submitIssueFeedback(
            @Path("issue_id") String issueId, @Body RequestBody body);
    @POST("api/v1/hostel/issues/{issue_id}/reopen") Call<ResponseBody> reopenIssue(
            @Path("issue_id") String issueId, @Body RequestBody body);

    @GET("api/v1/hostel/notices") Call<ResponseBody> getNotices();
    @POST("api/v1/hostel/notices") Call<ResponseBody> createNotice(@Body RequestBody body);
    @PUT("api/v1/hostel/notices/{notice_id}") Call<ResponseBody> updateNotice(
            @Path("notice_id") int noticeId, @Body RequestBody body);
    @DELETE("api/v1/hostel/notices/{notice_id}") Call<ResponseBody> deleteNotice(@Path("notice_id") int noticeId);
    @GET("api/v1/hostel/emergency-contacts") Call<ResponseBody> getEmergencyContacts();
    @POST("api/v1/hostel/emergency-contacts") Call<ResponseBody> createEmergencyContact(@Body RequestBody body);
    @PUT("api/v1/hostel/emergency-contacts/{contact_id}") Call<ResponseBody> updateEmergencyContact(
            @Path("contact_id") int contactId, @Body RequestBody body);
    @DELETE("api/v1/hostel/emergency-contacts/{contact_id}") Call<ResponseBody> deleteEmergencyContact(@Path("contact_id") int contactId);
    @GET("api/v1/hostel/lost-found") Call<ResponseBody> getLostFoundItems();
    @POST("api/v1/hostel/lost-found") Call<ResponseBody> createLostFoundItem(@Body RequestBody body);
    @PATCH("api/v1/hostel/lost-found/{item_id}/moderation") Call<ResponseBody> moderateLostFoundItem(
            @Path("item_id") String itemId, @Body RequestBody body);
    @POST("api/v1/hostel/feedback") Call<ResponseBody> submitHostelFeedback(@Body RequestBody body);
    @GET("api/v1/hostel/admin/issues/summary") Call<ResponseBody> getIssueSummary();
    @GET("api/v1/hostel/admin/feedback") Call<ResponseBody> getAdminFeedback();
    @GET("api/v1/hostel/admin/resolution-feedback") Call<ResponseBody> getResolutionFeedback();

    @GET("api/v1/admin/users") Call<ResponseBody> getAdminUsers();
    @POST("api/v1/admin/users/invite") Call<ResponseBody> inviteAdmin(@Body RequestBody body);
    @PATCH("api/v1/admin/users/{user_id}") Call<ResponseBody> updateAdminUser(
            @Path("user_id") int userId, @Body RequestBody body);

    @Streaming @GET("api/v1/research/export.csv") Call<ResponseBody> exportResearchCsv();
}
