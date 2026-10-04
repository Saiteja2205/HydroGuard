package com.example.data.api

import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import com.example.BuildConfig
import com.google.firebase.auth.FirebaseAuth
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

object RetrofitClient {

    private val loggingInterceptor = HttpLoggingInterceptor().apply {
        level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.BODY else HttpLoggingInterceptor.Level.NONE
    }

    private val okHttpClient = OkHttpClient.Builder()
        .addInterceptor { chain ->
            val firebaseUser = runCatching { FirebaseAuth.getInstance().currentUser }.getOrNull()
            val token = firebaseUser?.let { user ->
                runCatching {
                    val task = user.getIdToken(false)
                    val completed = CountDownLatch(1)
                    task.addOnCompleteListener { completed.countDown() }
                    if (!completed.await(12, TimeUnit.SECONDS) || !task.isSuccessful) null
                    else task.result?.token
                }.getOrNull()
            }
            val request = chain.request().newBuilder().apply {
                if (!token.isNullOrBlank()) header("Authorization", "Bearer $token")
            }.build()
            chain.proceed(request)
        }
        .addInterceptor(loggingInterceptor)
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    private val moshi = Moshi.Builder()
        .add(KotlinJsonAdapterFactory())
        .build()

    private val actualBaseUrl: String = BuildConfig.API_BASE_URL

    init {
        require(actualBaseUrl.startsWith("https://") || (BuildConfig.DEBUG && actualBaseUrl.startsWith("http://"))) {
            "A production HTTPS API URL must be configured."
        }
    }

    private val retrofit = Retrofit.Builder()
        .baseUrl(actualBaseUrl)
        .client(okHttpClient)
        .addConverterFactory(MoshiConverterFactory.create(moshi))
        .build()

    val apiService: HydroGuardApiService by lazy {
        retrofit.create(HydroGuardApiService::class.java)
    }

    // Create service with a custom base URL for testing
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
