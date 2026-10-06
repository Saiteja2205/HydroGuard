package com.example.data.repository

/** Shared policy makes the release denial independently testable. */
internal object DevelopmentAuthPolicy {
    fun allows(debugBuild: Boolean, explicitDevelopmentFlag: Boolean): Boolean =
        debugBuild && explicitDevelopmentFlag

    fun apiBridgeConfigured(debugBuild: Boolean, explicitDevelopmentFlag: Boolean, token: String): Boolean =
        allows(debugBuild, explicitDevelopmentFlag) && token.isNotBlank()

    fun destinationForRole(role: String): String =
        if (role.equals("ADMIN", ignoreCase = true)) "admin" else "student"
}

/** Process-local identity populated only by the debug development sign-in flow. */
internal object DevelopmentApiSession {
    @Volatile private var identity: Pair<String, String>? = null

    fun set(email: String, role: String) {
        identity = email to role.uppercase()
    }

    fun clear() {
        identity = null
    }

    fun current(): Pair<String, String>? = identity

    fun headers(debugBuild: Boolean, token: String): Map<String, String> {
        val currentIdentity = identity ?: return emptyMap()
        if (!debugBuild || token.isBlank()) return emptyMap()
        return mapOf(
            "X-HydroGuard-Development-Token" to token,
            "X-HydroGuard-Development-Role" to currentIdentity.second,
            "X-HydroGuard-Development-Uid" to currentIdentity.first
        )
    }
}
