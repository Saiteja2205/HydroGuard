package com.example.data.api

import com.squareup.moshi.Json

data class AuthenticatedUserResponse(
    val uid: String,
    val email: String,
    @Json(name = "display_name") val displayName: String,
    val role: String,
    val status: String
)

data class DevelopmentSessionResponse(
    @Json(name = "custom_token") val customToken: String
)

data class AdminUserResponse(
    val id: Int,
    val email: String,
    @Json(name = "display_name") val displayName: String?,
    val role: String,
    val status: String,
    @Json(name = "created_at") val createdAt: String,
    @Json(name = "updated_at") val updatedAt: String
)

data class AdminInviteRequest(val email: String)

data class AdminUserStatusRequest(val status: String)
