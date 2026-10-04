package com.example

import com.example.data.repository.DevelopmentAuthPolicy
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

    @Test fun studentSessionOpensStudentHome() {
        assertEquals("student", DevelopmentAuthPolicy.destinationForRole("STUDENT"))
    }

    @Test fun adminSessionOpensAdminDashboard() {
        assertEquals("admin", DevelopmentAuthPolicy.destinationForRole("ADMIN"))
    }

    @Test fun localStudentAndAdminSessionsHaveTheirOwnRoles() = runBlocking {
        val context = RuntimeEnvironment.getApplication()
        val database = Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java)
            .allowMainThreadQueries().build()
        try {
            val repository = FirebaseAuthRepository(database.hydroDao(), context)
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
}

