package com.aistudio.hydroguard.wxqpzx.data.api;

import android.util.Log;

import com.aistudio.hydroguard.wxqpzx.BuildConfig;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.IOException;
import java.net.UnknownHostException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

import okhttp3.MediaType;
import okhttp3.RequestBody;
import okhttp3.ResponseBody;
import retrofit2.Call;
import retrofit2.Response;

public class ApiRepository {
    public static final int FORECAST_MIN_HISTORY = 30;
    private static final MediaType JSON = MediaType.get("application/json; charset=utf-8");
    private final HydroGuardApiService api = RetrofitClient.api();

    /** Hands a fetched photograph back as raw bytes plus the media type the server declared. */
    public interface PhotoCallback {
        void onPhoto(byte[] bytes, String contentType);

        void onFailure(ApiFailure failure);
    }

    /**
     * Photographs are fetched with {@code .execute()} on this pool rather than
     * through {@code enqueue}, so both the socket read and the body decode stay
     * off the main thread — the same failure that produced
     * {@code NetworkOnMainThreadException} in the CSV export path.
     */
    private static final java.util.concurrent.ExecutorService PHOTO_EXECUTOR =
            java.util.concurrent.Executors.newFixedThreadPool(2);

    private final android.os.Handler mainHandler =
            new android.os.Handler(android.os.Looper.getMainLooper());

    public interface ForecastCallback extends ApiCallback { }

    public void checkHealth(ApiCallback callback) {
        enqueue(api.health(), "/api/v1/health", callback);
    }

    public void bootstrapAccount(ApiCallback callback) {
        enqueue(api.bootstrapAccount(), "/api/v1/auth/bootstrap", callback);
    }

    public void getLatestReading(String nodeId, ApiCallback callback) {
        enqueue(api.getLatestReading(nodeId), "/api/v1/nodes/" + nodeId + "/readings/latest", callback);
    }

    public void getReadingHistory(String nodeId, int limit, ApiCallback callback) {
        enqueue(api.getReadingHistory(nodeId, limit), "/api/v1/nodes/" + nodeId + "/readings/history", callback);
    }

    public void getAlerts(String nodeId, ApiCallback callback) {
        enqueue(api.getAlerts(nodeId), "/api/v1/nodes/" + nodeId + "/alerts", callback);
    }
    public void updateAlertStatus(int id, String status, ApiCallback callback) {
        enqueue(api.updateAlertStatus(id, status), "/api/v1/alerts/" + id, callback);
    }

    public void getNodes(ApiCallback callback) {
        enqueue(api.getNodes(), "/api/v1/nodes", callback);
    }

    /** The authoritative deployment: one building, one block, one water tank. */
    public void getHostelConfiguration(ApiCallback callback) {
        enqueue(api.getHostelConfiguration(), "/api/v1/hostel/configuration", callback);
    }

    public void updateNodeStatus(String nodeId, String status, ApiCallback callback) {
        enqueue(api.updateNodeStatus(nodeId, status), "/api/v1/nodes/" + nodeId + "/status", callback);
    }

    public void getReadingHistoryRange(String nodeId, String startIso, String endIso, int limit, ApiCallback callback) {
        enqueue(api.getReadingHistoryRange(nodeId, startIso, endIso, limit),
                "/api/v1/nodes/" + nodeId + "/readings/history", callback);
    }

    public void getThresholds(ApiCallback callback) {
        enqueue(api.getThresholds(), "/api/v1/thresholds", callback);
    }

    public void updateThresholds(JSONObject payload, ApiCallback callback) {
        enqueue(api.updateThresholds(jsonBody(payload)), "/api/v1/thresholds", callback);
    }

    public void generateForecast(String nodeId, ApiCallback callback) {
        getReadingHistory(nodeId, 500, new ApiCallback() {
            @Override public void onSuccess(String json) {
                try {
                    JSONObject history = new JSONObject(json);
                    JSONArray raw = history.optJSONArray("readings");
                    if (raw == null) throw new JSONException("Reading history was missing.");
                    List<JSONObject> ordered = new ArrayList<>();
                    for (int i = 0; i < raw.length(); i++) {
                        JSONObject row = raw.optJSONObject(i);
                        if (row != null) ordered.add(row);
                    }
                    Collections.sort(ordered, Comparator.comparing(row -> row.optString("timestamp", "")));

                    String selectedSource = null;
                    List<JSONObject> complete = new ArrayList<>();
                    for (JSONObject row : ordered) {
                        String source = row.optString("source", "").trim().toUpperCase(Locale.ROOT);
                        if (source.isEmpty() || !isComplete(row)) continue;
                        if (selectedSource == null || source.equals(selectedSource)) {
                            selectedSource = source;
                            complete.add(row);
                        } else {
                            complete.clear();
                            selectedSource = source;
                            complete.add(row);
                        }
                    }
                    if (complete.size() < FORECAST_MIN_HISTORY) {
                        callback.onFailure(new ApiFailure(ApiFailure.Kind.INSUFFICIENT_DATA,
                                "/api/v1/forecast", 422,
                                "At least 30 complete readings from one data source are needed for a forecast. "
                                        + complete.size() + " are available.", null));
                        return;
                    }
                    JSONObject request = new JSONObject();
                    request.put("node_id", nodeId);
                    request.put("source", selectedSource);
                    JSONArray requestReadings = new JSONArray();
                    for (JSONObject row : complete) {
                        JSONObject reading = new JSONObject();
                        reading.put("timestamp", row.getString("timestamp"));
                        reading.put("pH", row.getDouble("ph"));
                        reading.put("TDS", row.getDouble("tds"));
                        reading.put("turbidity", row.getDouble("turbidity"));
                        reading.put("temperature", row.getDouble("temperature"));
                        reading.put("optical_colour_index", row.getDouble("optical_colour_index"));
                        reading.put("source", selectedSource);
                        if (!row.isNull("red")) reading.put("red", row.getInt("red"));
                        if (!row.isNull("green")) reading.put("green", row.getInt("green"));
                        if (!row.isNull("blue")) reading.put("blue", row.getInt("blue"));
                        if (!row.isNull("clear")) reading.put("clear", row.getInt("clear"));
                        if (!row.isNull("calibration_id")) reading.put("calibration_id", row.getInt("calibration_id"));
                        requestReadings.put(reading);
                    }
                    request.put("readings", requestReadings);
                    enqueue(api.generateForecast(jsonBody(request)), "/api/v1/forecast", callback);
                } catch (Exception error) {
                    callback.onFailure(new ApiFailure(ApiFailure.Kind.MALFORMED_RESPONSE,
                            "/api/v1/forecast", null, "Could not prepare the server readings for forecasting.", error));
                }
            }

            @Override public void onFailure(ApiFailure failure) { callback.onFailure(failure); }
        });
    }

    private boolean isComplete(JSONObject row) {
        return finite(row, "ph") && finite(row, "tds") && finite(row, "turbidity")
                && finite(row, "temperature") && finite(row, "optical_colour_index");
    }

    private boolean finite(JSONObject object, String key) {
        if (object.isNull(key) || !object.has(key)) return false;
        double value = object.optDouble(key, Double.NaN);
        return !Double.isNaN(value) && !Double.isInfinite(value);
    }

    public void getIssues(ApiCallback callback) { enqueue(api.getHostelIssues(), "/api/v1/hostel/issues", callback); }

    /** Re-read a single report, e.g. after a status change returned an odd body. */
    public void getIssue(String issueId, ApiCallback callback) {
        enqueue(api.getHostelIssue(issueId), "/api/v1/hostel/issues/" + issueId, callback);
    }

    /**
     * Fetch the authoritative issue transition graph. The response is handed to
     * {@code IssueWorkflow.applyServerJson} by the caller so the buttons on
     * Hostel Operations always match what the backend will accept.
     */
    public void getIssueWorkflow(ApiCallback callback) {
        enqueue(api.getIssueWorkflow(), "/api/v1/hostel/issues/workflow", callback);
    }
    public void getNotices(ApiCallback callback) { enqueue(api.getNotices(), "/api/v1/hostel/notices", callback); }
    public void getEmergencyContacts(ApiCallback callback) { enqueue(api.getEmergencyContacts(), "/api/v1/hostel/emergency-contacts", callback); }
    public void getLostFoundItems(ApiCallback callback) { enqueue(api.getLostFoundItems(), "/api/v1/hostel/lost-found", callback); }
    public void getIssueSummary(ApiCallback callback) { enqueue(api.getIssueSummary(), "/api/v1/hostel/admin/issues/summary", callback); }
    public void getAdminFeedback(ApiCallback callback) { enqueue(api.getAdminFeedback(), "/api/v1/hostel/admin/feedback", callback); }
    public void getResolutionFeedback(ApiCallback callback) { enqueue(api.getResolutionFeedback(), "/api/v1/hostel/admin/resolution-feedback", callback); }
    public void getAdminUsers(ApiCallback callback) { enqueue(api.getAdminUsers(), "/api/v1/admin/users", callback); }
    public void getIssueTimeline(String issueId, ApiCallback callback) {
        enqueue(api.getIssueTimeline(issueId), "/api/v1/hostel/issues/" + issueId + "/timeline", callback);
    }
    public void inviteAdmin(String email, ApiCallback callback) {
        JSONObject json = new JSONObject();
        try { json.put("email", email.trim()); } catch (JSONException ignored) { }
        enqueue(api.inviteAdmin(jsonBody(json)), "/api/v1/admin/users/invite", callback);
    }
    public void studentRegister(String fullName, String email, String password, ApiCallback callback) {
        JSONObject json = new JSONObject();
        try {
            // Never send a JSON null: the backend derives a display name from the
            // college email when no full name is provided.
            json.put("full_name", fullName == null ? "" : fullName.trim());
            json.put("email", email);
            json.put("password", password);
        } catch (JSONException ignored) { }
        enqueue(api.studentRegister(jsonBody(json)), "/api/v1/auth/student/register", callback);
    }
    public void studentLogin(String email, String password, ApiCallback callback) {
        JSONObject json = new JSONObject();
        try {
            json.put("email", email);
            json.put("password", password);
        } catch (JSONException ignored) { }
        enqueue(api.studentLogin(jsonBody(json)), "/api/v1/auth/student/login", callback);
    }

    public void updateAdminStatus(int id, String status, ApiCallback callback) {
        JSONObject json = new JSONObject();
        try { json.put("status", status); } catch (JSONException ignored) { }
        enqueue(api.updateAdminUser(id, jsonBody(json)), "/api/v1/admin/users/" + id, callback);
    }
    public void createIssue(String category, String location, String severity, String description, ApiCallback callback) {
        JSONObject json = new JSONObject();
        try {
            json.put("category", category);
            json.put("location", location.trim());
            json.put("severity", severity);
            json.put("description", description.trim());
        } catch (JSONException ignored) { }
        enqueue(api.createHostelIssue(jsonBody(json)), "/api/v1/hostel/issues", callback);
    }
    /**
     * Persist a status transition. {@code comment} is the reason shown in the
     * issue timeline (waiting reason, acknowledgement note); {@code resolution}
     * is the summary the backend requires for RESOLVED. Both are trimmed and
     * capped to the backend's field limits so a long note fails locally with a
     * clear message instead of a bare 422.
     */
    public void updateIssueStatus(String issueId, String status, String comment, String resolution,
                                  ApiCallback callback) {
        JSONObject json = new JSONObject();
        try {
            json.put("status", status);
            String note = trim(comment, 2000);
            json.put("comment", note.isEmpty() ? "Updated in HydroGuard Android app" : note);
            String summary = trim(resolution, 5000);
            if (!summary.isEmpty()) json.put("resolution", summary);
        } catch (JSONException ignored) { }
        enqueue(api.updateIssueStatus(issueId, jsonBody(json)), "/api/v1/hostel/issues/" + issueId + "/status", callback);
    }

    private static String trim(String value, int limit) {
        if (value == null) return "";
        String trimmed = value.trim();
        return trimmed.length() <= limit ? trimmed : trimmed.substring(0, limit);
    }
    public void submitHostelFeedback(String category, int rating, String comment, ApiCallback callback) {
        JSONObject json = new JSONObject();
        try {
            json.put("category", category);
            json.put("rating", rating);
            if (comment != null && !comment.trim().isEmpty()) json.put("comment", comment.trim());
        } catch (JSONException ignored) { }
        enqueue(api.submitHostelFeedback(jsonBody(json)), "/api/v1/hostel/feedback", callback);
    }
    public void submitResolutionFeedback(String issueId, int stars, String comment, ApiCallback callback) {
        JSONObject json = new JSONObject();
        try {
            json.put("stars", stars);
            if (comment != null && !comment.trim().isEmpty()) json.put("comment", comment.trim());
        } catch (JSONException ignored) { }
        enqueue(api.submitIssueFeedback(issueId, jsonBody(json)), "/api/v1/hostel/issues/" + issueId + "/feedback", callback);
    }
    public void reopenIssue(String issueId, String reason, ApiCallback callback) {
        JSONObject json = new JSONObject();
        try { json.put("reason", reason.trim()); } catch (JSONException ignored) { }
        enqueue(api.reopenIssue(issueId, jsonBody(json)), "/api/v1/hostel/issues/" + issueId + "/reopen", callback);
    }
    public void submitLostFound(String kind, String title, String description, String category,
                                String location, String itemDate, String imageUrl, ApiCallback callback) {
        JSONObject json = new JSONObject();
        try {
            json.put("kind", kind);
            json.put("title", title.trim());
            json.put("description", description.trim());
            json.put("category", category);
            json.put("location", location.trim());
            json.put("item_date", itemDate);
            if (imageUrl != null && !imageUrl.isEmpty()) json.put("image_url", imageUrl);
        } catch (JSONException ignored) { }
        enqueue(api.createLostFoundItem(jsonBody(json)), "/api/v1/hostel/lost-found", callback);
    }

    /**
     * Uploads prepared photograph bytes and hands back the server-issued
     * reference.
     *
     * <p>The upload is a separate round trip on purpose: if it fails the caller
     * must not file the listing anyway, otherwise the app would claim a photo
     * is attached when nothing left the device.</p>
     */
    public void uploadLostFoundPhoto(final byte[] data, String mediaType, ApiCallback callback) {
        final MediaType type = MediaType.parse(
                mediaType == null || mediaType.isEmpty() ? "application/octet-stream" : mediaType);
        RequestBody body = new RequestBody() {
            @Override public MediaType contentType() { return type; }

            @Override public void writeTo(okio.BufferedSink sink) throws IOException {
                sink.write(data);
            }
        };
        enqueue(api.uploadLostFoundPhoto(body), LostFoundPhotos.REFERENCE_PREFIX, callback);
    }

    /**
     * Fetches a stored photograph on a worker thread.
     *
     * <p>Only references this server issued are requested; the storage key is
     * validated here as well as on the server so a malformed {@code image_url}
     * never becomes a request.</p>
     */
    public void fetchLostFoundPhoto(String imageUrl, final PhotoCallback callback) {
        final String key = LostFoundPhotos.keyOf(imageUrl);
        final String endpoint = LostFoundPhotos.REFERENCE_PREFIX + (key == null ? "" : key);
        if (key == null) {
            callback.onFailure(new ApiFailure(ApiFailure.Kind.MALFORMED_RESPONSE, imageUrl, null,
                    "This photo reference was not issued by the HydroGuard server.", null));
            return;
        }
        PHOTO_EXECUTOR.execute(() -> {
            try {
                Response<ResponseBody> response = api.getLostFoundPhoto(key).execute();
                if (!response.isSuccessful() || response.body() == null) {
                    final ApiFailure failure = classifyResponse(response.code(), endpoint, read(response.errorBody()));
                    mainHandler.post(() -> callback.onFailure(failure));
                    return;
                }
                try (ResponseBody body = response.body()) {
                    final byte[] bytes = body.bytes();
                    final String contentType = body.contentType() == null
                            ? "image/*" : body.contentType().toString();
                    mainHandler.post(() -> callback.onPhoto(bytes, contentType));
                }
            } catch (IOException error) {
                final ApiFailure failure = classifyNetworkError(endpoint, error);
                mainHandler.post(() -> callback.onFailure(failure));
            }
        });
    }
    public void moderateLostFound(String itemId, String status, ApiCallback callback) {
        JSONObject json = new JSONObject();
        try { json.put("moderation_status", status); } catch (JSONException ignored) { }
        enqueue(api.moderateLostFoundItem(itemId, jsonBody(json)),
                "/api/v1/hostel/lost-found/" + itemId + "/moderation", callback);
    }
    public void createNotice(String title, String body, String category, String priority, ApiCallback callback) {
        JSONObject json = new JSONObject();
        try {
            json.put("title", title.trim()); json.put("body", body.trim());
            json.put("category", category); json.put("priority", priority);
        } catch (JSONException ignored) { }
        enqueue(api.createNotice(jsonBody(json)), "/api/v1/hostel/notices", callback);
    }
    public void deleteNotice(int noticeId, ApiCallback callback) {
        enqueue(api.deleteNotice(noticeId), "/api/v1/hostel/notices/" + noticeId, callback);
    }
    public void createEmergencyContact(String category, String name, String phone, String details,
                                       ApiCallback callback) {
        JSONObject json = new JSONObject();
        try {
            json.put("category", category); json.put("name", name.trim()); json.put("phone", phone.trim());
            if (details != null && !details.trim().isEmpty()) json.put("details", details.trim());
            json.put("active", true); json.put("verified", false);
        } catch (JSONException ignored) { }
        enqueue(api.createEmergencyContact(jsonBody(json)), "/api/v1/hostel/emergency-contacts", callback);
    }
    public void updateEmergencyContact(int id, String category, String name, String phone, String details,
                                       boolean active, boolean verified, ApiCallback callback) {
        JSONObject json = new JSONObject();
        try {
            json.put("category", category); json.put("name", name); json.put("phone", phone);
            if (details != null && !details.isEmpty()) json.put("details", details);
            json.put("active", active); json.put("verified", verified);
        } catch (JSONException ignored) { }
        enqueue(api.updateEmergencyContact(id, jsonBody(json)),
                "/api/v1/hostel/emergency-contacts/" + id, callback);
    }
    public void deleteEmergencyContact(int contactId, ApiCallback callback) {
        enqueue(api.deleteEmergencyContact(contactId), "/api/v1/hostel/emergency-contacts/" + contactId, callback);
    }

    private void enqueue(Call<ResponseBody> call, String endpoint, ApiCallback callback) {
        call.enqueue(new retrofit2.Callback<ResponseBody>() {
            @Override public void onResponse(Call<ResponseBody> ignored, Response<ResponseBody> response) {
                // Any HTTP response — including 4xx/5xx — proves the server answered, so the
                // app bar's link state is measured here rather than assumed.
                ServerLink.recordResponseReceived();
                String body = read(response.isSuccessful() ? response.body() : response.errorBody());
                if (response.isSuccessful()) {
                    callback.onSuccess(body);
                    return;
                }
                callback.onFailure(classifyResponse(response.code(), endpoint, body));
            }

            @Override public void onFailure(Call<ResponseBody> ignored, Throwable error) {
                // No response was produced at all: the link is down, regardless of what the
                // Wi-Fi radio reports about association.
                ServerLink.recordTransportFailure();
                ApiFailure failure = classifyNetworkError(endpoint, error);
                if (BuildConfig.DEBUG) {
                    Log.w("HydroGuardApi", failure.getMessage());
                    Log.e("HydroGuardApi", "Network request failed: " + error.getMessage(), error);
                }
                callback.onFailure(failure);
            }
        });
    }

    private ApiFailure classifyNetworkError(String endpoint, Throwable error) {
        Throwable rootCause = error;
        while (rootCause.getCause() != null && rootCause.getCause() != rootCause) {
            rootCause = rootCause.getCause();
        }
        return new ApiFailure(ApiFailure.Kind.SERVER_UNREACHABLE, endpoint, null,
                failureMessage(rootCause, RetrofitClient.baseUrl(), LanApiRoute.isWifiConnected()), error);
    }

    static String failureMessage(Throwable rootCause, String baseUrl, boolean wifiConnected) {
        if (rootCause instanceof LanApiRoute.LanRouteUnavailableException) {
            return rootCause.getMessage();
        }
        boolean lanBackend = LanApiRoute.isLanApiHost(baseUrl);
        if (rootCause instanceof UnknownHostException) {
            return "The HydroGuard API host could not be resolved at " + baseUrl
                    + " Verify the development computer's current Wi-Fi IPv4 address and rebuild the debug app.";
        }
        if (rootCause instanceof java.net.SocketTimeoutException) {
            if (lanBackend && wifiConnected) {
                return "The HydroGuard backend at " + baseUrl + " did not respond even though the phone is on Wi-Fi. "
                        + "Check that the backend terminal is still running and that Windows Firewall allows inbound port 8000 on this network.";
            }
            return "The HydroGuard API at " + baseUrl + " did not respond before the request timed out. "
                    + "Check that the backend finished starting and that the phone and computer share Wi-Fi.";
        }
        if (rootCause instanceof java.net.ConnectException) {
            if (lanBackend && !wifiConnected) {
                return "The phone is not connected to Wi-Fi, so the HydroGuard backend at " + baseUrl
                        + " cannot be reached over mobile data. Connect Wi-Fi and try again.";
            }
            return "A connection to the HydroGuard API at " + baseUrl + " was refused or blocked. "
                    + "Verify that the backend is running on the development computer's LAN address on port 8000 and that Windows Firewall allows the phone on this network.";
        }
        return "The network request to the HydroGuard API at " + baseUrl
                + " failed before the server returned a response. Check the phone's Wi-Fi and the backend's LAN connection.";
    }

    private ApiFailure classifyResponse(int status, String endpoint, String body) {
        String detail = parseDetail(body);
        ApiFailure.Kind kind = ApiFailure.Kind.API_ERROR;
        String message;
        if (status == 401 || status == 403) {
            kind = ApiFailure.Kind.AUTHENTICATION;
            message = detail.isEmpty() ? "HydroGuard did not accept this session. Sign in again or check development authentication settings." : detail;
        } else if (status == 422 && endpoint.contains("forecast")) {
            kind = ApiFailure.Kind.INSUFFICIENT_DATA;
            message = detail.isEmpty() ? "At least 30 complete readings from one source are needed for forecasting." : detail;
        } else if (status == 404 && endpoint.endsWith("/readings/latest")) {
            message = detail.isEmpty() ? "No reading has been received for this sensor yet." : detail;
        } else if (status >= 500) {
            message = "The HydroGuard server responded with an error (HTTP " + status + "). "
                    + (detail.isEmpty() ? "Check the backend log for this request." : detail);
        } else {
            message = detail.isEmpty() ? "HydroGuard could not complete this request (HTTP " + status + ")." : detail;
        }
        return new ApiFailure(kind, endpoint, status, message, null);
    }

    private String parseDetail(String body) {
        if (body == null || body.trim().isEmpty()) return "";
        try {
            JSONObject json = new JSONObject(body);
            Object detail = json.opt("detail");
            return detail instanceof String ? ((String) detail).trim() : "";
        } catch (JSONException ignored) {
            return "";
        }
    }

    private String read(ResponseBody body) {
        if (body == null) return "";
        try { return body.string(); } catch (IOException ignored) { return ""; }
    }

    private static RequestBody jsonBody(JSONObject json) {
        return RequestBody.create(json.toString().getBytes(StandardCharsets.UTF_8), JSON);
    }
}
