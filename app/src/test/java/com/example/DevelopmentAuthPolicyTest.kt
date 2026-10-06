package com.example

import com.example.data.repository.DevelopmentAuthPolicy
import com.example.data.repository.DevelopmentApiSession
import com.example.data.database.AppDatabase
import com.example.data.repository.FirebaseAuthRepository
import kotlinx.coroutines.runBlocking
import androidx.room.Room
import org.robolectric.RuntimeEnvironment
import org.robolectric.RobolectricTestRunner
import org.junit.runner.RunWith
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.assertEquals
import org.junit.Test

@RunWith(RobolectricTestRunner::class)
class DevelopmentAuthPolicyTest {
    @Test fun debugDevelopmentLoginIsAllowed() {
        assertTrue(DevelopmentAuthPolicy.allows(debugBuild = true, explicitDevelopmentFlag = true))
    }

    @Test fun releaseBuildCannotEnableDevelopmentLogin() {
        assertFalse(DevelopmentAuthPolicy.allows(debugBuild = false, explicitDevelopmentFlag = true))
    }

    @Test fun disabledBuildFlagDeniesDevelopmentLogin() {
        assertFalse(DevelopmentAuthPolicy.allows(debugBuild = true, explicitDevelopmentFlag = false))
    }

    @Test fun developmentApiBridgeRequiresAConfiguredDebugToken() {
        assertTrue(DevelopmentAuthPolicy.apiBridgeConfigured(true, true, "local-test-token"))
        assertFalse(DevelopmentAuthPolicy.apiBridgeConfigured(true, true, ""))
        assertFalse(DevelopmentAuthPolicy.apiBridgeConfigured(false, true, "local-test-token"))
    }

    @Test fun studentSessionOpensStudentHome() {
        assertEquals("student", DevelopmentAuthPolicy.destinationForRole("STUDENT"))
    }

    @Test fun adminSessionOpensAdminDashboard() {
        assertEquals("admin", DevelopmentAuthPolicy.destinationForRole("ADMIN"))
    }

    @Test fun developmentApiSessionIsClearedAtSignOut() {
        DevelopmentApiSession.set("demo.admin@hydroguard.local", "ADMIN")
        assertEquals("demo.admin@hydroguard.local" to "ADMIN", DevelopmentApiSession.current())
        DevelopmentApiSession.clear()
        assertEquals(null, DevelopmentApiSession.current())
    }

    @Test fun developmentApiHeadersAreSharedByDebugRequestsAndNeverAddedToReleaseRequests() {
        DevelopmentApiSession.set("demo.student@hydroguard.local", "STUDENT")
        try {
            assertEquals(
                mapOf(
                    "X-HydroGuard-Development-Token" to "local-test-token",
                    "X-HydroGuard-Development-Role" to "STUDENT",
                    "X-HydroGuard-Development-Uid" to "demo.student@hydroguard.local"
                ),
                DevelopmentApiSession.headers(debugBuild = true, token = "local-test-token")
            )
            assertTrue(DevelopmentApiSession.headers(debugBuild = false, token = "local-test-token").isEmpty())
            assertTrue(DevelopmentApiSession.headers(debugBuild = true, token = "").isEmpty())
        } finally {
            DevelopmentApiSession.clear()
        }
    }

    @Test fun localStudentAndAdminSessionsHaveTheirOwnRoles() = runBlocking {
        val context = RuntimeEnvironment.getApplication()
        val database = Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java)
            .allowMainThreadQueries().build()
        try {
            val repository = FirebaseAuthRepository(database.hydroDao(), context, "local-test-token")
            val student = repository.loginAsDevelopment("STUDENT").getOrThrow()
            assertEquals("demo.student@hydroguard.local", student.email)
            assertEquals("STUDENT", student.role)
            assertEquals(student, database.hydroDao().getUserByEmail(student.email))

            val admin = repository.loginAsDevelopment("ADMIN").getOrThrow()
            assertEquals("demo.admin@hydroguard.local", admin.email)
            assertEquals("ADMIN", admin.role)
            assertEquals(admin, database.hydroDao().getUserByEmail(admin.email))
        } finally {
            database.close()
        }
    }

    @Test fun developmentLoginRefusesToCreateAnUnauthenticatedLocalSession() = runBlocking {
        val context = RuntimeEnvironment.getApplication()
        val database = Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java)
            .allowMainThreadQueries().build()
        try {
            val repository = FirebaseAuthRepository(database.hydroDao(), context, "")
            val result = repository.loginAsDevelopment("STUDENT")
            assertTrue(result.isFailure)
            assertEquals("Development login is not configured.", result.exceptionOrNull()?.message)
            assertEquals(null, DevelopmentApiSession.current())
            assertEquals(null, database.hydroDao().getUserByEmail("demo.student@hydroguard.local"))
        } finally {
            database.close()
        }
    }
}

