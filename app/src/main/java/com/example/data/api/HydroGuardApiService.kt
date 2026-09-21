package com.example.data.api

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path

interface HydroGuardApiService {

    @GET("api/v1/nodes/{node_id}/readings/latest")
    suspend fun getLatestReading(
        @Path("node_id") nodeId: String
    ): Response<LatestReadingResponse>

    @POST("api/v1/forecast")
    suspend fun generateForecast(
        @Body request: ForecastRequest
    ): Response<ForecastResponse>
}
