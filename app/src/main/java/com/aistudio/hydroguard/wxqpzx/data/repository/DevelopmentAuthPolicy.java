package com.aistudio.hydroguard.wxqpzx.data.repository;

import android.content.Context;
import android.content.SharedPreferences;

import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

public final class DevelopmentAuthPolicy {
    private static final String PREFS = "hydroguard_debug_session";
    private static volatile String email;
    private static volatile String role;

    private DevelopmentAuthPolicy() { }

    public static boolean allows(boolean debugBuild, boolean explicitDevelopmentFlag) {
        return debugBuild && explicitDevelopmentFlag;
    }

    public static boolean apiBridgeConfigured(boolean debugBuild, boolean explicitDevelopmentFlag, String token) {
        return allows(debugBuild, explicitDevelopmentFlag) && token != null && !token.trim().isEmpty();
    }

    public static synchronized void restore(Context context, boolean debugBuild, boolean enabled, String token) {
        // A development identity is never reloaded from disk. Demo sign-in has to be
        // invoked explicitly by the user on every app launch, so anything left over
        // from a previous run is discarded here and only legacy storage is migrated.
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().clear().apply();
        if (!apiBridgeConfigured(debugBuild, enabled, token)) {
            email = null;
            role = null;
        }
    }

    public static synchronized void set(Context context, String newEmail, String newRole) {
        String normalizedRole = newRole == null ? "" : newRole.trim().toUpperCase(java.util.Locale.ROOT);
        if (!validIdentity(newEmail, normalizedRole)) throw new IllegalArgumentException("Unsupported development identity.");
        // Session-scoped only: kept in memory so it never authenticates a later app launch.
        email = newEmail.trim().toLowerCase(java.util.Locale.ROOT);
        role = normalizedRole;
    }

    public static synchronized void clear(Context context) {
        email = null;
        role = null;
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().clear().apply();
    }

    public static Map<String, String> current() {
        if (email == null || role == null) return Collections.emptyMap();
        Map<String, String> identity = new HashMap<>();
        identity.put("email", email);
        identity.put("role", role);
        return Collections.unmodifiableMap(identity);
    }

    public static Map<String, String> headers(boolean debugBuild, boolean enabled, String token) {
        Map<String, String> identity = current();
        if (!apiBridgeConfigured(debugBuild, enabled, token) || identity.isEmpty()) return Collections.emptyMap();
        Map<String, String> headers = new HashMap<>();
        headers.put("X-HydroGuard-Development-Token", token);
        headers.put("X-HydroGuard-Development-Role", identity.get("role"));
        headers.put("X-HydroGuard-Development-Uid", identity.get("email"));
        return Collections.unmodifiableMap(headers);
    }

    private static boolean validIdentity(String valueEmail, String valueRole) {
        if (valueEmail == null || valueRole == null) return false;
        String normalizedEmail = valueEmail.trim().toLowerCase(java.util.Locale.ROOT);
        String normalizedRole = valueRole.trim().toUpperCase(java.util.Locale.ROOT);
        return ("demo.student@hydroguard.local".equals(normalizedEmail) && "STUDENT".equals(normalizedRole))
                || ("demo.admin@hydroguard.local".equals(normalizedEmail) && "ADMIN".equals(normalizedRole));
    }
}
