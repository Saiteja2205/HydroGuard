package com.example.data.repository

import android.util.Log
import com.example.data.api.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class ApiRepository {

    private val apiService = RetrofitClient.apiService

    suspend fun getLatestReading(nodeId: String): Result<LatestReadingResponse> = withContext(Dispatchers.IO) {
        try {
            val response = apiService.getLatestReading(nodeId)
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                val errorMsg = "API Error: ${response.code()} - ${response.message()}"
                Log.e("ApiRepository", errorMsg)
                Result.failure(Exception(errorMsg))
            }
        } catch (e: Exception) {
            Log.e("ApiRepository", "Network error fetching latest reading", e)
            Result.failure(e)
        }
    }

    suspend fun generateForecast(nodeId: String, history: List<HistoricalReadingResponse>): Result<ForecastResponse> = withContext(Dispatchers.IO) {
        try {
            val valid = history.filter { it.temperature != null }.sortedBy { it.timestamp }
            if (valid.size < FORECAST_MIN_HISTORY) {
                return@withContext Result.failure(InsufficientForecastDataException(
                    "Insufficient historical data for reliable forecasting. At least $FORECAST_MIN_HISTORY valid timestamped observations are required."
                ))
            }
            val window = valid.takeLast(FORECAST_MIN_HISTORY)
            if (window.map { it.timestamp }.distinct().size != window.size) {
                return@withContext Result.failure(InsufficientForecastDataException("Forecast history contains duplicate timestamps."))
            }
            val sources = window.map { it.source.uppercase() }.distinct()
            if (sources.size != 1) {
                return@withContext Result.failure(InsufficientForecastDataException("Forecast history contains mixed data sources."))
            }
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
                    opticalColourIndex = row.opticalColourIndex,
                    calibrationId = row.calibrationId,
                    source = sources.single()
                )
            }
            val request = ForecastRequest(nodeId = nodeId, readings = readings)
            val response = apiService.generateForecast(request)
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                val detail = response.errorBody()?.string()?.take(500)
                val errorMsg = detail ?: "API Error: ${response.code()} - ${response.message()}"
                Log.e("ApiRepository", errorMsg)
                Result.failure(Exception(errorMsg))
            }
        } catch (e: Exception) {
            Log.e("ApiRepository", "Network error generating forecast", e)
            Result.failure(e)
        }
    }

    suspend fun getHistoricalReadings(nodeId: String, limit: Int? = null): Result<HistoryResponse> = withContext(Dispatchers.IO) {
        try {
            val response = apiService.getHistoricalReadings(nodeId, limit)
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                val errorMsg = "API Error: ${response.code()} - ${response.message()}"
                Log.e("ApiRepository", errorMsg)
                Result.failure(Exception(errorMsg))
            }
        } catch (e: Exception) {
            Log.e("ApiRepository", "Network error fetching historical readings", e)
            Result.failure(e)
        }
    }

    suspend fun getAlerts(nodeId: String): Result<AlertListResponse> = withContext(Dispatchers.IO) {
        try {
            val response = apiService.getAlerts(nodeId)
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                val errorMsg = "API Error: ${response.code()} - ${response.message()}"
                Log.e("ApiRepository", errorMsg)
                Result.failure(Exception(errorMsg))
            }
        } catch (e: Exception) {
            Log.e("ApiRepository", "Network error fetching alerts", e)
            Result.failure(e)
        }
    }

    companion object { const val FORECAST_MIN_HISTORY = 30 }
}

class InsufficientForecastDataException(message: String) : Exception(message)
