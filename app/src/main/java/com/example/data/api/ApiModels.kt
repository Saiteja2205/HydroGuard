package com.example.data.api

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

/** API models mirror backend-authoritative records. Raw TCS34725 counts are preserved. */
@JsonClass(generateAdapter = true)
data class LatestReadingResponse(
    @Json(name = "node_id") val nodeId: String,
    val timestamp: String,
    val ph: Float,
    val tds: Float,
    val turbidity: Float,
    val temperature: Float?,
    val red: Int?,
    val green: Int?,
    val blue: Int?,
    val clear: Int?,
    @Json(name = "optical_colour_index") val opticalColourIndex: Float?,
    @Json(name = "calibration_id") val calibrationId: Int?,
    val source: String
)

@JsonClass(generateAdapter = true)
data class ForecastReading(
    val timestamp: String,
    @Json(name = "pH") val pH: Float,
    @Json(name = "TDS") val TDS: Float,
    val turbidity: Float,
    val temperature: Float,
    val red: Int? = null,
    val green: Int? = null,
    val blue: Int? = null,
    val clear: Int? = null,
    @Json(name = "optical_colour_index") val opticalColourIndex: Float? = null,
    @Json(name = "calibration_id") val calibrationId: Int? = null,
    val source: String
)

@JsonClass(generateAdapter = true)
data class ForecastRequest(
    @Json(name = "node_id") val nodeId: String,
    val readings: List<ForecastReading>
)

@JsonClass(generateAdapter = true)
data class ModelPrediction(
    @Json(name = "pH") val pH: Float,
    @Json(name = "TDS") val TDS: Float,
    val turbidity: Float,
    val temperature: Float
)

@JsonClass(generateAdapter = true)
data class ModelWeights(
    @Json(name = "LSTM") val LSTM: Float,
    @Json(name = "PatchTST") val PatchTST: Float,
    @Json(name = "TimeMixer") val TimeMixer: Float
)

@JsonClass(generateAdapter = true)
data class ForecastResponse(
    @Json(name = "forecast_date") val forecastDate: String,
    val prediction: ModelPrediction,
    @Json(name = "model_predictions") val modelPredictions: Map<String, ModelPrediction>? = null,
    val weights: Map<String, ModelWeights>? = null,
    @Json(name = "node_id") val nodeId: String,
    @Json(name = "input_start") val inputStart: String,
    @Json(name = "input_end") val inputEnd: String,
    @Json(name = "data_source") val dataSource: String,
    @Json(name = "model_versions") val modelVersions: Map<String, String>,
    @Json(name = "weight_strategy") val weightStrategy: String,
    @Json(name = "weight_status") val weightStatus: String,
    @Json(name = "optical_colour_forecast_available") val opticalColourForecastAvailable: Boolean = false
)

@JsonClass(generateAdapter = true)
data class HistoricalReadingResponse(
    val id: Int,
    @Json(name = "node_id") val nodeId: String,
    val timestamp: String,
    val ph: Float,
    val tds: Float,
    val turbidity: Float,
    val temperature: Float?,
    val red: Int?,
    val green: Int?,
    val blue: Int?,
    val clear: Int?,
    @Json(name = "optical_colour_index") val opticalColourIndex: Float?,
    @Json(name = "calibration_id") val calibrationId: Int?,
    val source: String,
    @Json(name = "created_at") val createdAt: String
)

@JsonClass(generateAdapter = true)
data class HistoryResponse(val readings: List<HistoricalReadingResponse>, val count: Int)

@JsonClass(generateAdapter = true)
data class AlertResponse(
    val id: Int,
    @Json(name = "node_id") val nodeId: String,
    val timestamp: String,
    val parameter: String,
    val value: Float,
    val threshold: Float,
    val severity: String,
    val message: String,
    val status: String,
    @Json(name = "created_at") val createdAt: String
)

@JsonClass(generateAdapter = true)
data class AlertListResponse(val alerts: List<AlertResponse>, val count: Int)
