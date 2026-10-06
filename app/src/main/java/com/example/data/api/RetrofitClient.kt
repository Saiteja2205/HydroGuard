package com.example.data.api

import android.util.Log
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.Response
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import com.example.BuildConfig
import com.google.firebase.auth.FirebaseAuth
import com.example.data.repository.DevelopmentApiSession
import java.io.IOException
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

object RetrofitClient {

    private val diagnosticsInterceptor = Interceptor { chain ->
        val request = chain.request()
        val url = request.url
        val endpoint = "${url.scheme}://${url.host}:${url.port}${url.encodedPath}"
        val startedAt = System.nanoTime()
        if (BuildConfig.DEBUG) Log.d("HydroGuardApi", "request ${request.method} $endpoint")
        try {
            val response = chain.proceed(request)
            val durationMs = (System.nanoTime() - startedAt) / 1_000_000
            if (BuildConfig.DEBUG) Log.d("HydroGuardApi", "response ${response.code} ${request.method} $endpoint ${durationMs}ms")
            response
        } catch (exception: IOException) {
            val durationMs = (System.nanoTime() - startedAt) / 1_000_000
            if (BuildConfig.DEBUG) Log.e("HydroGuardApi", "failure ${exception.javaClass.simpleName} ${request.method} $endpoint ${durationMs}ms")
            throw exception
        }
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
                DevelopmentApiSession.headers(BuildConfig.DEBUG, BuildConfig.DEVELOPMENT_API_TOKEN)
                    .forEach { (name, value) -> header(name, value) }
            }.build()
            chain.proceed(request)
        }
        .addInterceptor(diagnosticsInterceptor)
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
