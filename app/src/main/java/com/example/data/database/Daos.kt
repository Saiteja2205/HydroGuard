package com.example.data.database

import androidx.room.*
import kotlinx.coroutines.flow.Flow

@Dao
interface HydroDao {
    // Users
    @Query("SELECT * FROM users WHERE email = :email LIMIT 1")
    suspend fun getUserByEmail(email: String): User?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertUser(user: User)

    @Query("SELECT * FROM users")
    fun getAllUsers(): Flow<List<User>>

    // Sensor Nodes
    @Query("SELECT * FROM sensor_nodes")
    fun getAllNodes(): Flow<List<SensorNode>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertNode(node: SensorNode)

    @Query("SELECT * FROM sensor_nodes WHERE nodeId = :id LIMIT 1")
    suspend fun getNodeById(id: String): SensorNode?

    // Sensor Readings
    @Query("SELECT * FROM sensor_readings WHERE nodeId = :nodeId ORDER BY timestamp DESC LIMIT 50")
    fun getHistoricalReadings(nodeId: String): Flow<List<SensorReading>>

    @Query("SELECT * FROM sensor_readings WHERE nodeId = :nodeId ORDER BY timestamp DESC LIMIT 1")
    fun getLatestReading(nodeId: String): Flow<SensorReading?>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertReading(reading: SensorReading)

    // Predictions
    @Query("SELECT * FROM predictions WHERE nodeId = :nodeId LIMIT 1")
    fun getPredictionForNode(nodeId: String): Flow<Prediction?>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertPrediction(prediction: Prediction)

    // Alerts
    @Query("SELECT * FROM alerts ORDER BY timestamp DESC")
    fun getAllAlerts(): Flow<List<Alert>>

    @Query("SELECT * FROM alerts WHERE isResolved = 0 ORDER BY timestamp DESC")
    fun getUnresolvedAlerts(): Flow<List<Alert>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAlert(alert: Alert)

    @Query("UPDATE alerts SET isResolved = 1, resolvedAt = :resolvedAt, remarks = :remarks WHERE id = :alertId")
    suspend fun resolveAlert(alertId: String, resolvedAt: Long, remarks: String)

    // Notifications
    @Query("SELECT * FROM notifications ORDER BY timestamp DESC")
    fun getNotificationLogs(): Flow<List<NotificationLog>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertNotification(notification: NotificationLog)

    @Query("UPDATE notifications SET isRead = 1 WHERE id = :id")
    suspend fun markNotificationAsRead(id: Long)

    // Water Feedback
    @Query("SELECT * FROM water_feedback ORDER BY timestamp DESC")
    fun getAllWaterFeedback(): Flow<List<WaterFeedback>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertWaterFeedback(feedback: WaterFeedback)

    @Query("UPDATE water_feedback SET status = :status, remarks = :remarks, assignedStaff = :staff WHERE id = :id")
    suspend fun updateWaterFeedbackStatus(id: String, status: String, remarks: String?, staff: String?)

    // Hostel Feedback
    @Query("SELECT * FROM hostel_feedback ORDER BY timestamp DESC")
    fun getAllHostelFeedback(): Flow<List<HostelFeedback>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertHostelFeedback(feedback: HostelFeedback)

    @Query("UPDATE hostel_feedback SET status = :status, remarks = :remarks, assignedStaff = :staff WHERE id = :id")
    suspend fun updateHostelFeedbackStatus(id: String, status: String, remarks: String?, staff: String?)

    // Water Reports
    @Query("SELECT * FROM reports ORDER BY generatedAt DESC")
    fun getAllReports(): Flow<List<WaterQualityReport>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertReport(report: WaterQualityReport)

    // Audit Logs
    @Query("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 100")
    fun getAuditLogs(): Flow<List<AuditLog>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAuditLog(log: AuditLog)
}
