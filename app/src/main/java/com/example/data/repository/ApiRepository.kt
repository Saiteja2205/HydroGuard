package com.example.data.repository

import android.util.Log
import com.example.BuildConfig
import com.example.data.api.*
import com.squareup.moshi.JsonDataException
import com.squareup.moshi.JsonEncodingException
import org.json.JSONArray
import org.json.JSONObject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.withContext
import retrofit2.Response
import java.io.IOException

enum class ApiFailureKind {
    SERVER_UNREACHABLE,
    NO_READING,
    AUTHENTICATION,
    API_ERROR,
    MALFORMED_RESPONSE,
    INSUFFICIENT_DATA
}

class ApiRequestFailure(
    val kind: ApiFailureKind,
    val endpoint: String,
    val statusCode: Int? = null,
    val userDetail: String? = null,
    cause: Throwable? = null
) : Exception(
    userDetail?.takeIf(String::isNotBlank) ?: when (kind) {
        ApiFailureKind.SERVER_UNREACHABLE -> "HydroGuard server is currently unreachable."
        ApiFailureKind.NO_READING -> "No sensor reading has been received from this node yet."
        ApiFailureKind.AUTHENTICATION -> "Your session has expired. Sign in again."
        ApiFailureKind.API_ERROR -> "Unable to retrieve water monitoring data."
        ApiFailureKind.MALFORMED_RESPONSE -> "The server returned an unexpected response."
        ApiFailureKind.INSUFFICIENT_DATA -> "Not enough complete server readings are available for forecasting yet."
    },
    cause
)

class ApiRepository {

    private val apiService = RetrofitClient.apiService

    suspend fun bootstrapAccount(): Result<AuthenticatedUserResponse> = request(
        endpoint = "/api/v1/auth/bootstrap"
    ) { apiService.bootstrapAccount() }

    suspend fun createDevelopmentDemoStudentSession(): Result<String> = request(
        endpoint = "/api/v1/auth/development/demo-student-session"
    ) { apiService.createDevelopmentDemoStudentSession() }.map { it.customToken }

    suspend fun getAdminUsers(): Result<List<AdminUserResponse>> = request(
        endpoint = "/api/v1/admin/users"
    ) { apiService.listAdminUsers() }

    suspend fun inviteAdmin(email: String): Result<AdminUserResponse> = request(
        endpoint = "/api/v1/admin/users/invite"
    ) { apiService.inviteAdmin(AdminInviteRequest(email = email)) }

    suspend fun updateAdminUserStatus(userId: Int, status: String): Result<AdminUserResponse> = request(
        endpoint = "/api/v1/admin/users/$userId"
    ) { apiService.updateAdminUserStatus(userId, AdminUserStatusRequest(status = status)) }

    suspend fun getLatestReading(nodeId: String): Result<LatestReadingResponse> = request(
        endpoint = "/api/v1/nodes/$nodeId/readings/latest",
        noReadingIsExpected = true
    ) { apiService.getLatestReading(nodeId) }

    suspend fun getNodeHealth(nodeId: String): Result<NodeHealthResponse> = request(
        endpoint = "/api/v1/nodes/$nodeId"
    ) { apiService.getNodeHealth(nodeId) }

    suspend fun getHistoricalReadings(nodeId: String, limit: Int? = null): Result<HistoryResponse> = request(
        endpoint = "/api/v1/nodes/$nodeId/readings/history"
    ) { apiService.getHistoricalReadings(nodeId, limit) }

    suspend fun getAlerts(nodeId: String): Result<AlertListResponse> = request(
        endpoint = "/api/v1/nodes/$nodeId/alerts"
    ) { apiService.getAlerts(nodeId) }

    suspend fun getModelPerformance(nodeId: String): Result<ModelPerformanceResponse> = request(
        endpoint = "/api/v1/nodes/$nodeId/model-performance"
    ) { apiService.getModelPerformance(nodeId) }

    suspend fun exportResearchCsv(): Result<ByteArray> = withContext(Dispatchers.IO) {
        val endpoint = "/api/v1/research/export.csv"
        try {
            val response = apiService.exportResearchCsv()
            if (!response.isSuccessful) return@withContext responseResult(response, endpoint).map { body -> body.use { it.bytes() } }
            val body = response.body()
                ?: return@withContext Result.failure(ApiRequestFailure(ApiFailureKind.MALFORMED_RESPONSE, endpoint, response.code()))
            Result.success(body.use { it.bytes() })
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: Exception) {
            val failure = classifyFailure(error, endpoint)
            Log.e("HydroGuardApi", "${failure.kind} endpoint=${failure.endpoint} type=${error.javaClass.simpleName}")
            Result.failure(failure)
        }
    }

    suspend fun getHostelNotices(): Result<List<HostelNoticeResponse>> = request(
        endpoint = "/api/v1/hostel/notices"
    ) { apiService.getHostelNotices() }

    suspend fun getHostelIssues(): Result<List<HostelIssueResponse>> = request(
        endpoint = "/api/v1/hostel/issues"
    ) { apiService.getHostelIssues() }

    suspend fun getIssueTimeline(issueId: String): Result<List<IssueEventResponse>> = request(
        endpoint = "/api/v1/hostel/issues/$issueId/timeline"
    ) { apiService.getIssueTimeline(issueId) }

    suspend fun submitResolutionFeedback(issueId: String, feedback: IssueFeedbackRequest): Result<Unit> = request(
        endpoint = "/api/v1/hostel/issues/$issueId/feedback"
    ) { apiService.submitResolutionFeedback(issueId, feedback) }

    suspend fun reopenIssue(issueId: String, request: IssueReopenRequest): Result<HostelIssueResponse> = request(
        endpoint = "/api/v1/hostel/issues/$issueId/reopen"
    ) { apiService.reopenIssue(issueId, request) }

    suspend fun generateForecast(nodeId: String, history: List<HistoricalReadingResponse>): Result<ForecastResponse> = withContext(Dispatchers.IO) {
        try {
            val completeBySource = history
                .filter {
                    it.ph.isFinite() && it.tds.isFinite() && it.turbidity.isFinite() &&
                        it.temperature?.isFinite() == true && it.opticalColourIndex?.isFinite() == true
                }
                .groupBy { canonicalSource(it.source) }
            val sourceGroup = completeBySource.maxByOrNull { it.value.size }
            val valid = sourceGroup?.value.orEmpty().sortedBy { it.timestamp }
            if (valid.size < FORECAST_MIN_HISTORY) {
                val missingCounts = listOf(
                    "pH" to history.count { !it.ph.isFinite() },
                    "TDS" to history.count { !it.tds.isFinite() },
                    "Turbidity" to history.count { !it.turbidity.isFinite() },
                    "Temperature" to history.count { it.temperature?.isFinite() != true },
                    "Optical Colour Index" to history.count { it.opticalColourIndex?.isFinite() != true }
                ).filter { it.second > 0 }
                val missingSummary = missingCounts.joinToString { "${it.first} missing in ${it.second}" }
                val sourceSummary = completeBySource.entries.joinToString { "${it.key}: ${it.value.size}" }
                val detail = buildString {
                    append("Forecast needs at least $FORECAST_MIN_HISTORY complete five-parameter readings from one data source. ")
                    append("Found ${valid.size} complete readings among ${history.size} returned observations.")
                    if (missingSummary.isNotBlank()) append(" $missingSummary.")
                    if (sourceSummary.isNotBlank()) append(" Complete readings by source: $sourceSummary.")
                    append(" No missing values were filled in.")
                }
                return@withContext Result.failure(
                    ApiRequestFailure(ApiFailureKind.INSUFFICIENT_DATA, "/api/v1/forecast", userDetail = detail)
                )
            }
            val window = valid.takeLast(FORECAST_MIN_HISTORY)
            if (window.map { it.timestamp }.distinct().size != window.size) {
                return@withContext Result.failure(
                    ApiRequestFailure(
                        ApiFailureKind.INSUFFICIENT_DATA,
                        "/api/v1/forecast",
                        userDetail = "Forecast needs 30 unique, chronologically ordered timestamps. The available history contains duplicate timestamps."
                    )
                )
            }
            val source = canonicalSource(sourceGroup?.key ?: window.first().source)
            val readings = window.map { row ->
                ForecastReading(
                    timestamp = row.timestamp,
                    pH = row.ph,
                    TDS = row.tds,
                    turbidity = row.turbidity,
                    temperature = row.temperature!!,
                    red = row.red,
                    green = row.green,
                    blue = row.blue,
                    clear = row.clear,
                    opticalColourIndex = row.opticalColourIndex!!,
                    calibrationId = row.calibrationId,
                    source = source
                )
            }
            val response = apiService.generateForecast(ForecastRequest(nodeId = nodeId, readings = readings))
            responseResult(response, "/api/v1/forecast")
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (failure: ApiRequestFailure) {
            Result.failure(failure)
        } catch (error: Exception) {
            val failure = classifyFailure(error, "/api/v1/forecast")
            Log.e("HydroGuardApi", "${failure.kind} endpoint=${failure.endpoint} type=${error.javaClass.simpleName}")
            Result.failure(failure)
        }
    }

    private suspend fun <T : Any> request(
        endpoint: String,
        noReadingIsExpected: Boolean = false,
        call: suspend () -> Response<T>
    ): Result<T> = withContext(Dispatchers.IO) {
        try {
            responseResult(call(), endpoint, noReadingIsExpected)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: Exception) {
            val failure = classifyFailure(error, endpoint)
            Log.e("HydroGuardApi", "${failure.kind} endpoint=${failure.endpoint} type=${error.javaClass.simpleName}")
            Result.failure(failure)
        }
    }

    private fun <T : Any> responseResult(
        response: Response<T>,
        endpoint: String,
        noReadingIsExpected: Boolean = false
    ): Result<T> {
        if (response.isSuccessful) {
            val body = response.body()
            if (body != null) return Result.success(body)
            return Result.failure(ApiRequestFailure(ApiFailureKind.MALFORMED_RESPONSE, endpoint, response.code()))
        }
        val kind = when {
            response.code() == 401 || response.code() == 403 -> ApiFailureKind.AUTHENTICATION
            noReadingIsExpected && response.code() == 404 -> ApiFailureKind.NO_READING
            endpoint == "/api/v1/forecast" && response.code() == 422 -> ApiFailureKind.INSUFFICIENT_DATA
            else -> ApiFailureKind.API_ERROR
        }
        val detail = response.errorBody()?.use { errorBody -> parseErrorDetail(errorBody.string()) }
        if (BuildConfig.DEBUG) {
            Log.w("HydroGuardApi", "HTTP ${response.code()} endpoint=$endpoint detail=${detail ?: "<empty response body>"}")
        }
        return Result.failure(ApiRequestFailure(kind, endpoint, response.code(), userDetail = detail))
    }

    private fun parseErrorDetail(body: String): String? {
        val raw = body.trim()
        if (raw.isBlank()) return null
        val detail = runCatching { JSONObject(raw).opt("detail") }.getOrNull()
        val message = when (detail) {
            is String -> detail
            is JSONArray -> buildList {
                for (index in 0 until detail.length()) {
                    val item = detail.optJSONObject(index) ?: continue
                    val location = item.optJSONArray("loc")?.let { path ->
                        (0 until path.length()).joinToString(".") { path.optString(it) }
                    }.orEmpty()
                    val reason = item.optString("msg").takeIf(String::isNotBlank).orEmpty()
                    add(listOf(location, reason).filter(String::isNotBlank).joinToString(": "))
                }
            }.filter(String::isNotBlank).joinToString("; ").takeIf(String::isNotBlank)
            null -> raw
            else -> detail.toString()
        }
        return message?.trim()?.take(600)?.takeIf(String::isNotBlank)
    }

    private fun classifyFailure(error: Throwable, endpoint: String): ApiRequestFailure = when (error) {
        is ApiRequestFailure -> error
        is JsonDataException -> ApiRequestFailure(ApiFailureKind.MALFORMED_RESPONSE, endpoint, cause = error)
        is JsonEncodingException -> ApiRequestFailure(ApiFailureKind.MALFORMED_RESPONSE, endpoint, cause = error)
        is IOException -> ApiRequestFailure(ApiFailureKind.SERVER_UNREACHABLE, endpoint, cause = error)
        else -> ApiRequestFailure(ApiFailureKind.API_ERROR, endpoint, cause = error)
    }

    companion object { const val FORECAST_MIN_HISTORY = 30 }

    private fun canonicalSource(source: String): String = when (source.trim().uppercase()) {
        "ESP32" -> "REAL_SENSOR"
        "MANUAL" -> "HISTORICAL_DATA"
        "HISTORICAL_DEMO", "HISTORICAL_OR_SIMULATED" -> "DEMO"
        else -> source.trim().uppercase()
    }
}
