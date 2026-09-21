package com.example.data.api

import android.util.Log
import kotlinx.coroutines.runBlocking

// Simple test to verify API integration
object ApiTest {

    private const val TAG = "ApiTest"

    fun testApiConnection() {
        runBlocking {
            try {
                val apiService = RetrofitClient.apiService

                // Test GET latest reading
                Log.d(TAG, "Testing GET /api/v1/nodes/node_1/readings/latest")
                val readingResponse = apiService.getLatestReading("node_1")
                if (readingResponse.isSuccessful && readingResponse.body() != null) {
                    val reading = readingResponse.body()!!
                    Log.d(TAG, "âœ“ Latest reading fetched successfully: pH=${reading.ph}, TDS=${reading.tds}")
                } else {
                    Log.e(TAG, "âœ— Failed to fetch latest reading: ${readingResponse.code()}")
                }

                // Test POST forecast
                Log.d(TAG, "Testing POST /api/v1/forecast")
                val forecastReadings = generateTestReadings()
                val forecastRequest = ForecastRequest(readings = forecastReadings)
                val forecastResponse = apiService.generateForecast(forecastRequest)

                if (forecastResponse.isSuccessful && forecastResponse.body() != null) {
                    val forecast = forecastResponse.body()!!
                    Log.d(TAG, "âœ“ Forecast generated successfully: pH=${forecast.prediction.pH}, TDS=${forecast.prediction.TDS}")
                    Log.d(TAG, "  Model weights: ${forecast.weights}")
                } else {
                    Log.e(TAG, "âœ— Failed to generate forecast: ${forecastResponse.code()}")
                }

            } catch (e: Exception) {
                Log.e(TAG, "API test failed with exception", e)
            }
        }
    }

    private fun generateTestReadings(): List<ForecastReading> {
        val readings = mutableListOf<ForecastReading>()
        for (i in 0 until 30) {
            readings.add(
                ForecastReading(
                    timestamp = "2026-09-${String.format("%02d", 20 - i)}T12:00:00Z",
                    pH = 7.0f + (i % 10) * 0.1f,
                    TDS = 300f + (i % 20) * 10f,
                    turbidity = 1.0f + (i % 5) * 0.2f,
                    temperature = 20.0f + (i % 10) * 0.5f
                )
            )
        }
        return readings
    }
}
