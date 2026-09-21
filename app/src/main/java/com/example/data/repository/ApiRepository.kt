package com.example.data.repository

import android.util.Log
import com.example.data.api.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.*
import kotlin.random.Random

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

    suspend fun generateForecast(readings: List<ForecastReading>): Result<ForecastResponse> = withContext(Dispatchers.IO) {
        try {
            val request = ForecastRequest(readings = readings)
            val response = apiService.generateForecast(request)
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                val errorMsg = "API Error: ${response.code()} - ${response.message()}"
                Log.e("ApiRepository", errorMsg)
                Result.failure(Exception(errorMsg))
            }
        } catch (e: Exception) {
            Log.e("ApiRepository", "Network error generating forecast", e)
            Result.failure(e)
        }
    }

    // Helper method to generate mock historical readings for forecast request
    fun generateForecastReadingsFromLatest(latestReading: LatestReadingResponse): List<ForecastReading> {
        val readings = mutableListOf<ForecastReading>()
        val sdf = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US)
        sdf.timeZone = TimeZone.getTimeZone("UTC")

        val baseTime = sdf.parse(latestReading.timestamp)?.time ?: System.currentTimeMillis()
        val hourMs = 3600000L

        // Generate 30 days of historical data ending with the latest reading
        for (i in 29 downTo 0) {
            val timestamp = baseTime - (i * hourMs)
            val timeStr = sdf.format(Date(timestamp))

            // Add some variation to simulate historical data
            val variation = (i * 0.1f).coerceAtMost(2.0f)

            // Helper function to safely add random variation, avoiding empty ranges
            fun addVariation(base: Float, scale: Float, min: Float? = null, max: Float? = null): Float {
                if (variation == 0f) return base
                val randomChange = Random.nextDouble((-variation * scale).toDouble(), (variation * scale).toDouble()).toFloat()
                val result = base + randomChange
                return when {
                    min != null && max != null -> result.coerceIn(min, max)
                    min != null -> result.coerceAtLeast(min)
                    max != null -> result.coerceAtMost(max)
                    else -> result
                }
            }

            readings.add(
                ForecastReading(
                    timestamp = timeStr,
                    pH = addVariation(latestReading.ph, 1.0f, 6.0f, 8.5f),
                    TDS = addVariation(latestReading.tds, 10.0f, 50f),
                    turbidity = addVariation(latestReading.turbidity, 0.5f, 0.1f),
                    temperature = addVariation(latestReading.temperature, 0.2f, 15f, 35f),
                    EC = latestReading.ec,
                    DO = latestReading.`do`
                )
            )
        }

        return readings
    }
}
