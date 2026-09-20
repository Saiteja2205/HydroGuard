package com.example.data.repository

import android.content.Context
import android.util.Log
import com.example.data.database.*
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.UUID

class HydroRepository(
    private val dao: HydroDao,
    private val scope: CoroutineScope
) {
    // Flows from Dao
    val allNodes: Flow<List<SensorNode>> = dao.getAllNodes()
    val allAlerts: Flow<List<Alert>> = dao.getAllAlerts()
    val activeAlerts: Flow<List<Alert>> = dao.getUnresolvedAlerts()
    val notificationLogs: Flow<List<NotificationLog>> = dao.getNotificationLogs()
    val waterFeedbackList: Flow<List<WaterFeedback>> = dao.getAllWaterFeedback()
    val hostelFeedbackList: Flow<List<HostelFeedback>> = dao.getAllHostelFeedback()
    val reportsList: Flow<List<WaterQualityReport>> = dao.getAllReports()
    val auditLogs: Flow<List<AuditLog>> = dao.getAuditLogs()

    fun getLatestReading(nodeId: String): Flow<SensorReading?> = dao.getLatestReading(nodeId)
    fun getHistoricalReadings(nodeId: String): Flow<List<SensorReading>> = dao.getHistoricalReadings(nodeId)
    fun getPrediction(nodeId: String): Flow<Prediction?> = dao.getPredictionForNode(nodeId)

    init {
        scope.launch {
            seedInitialDataIfNeeded()
            startSensorSimulation()
        }
    }

    private suspend fun seedInitialDataIfNeeded() = withContext(Dispatchers.IO) {
        // Check if DB is already seeded by checking users
        val existingUser = dao.getUserByEmail("admin@hostel.edu")
        if (existingUser != null) return@withContext

        Log.d("HydroRepository", "Database empty. Seeding professional initial data...")

        // 1. Seed Users
        dao.insertUser(User("admin@hostel.edu", "Prof. Rajat Sen", "ADMIN", "A", "Admin Office"))
        dao.insertUser(User("student@hostel.edu", "Ananya Verma", "STUDENT", "A", "304"))
        dao.insertUser(User("student2@hostel.edu", "Rahul Sharma", "STUDENT", "B", "112"))

        // 2. Seed Sensor Nodes
        val nodes = listOf(
            SensorNode("node_overhead_a", "Block A Overhead Storage", "Block A - Roof", "ONLINE"),
            SensorNode("node_overhead_b", "Block B Overhead Storage", "Block B - Roof", "ONLINE"),
            SensorNode("node_mess", "Mess Main Purification Plant", "Dining Hall - GF", "ONLINE")
        )
        for (node in nodes) {
            dao.insertNode(node)
        }

        // 3. Seed Historical Readings (20 hours of history for each node)
        val now = System.currentTimeMillis()
        val hourMs = 3600000L

        // Block A: Safe but slightly shifting
        for (i in 20 downTo 1) {
            val ts = now - i * hourMs
            dao.insertReading(
                SensorReading(
                    nodeId = "node_overhead_a",
                    timestamp = ts,
                    ph = 7.2f + (-0.1f..0.1f).random(),
                    turbidity = 1.2f + (-0.2f..0.2f).random(),
                    tds = 180f + (-5f..5f).random(),
                    temperature = 22.4f + (-0.5f..0.5f).random(),
                    flowRate = 18.0f + (-1f..1f).random()
                )
            )
        }

        // Block B: Had a high turbidity warning event yesterday
        for (i in 20 downTo 1) {
            val ts = now - i * hourMs
            val phVal = if (i == 8) 6.1f else (7.4f + (-0.1f..0.1f).random())
            val turbVal = if (i == 12) 6.4f else (1.5f + (-0.2f..0.2f).random())
            dao.insertReading(
                SensorReading(
                    nodeId = "node_overhead_b",
                    timestamp = ts,
                    ph = phVal,
                    turbidity = turbVal,
                    tds = 220f + (-8f..8f).random(),
                    temperature = 24.1f + (-0.4f..0.4f).random(),
                    flowRate = 14.5f + (-1.5f..1.5f).random()
                )
            )
        }

        // Mess plant: pristine condition
        for (i in 20 downTo 1) {
            val ts = now - i * hourMs
            dao.insertReading(
                SensorReading(
                    nodeId = "node_mess",
                    timestamp = ts,
                    ph = 7.0f + (-0.05f..0.05f).random(),
                    turbidity = 0.3f + (-0.05f..0.05f).random(),
                    tds = 95f + (-3f..3f).random(),
                    temperature = 19.8f + (-0.3f..0.3f).random(),
                    flowRate = 22.0f + (-0.5f..0.5f).random()
                )
            )
        }

        // 4. Seed some Alerts
        dao.insertAlert(
            Alert(
                id = "alert_historical_1",
                nodeId = "node_overhead_b",
                timestamp = now - 12 * hourMs,
                parameterName = "Turbidity",
                value = 6.4f,
                thresholdLimit = 5.0f,
                riskLevel = "Warning",
                title = "High Turbidity Warning",
                recommendation = "Sediment build-up detected. Standard filter backwash recommended.",
                isResolved = true,
                resolvedAt = now - 10 * hourMs,
                remarks = "Completed manual high-pressure filter flushing. Turbidity returned to normal."
            )
        )

        // 5. Seed some Notifications
        dao.insertNotification(
            NotificationLog(
                title = "System Calibrated",
                body = "All 3 IoT water nodes have been synced. Connection health: 100%.",
                type = "SYSTEM"
            )
        )
        dao.insertNotification(
            NotificationLog(
                title = "Water Quality Warning",
                body = "Overhead Tank B reported elevated Turbidity of 6.4 NTU. Inspection suggested.",
                type = "ALERT"
            )
        )

        // 6. Seed Student Feedback
        dao.insertWaterFeedback(
            WaterFeedback(
                id = "w_fb_1",
                rating = 2,
                issueType = "Yellow Water",
                description = "Water coming from Block A 3rd floor taps looks slightly yellow today morning.",
                imagePath = null,
                hostelBlock = "A",
                roomNumber = "304",
                timestamp = now - 6 * hourMs,
                status = "PENDING"
            )
        )
        dao.insertWaterFeedback(
            WaterFeedback(
                id = "w_fb_2",
                rating = 5,
                issueType = "Other",
                description = "Water pressure and taste are perfect in the mess hall water dispenser. Clean!",
                imagePath = null,
                hostelBlock = "Mess",
                roomNumber = "GF",
                timestamp = now - 24 * hourMs,
                status = "RESOLVED",
                remarks = "Feedback acknowledged with appreciation. Filtration parameters verified.",
                assignedStaff = "Chef Anand"
            )
        )

        dao.insertHostelFeedback(
            HostelFeedback(
                id = "h_fb_1",
                category = "Drinking Water",
                priority = "HIGH",
                description = "Water filter on 2nd floor Block B is leaking water constantly, creating a puddle.",
                imagePath = null,
                hostelBlock = "B",
                roomNumber = "2nd Floor Corridor",
                timestamp = now - 4 * hourMs,
                status = "PENDING"
            )
        )
        dao.insertHostelFeedback(
            HostelFeedback(
                id = "h_fb_2",
                category = "Cleanliness",
                priority = "LOW",
                description = "Washroom mirror is cracked in Block A level 3.",
                imagePath = null,
                hostelBlock = "A",
                roomNumber = "3rd Floor West Wing",
                timestamp = now - 36 * hourMs,
                status = "RESOLVED",
                remarks = "Replaced broken mirror with a brand new unit.",
                assignedStaff = "Maintenance Team"
            )
        )

        // 7. Seed initial Telemetry Summaries
        dao.insertPrediction(
            Prediction(
                nodeId = "node_overhead_a",
                timestamp = now,
                contaminationProbability = 4.0f,
                riskScore = 12.0f,
                confidence = 94.0f,
                predictionText = "SAFE STATUS: Baseline telemetry indicates optimal water condition. Low sediment, standard mineralization, and steady flow stability.",
                predictedPh = 7.3f,
                predictedTurbidity = 1.1f,
                predictedTds = 182f
            )
        )
        dao.insertPrediction(
            Prediction(
                nodeId = "node_overhead_b",
                timestamp = now,
                contaminationProbability = 18.0f,
                riskScore = 22.0f,
                confidence = 91.0f,
                predictionText = "STABILIZING STATUS: Water clarity is recovering following filtration backwash. Parameter stabilization monitored continuously.",
                predictedPh = 7.2f,
                predictedTurbidity = 1.8f,
                predictedTds = 215f
            )
        )
        dao.insertPrediction(
            Prediction(
                nodeId = "node_mess",
                timestamp = now,
                contaminationProbability = 1.0f,
                riskScore = 5.0f,
                confidence = 98.0f,
                predictionText = "EXCELLENT STATUS: Multi-stage RO filtration outputs optimal mineralization. System telemetry confirms zero contamination risks.",
                predictedPh = 7.0f,
                predictedTurbidity = 0.25f,
                predictedTds = 92f
            )
        )

        // 8. Seed Water Reports
        dao.insertReport(
            WaterQualityReport(
                id = "rep_weekly_1",
                title = "Weekly Water Health Audit (W4 June)",
                summary = "All facilities logged optimal ratings except for a brief Turbidity anomaly in Block B. Weekly average scores: 94% (A), 87% (B), 99% (Mess).",
                generatedAt = now - 2 * 24 * hourMs,
                avgPh = 7.15f,
                avgTurbidity = 1.45f,
                avgTds = 165f,
                totalAlerts = 1,
                totalComplaints = 2
            )
        )
    }

    private suspend fun startSensorSimulation() {
        while (true) {
            delay(10000) // Simulate reading stream updates from ESP32 every 10 seconds
            try {
                updateNodeReadings()
            } catch (e: Exception) {
                Log.e("HydroRepository", "Error during sensor stream simulation: ${e.message}")
            }
        }
    }

    private suspend fun updateNodeReadings() = withContext(Dispatchers.IO) {
        val now = System.currentTimeMillis()

        // We fetch nodes currently online
        val nodeList = listOf("node_overhead_a", "node_overhead_b", "node_mess")
        for (nodeId in nodeList) {
            // Get latest reading to base the new values on (keeps things continuous and realistic)
            val latest = dao.getLatestReading(nodeId).firstOrNull()

            val phDelta = (-0.08f..0.08f).random()
            val turbDelta = (-0.15f..0.15f).random()
            val tdsDelta = (-3f..3f).random()
            val tempDelta = (-0.1f..0.1f).random()
            val flowDelta = (-0.5f..0.5f).random()

            val basePh = latest?.ph ?: 7.2f
            val baseTurb = latest?.turbidity ?: 1.2f
            val baseTds = latest?.tds ?: 180f
            val baseTemp = latest?.temperature ?: 22.0f
            val baseFlow = latest?.flowRate ?: 15.0f

            // Add occasional simulated drift for variety / demo testing
            var finalPh = (basePh + phDelta).coerceIn(4.0f, 10.0f)
            var finalTurb = (baseTurb + turbDelta).coerceAtLeast(0.1f)
            var finalTds = (baseTds + tdsDelta).coerceAtLeast(10f)
            val finalTemp = (baseTemp + tempDelta).coerceIn(15f, 35f)
            val finalFlow = (baseFlow + flowDelta).coerceIn(2f, 30f)

            // Inject occasional anomaly in Block B for alerts demo
            if (nodeId == "node_overhead_b" && (1..12).random() == 5) {
                finalTurb = 5.8f // Drastic rise
                finalPh = 6.2f   // Drastic drift
                finalTds = 520f  // Elevates past safe ranges
                Log.d("HydroRepository", "SIMULATOR: Injected water quality alert parameters for $nodeId")
            }

            val newReading = SensorReading(
                nodeId = nodeId,
                timestamp = now,
                ph = finalPh,
                turbidity = finalTurb,
                tds = finalTds,
                temperature = finalTemp,
                flowRate = finalFlow
            )

            dao.insertReading(newReading)

            // Auto-trigger safety alert if limits breached
            checkThresholdsAndTriggerAlerts(newReading)
        }
    }

    private suspend fun checkThresholdsAndTriggerAlerts(reading: SensorReading) {
        val nodeName = when (reading.nodeId) {
            "node_overhead_a" -> "Block A Overhead Storage"
            "node_overhead_b" -> "Block B Overhead Storage"
            else -> "Mess Main Purification Plant"
        }

        // pH thresholds (< 6.5 or > 8.5)
        if (reading.ph < 6.5f) {
            createAlert(
                reading.nodeId,
                "pH",
                reading.ph,
                6.5f,
                "Critical",
                "Unsafe pH Level (Acidic)",
                "Immediate inspection required. Extreme acidity detected. Safe range is 6.5 to 8.5. Corrosion risks in pipe layout.",
                nodeName
            )
        } else if (reading.ph > 8.5f) {
            createAlert(
                reading.nodeId,
                "pH",
                reading.ph,
                8.5f,
                "Warning",
                "Unsafe pH Level (Alkaline)",
                "Alkaline drift detected. Verify mineral treatment settings. Safe range is 6.5 to 8.5.",
                nodeName
            )
        }

        // Turbidity threshold (> 5.0 NTU)
        if (reading.turbidity > 5.0f) {
            createAlert(
                reading.nodeId,
                "Turbidity",
                reading.turbidity,
                5.0f,
                "Critical",
                "High Turbidity Detected",
                "High particulate density in $nodeName water supply. Mud/sediment infiltration suspected. Immediate bypass filtration flushing required.",
                nodeName
            )
        }

        // TDS threshold (> 500 mg/L)
        if (reading.tds > 500f) {
            createAlert(
                reading.nodeId,
                "TDS",
                reading.tds,
                500f,
                "Warning",
                "Elevated Total Dissolved Solids",
                "TDS levels exceed ideal 500 mg/L limit. Water may taste salty/metallic and contain high mineral clusters. Service filtration unit.",
                nodeName
            )
        }
    }

    private suspend fun createAlert(
        nodeId: String,
        param: String,
        valMeasured: Float,
        limit: Float,
        risk: String,
        title: String,
        recom: String,
        nodeName: String
    ) {
        val alertId = "alert_${nodeId}_${param}_${System.currentTimeMillis() / 1000}"
        
        // Check if there is already an active (unresolved) alert for this same node and parameter
        // to avoid duplicate notification spamming.
        val hasActive = dao.getUnresolvedAlerts().firstOrNull()?.any {
            it.nodeId == nodeId && it.parameterName == param
        } ?: false

        if (hasActive) return

        val alert = Alert(
            id = alertId,
            nodeId = nodeId,
            timestamp = System.currentTimeMillis(),
            parameterName = param,
            value = valMeasured,
            thresholdLimit = limit,
            riskLevel = risk,
            title = title,
            recommendation = recom,
            isResolved = false
        )

        dao.insertAlert(alert)

        // Generate matching Notification Log
        val notification = NotificationLog(
            title = "$title at $nodeName",
            body = "Measured $param: $valMeasured (Limit: $limit). Risk Level: $risk. Action: $recom",
            type = "ALERT"
        )
        dao.insertNotification(notification)
        Log.d("HydroRepository", "ALERT FIRED: $title at $nodeId ($valMeasured / $limit)")
    }

    // Interactive helper actions
    suspend fun addNewWaterFeedback(
        rating: Int,
        issueType: String,
        description: String,
        block: String,
        room: String,
        imagePath: String?
    ) = withContext(Dispatchers.IO) {
        val feedback = WaterFeedback(
            id = "w_fb_" + UUID.randomUUID().toString().take(6),
            rating = rating,
            issueType = issueType,
            description = description,
            imagePath = imagePath,
            hostelBlock = block,
            roomNumber = room,
            timestamp = System.currentTimeMillis(),
            status = "PENDING"
        )
        dao.insertWaterFeedback(feedback)
    }

    suspend fun addNewHostelFeedback(
        category: String,
        priority: String,
        description: String,
        block: String,
        room: String,
        imagePath: String?
    ) = withContext(Dispatchers.IO) {
        val feedback = HostelFeedback(
            id = "h_fb_" + UUID.randomUUID().toString().take(6),
            category = category,
            priority = priority,
            description = description,
            imagePath = imagePath,
            hostelBlock = block,
            roomNumber = room,
            timestamp = System.currentTimeMillis(),
            status = "PENDING"
        )
        dao.insertHostelFeedback(feedback)
    }

    suspend fun resolveWaterFeedback(feedbackId: String, remarks: String, staff: String, adminEmail: String) = withContext(Dispatchers.IO) {
        dao.updateWaterFeedbackStatus(feedbackId, "RESOLVED", remarks, staff)
        dao.insertAuditLog(AuditLog(adminEmail = adminEmail, action = "Resolved water complaint $feedbackId"))
    }

    suspend fun resolveHostelFeedback(feedbackId: String, remarks: String, staff: String, adminEmail: String) = withContext(Dispatchers.IO) {
        dao.updateHostelFeedbackStatus(feedbackId, "RESOLVED", remarks, staff)
        dao.insertAuditLog(AuditLog(adminEmail = adminEmail, action = "Resolved facility complaint $feedbackId"))
    }

    suspend fun resolveAlert(alertId: String, remarks: String, adminEmail: String) = withContext(Dispatchers.IO) {
        dao.resolveAlert(alertId, System.currentTimeMillis(), remarks)
        dao.insertAuditLog(AuditLog(adminEmail = adminEmail, action = "Resolved critical water alert $alertId"))
    }

    suspend fun configureThreshold(nodeId: String, param: String, newThreshold: Float, adminEmail: String) = withContext(Dispatchers.IO) {
        dao.insertAuditLog(AuditLog(adminEmail = adminEmail, action = "Updated threshold for $nodeId parameter $param to $newThreshold"))
    }

    suspend fun exportReport(title: String, summary: String, ph: Float, turb: Float, tds: Float, alertsCount: Int, feedbackCount: Int, adminEmail: String) = withContext(Dispatchers.IO) {
        val report = WaterQualityReport(
            id = "rep_" + UUID.randomUUID().toString().take(6),
            title = title,
            summary = summary,
            avgPh = ph,
            avgTurbidity = turb,
            avgTds = tds,
            totalAlerts = alertsCount,
            totalComplaints = feedbackCount
        )
        dao.insertReport(report)
        dao.insertAuditLog(AuditLog(adminEmail = adminEmail, action = "Generated system export report: $title"))
    }

    // Helper math extension range
    private fun ClosedRange<Float>.random() = (Math.random() * (endInclusive - start) + start).toFloat()
}
