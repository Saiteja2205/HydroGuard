package com.example.data.api

import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import java.util.concurrent.TimeUnit

object RetrofitClient {

    // Base URL configuration - supports both emulator and physical device
    // For Android Emulator: use 10.0.2.2 (special alias for host machine)
    // For Physical Device: use your PC's local IP address
    private const val BASE_URL = "http://10.0.2.2:8000/"

    // Alternative base URL for physical device testing
    // To use on physical device: set this to your PC's IP, e.g., "http://192.168.1.100:8000/"
    // Current Hotspot IP: 10.62.235.152
    private const val PHYSICAL_DEVICE_BASE_URL = "http://10.62.235.152:8000/"

    // Set to true when testing on physical device, false for emulator
    private val usePhysicalDeviceUrl = true

    private val loggingInterceptor = HttpLoggingInterceptor().apply {
        level = HttpLoggingInterceptor.Level.BODY
    }

    private val okHttpClient = OkHttpClient.Builder()
        .addInterceptor(loggingInterceptor)
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    private val moshi = Moshi.Builder()
        .add(KotlinJsonAdapterFactory())
        .build()

    private val actualBaseUrl: String
        get() = if (usePhysicalDeviceUrl) PHYSICAL_DEVICE_BASE_URL else BASE_URL

    private val retrofit = Retrofit.Builder()
        .baseUrl(actualBaseUrl)
        .client(okHttpClient)
        .addConverterFactory(MoshiConverterFactory.create(moshi))
        .build()

    val apiService: HydroGuardApiService by lazy {
        retrofit.create(HydroGuardApiService::class.java)
    }

    // Method to create service with custom base URL (for testing)
    fun createApiService(customBaseUrl: String): HydroGuardApiService {
        val customRetrofit = Retrofit.Builder()
            .baseUrl(customBaseUrl)
            .client(okHttpClient)
            .addConverterFactory(MoshiConverterFactory.create(moshi))
            .build()
        return customRetrofit.create(HydroGuardApiService::class.java)
    }

    // Get current base URL for debugging
    fun getCurrentBaseUrl(): String = actualBaseUrl
}
