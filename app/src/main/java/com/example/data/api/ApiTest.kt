package com.example.data.api

import android.util.Log
import kotlinx.coroutines.runBlocking

/** Read-only API smoke check. Forecast smoke tests must use stored backend history. */
object ApiTest {
    private const val TAG = "ApiTest"

    fun testApiConnection(nodeId: String) {
        runBlocking {
            try {
                val latest = RetrofitClient.apiService.getLatestReading(nodeId)
                if (latest.isSuccessful && latest.body() != null) {
                    val reading = latest.body()!!
                    Log.d(TAG, "Latest ${reading.source} reading fetched for $nodeId at ${reading.timestamp}")
                } else {
                    Log.e(TAG, "Latest reading request failed: ${latest.code()}")
                }

                val history = RetrofitClient.apiService.getHistoricalReadings(nodeId, 1000)
                Log.d(TAG, "Stored history request returned ${history.body()?.count ?: 0} observations")
            } catch (e: Exception) {
                Log.e(TAG, "API read-only smoke check failed", e)
            }
        }
    }
}
