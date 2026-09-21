package com.example.data.api

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

// Latest Reading Response
@JsonClass(generateAdapter = true)
data class LatestReadingResponse(
    @Json(name = "node_id")
    val nodeId: String,
    @Json(name = "timestamp")
    val timestamp: String,
    @Json(name = "ph")
    val ph: Float,
    @Json(name = "tds")
    val tds: Float,
    @Json(name = "turbidity")
    val turbidity: Float,
    @Json(name = "temperature")
    val temperature: Float,
    @Json(name = "ec")
    val ec: Float?,
    @Json(name = "do")
    val `do`: Float?,
    @Json(name = "flow_rate")
    val flowRate: Float,
    @Json(name = "source")
    val source: String
)

// Forecast Reading (for request)
@JsonClass(generateAdapter = true)
data class ForecastReading(
    @Json(name = "timestamp")
    val timestamp: String,
    @Json(name = "pH")
    val pH: Float,
    @Json(name = "TDS")
    val TDS: Float,
    @Json(name = "turbidity")
    val turbidity: Float,
    @Json(name = "temperature")
    val temperature: Float,
    @Json(name = "EC")
    val EC: Float? = null,
    @Json(name = "DO")
    val `DO`: Float? = null
)

// Forecast Request
@JsonClass(generateAdapter = true)
data class ForecastRequest(
    @Json(name = "readings")
    val readings: List<ForecastReading>
)

// Model Prediction (single model)
@JsonClass(generateAdapter = true)
data class ModelPrediction(
    @Json(name = "pH")
    val pH: Float,
    @Json(name = "TDS")
    val TDS: Float,
    @Json(name = "turbidity")
    val turbidity: Float,
    @Json(name = "temperature")
    val temperature: Float,
    @Json(name = "EC")
    val EC: Float?,
    @Json(name = "DO")
    val `DO`: Float?
)

// Model Weights (single parameter)
@JsonClass(generateAdapter = true)
data class ModelWeights(
    @Json(name = "LSTM")
    val LSTM: Float,
    @Json(name = "PatchTST")
    val PatchTST: Float,
    @Json(name = "TimeMixer")
    val TimeMixer: Float
)

// Forecast Response
@JsonClass(generateAdapter = true)
data class ForecastResponse(
    @Json(name = "forecast_date")
    val forecastDate: String,
    @Json(name = "prediction")
    val prediction: ModelPrediction,
    @Json(name = "model_predictions")
    val modelPredictions: Map<String, ModelPrediction>? = null,
    @Json(name = "weights")
    val weights: Map<String, ModelWeights>? = null
)
