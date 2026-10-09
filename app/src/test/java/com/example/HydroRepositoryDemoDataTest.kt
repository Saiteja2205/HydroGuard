package com.example

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import android.content.Context
import com.example.data.database.AppDatabase
import com.example.data.database.SensorReading
import com.example.data.database.User
import com.example.data.repository.HydroRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class HydroRepositoryDemoDataTest {
    private lateinit var database: AppDatabase
    private lateinit var seedScope: CoroutineScope

    @Before
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        database = Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        seedScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    }

    @After
    fun tearDown() {
        seedScope.cancel()
        database.close()
    }

    @Test
    fun existingDebugDatabaseIsToppedUpAndRoomHistoryFlowEmitsUpdates() = runBlocking {
        val dao = database.hydroDao()
        dao.insertUser(User("admin@hostel.edu", "Admin", "ADMIN", "A", "Office"))
        val now = System.currentTimeMillis()
        for (nodeId in listOf("node_overhead_a", "node_overhead_b", "node_mess")) {
            for (hoursAgo in 20 downTo 1) {
                dao.insertReading(
                    SensorReading(
                        nodeId = nodeId,
                        timestamp = now - hoursAgo * 60L * 60L * 1000L,
                        ph = 7.1f,
                        turbidity = 1.0f,
                        tds = 150f,
                        temperature = 21f,
                        source = "DEMO"
                    )
                )
            }
        }

        HydroRepository(dao, seedScope)

        withTimeout(20_000) {
            while (listOf("node_overhead_a", "node_overhead_b", "node_mess")
                    .any { dao.countReadings(it, "DEMO") < 200 }) {
                delay(25)
            }
        }

        listOf("node_overhead_a", "node_overhead_b", "node_mess").forEach { nodeId ->
            assertEquals(200, dao.countReadings(nodeId, "DEMO"))
            val history = dao.getHistoricalReadings(nodeId).first()
            assertEquals(200, history.count { it.source == "DEMO" })
            assertTrue(history.all { it.ph.isFinite() && it.tds.isFinite() && it.turbidity.isFinite() && it.temperature.isFinite() })
        }

        val insertedAt = System.currentTimeMillis() + 1_000L
        dao.insertReading(
            SensorReading(
                nodeId = "node_overhead_a",
                timestamp = insertedAt,
                ph = 7.2f,
                turbidity = 1.1f,
                tds = 151f,
                temperature = 21.1f,
                source = "SIMULATED"
            )
        )
        val emittedHistory = withTimeout(5_000) {
            dao.getHistoricalReadings("node_overhead_a").first { rows -> rows.firstOrNull()?.timestamp == insertedAt }
        }
        assertEquals("SIMULATED", emittedHistory.first().source)
    }
}
