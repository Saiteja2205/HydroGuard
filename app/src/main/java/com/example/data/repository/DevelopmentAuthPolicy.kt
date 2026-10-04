package com.example.data.repository

/** Shared policy makes the release denial independently testable. */
internal object DevelopmentAuthPolicy {
    fun allows(debugBuild: Boolean, explicitDevelopmentFlag: Boolean): Boolean =
        debugBuild && explicitDevelopmentFlag

    fun destinationForRole(role: String): String =
        if (role.equals("ADMIN", ignoreCase = true)) "admin" else "student"
}
