package com.example.data.database

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "users")
data class User(
    @PrimaryKey val email: String,
    val name: String,
    val role: String, // "ADMIN" or "STUDENT"
    val hostelBlock: String,
    val roomNumber: String,
    val createdAt: Long = System.currentTimeMillis()
)

@Entity(tableName = "sensor_nodes")
data class SensorNode(
    @PrimaryKey val nodeId: String,
    val name: String, // e.g. "Block A Overhead Tank", "Mess Ground Water"
    val location: String, // Block / Floor
    val status: String, // "ONLINE", "OFFLINE", "MAINTENANCE"
    val lastSeen: Long = System.currentTimeMillis()
)

@Entity(tableName = "sensor_readings")
data class SensorReading(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val nodeId: String,
    val timestamp: Long = System.currentTimeMillis(),
    val ph: Float,
    val turbidity: Float,
    val tds: Float,
    val temperature: Float,
    val flowRate: Float
)

@Entity(tableName = "predictions")
data class Prediction(
    @PrimaryKey val nodeId: String,
    val timestamp: Long = System.currentTimeMillis(),
    val contaminationProbability: Float, // 0.0 - 100.0
    val riskScore: Float, // 0.0 - 100.0
    val confidence: Float, // 0.0 - 100.0
    val predictionText: String, // AI Insights
    val predictedPh: Float,
    val predictedTurbidity: Float,
    val predictedTds: Float
)

@Entity(tableName = "alerts")
data class Alert(
    @PrimaryKey val id: String,
    val nodeId: String,
    val timestamp: Long = System.currentTimeMillis(),
    val parameterName: String, // "pH", "Turbidity", etc.
    val value: Float,
    val thresholdLimit: Float,
    val riskLevel: String, // "Warning", "Critical"
    val title: String,
    val recommendation: String,
    val isResolved: Boolean = false,
    val resolvedAt: Long? = null,
    val remarks: String? = null
)

@Entity(tableName = "notifications")
data class NotificationLog(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val title: String,
    val body: String,
    val timestamp: Long = System.currentTimeMillis(),
    val isRead: Boolean = false,
    val type: String // "ALERT", "SYSTEM", "ANNOUNCEMENT"
)

@Entity(tableName = "water_feedback")
data class WaterFeedback(
    @PrimaryKey val id: String,
    val rating: Int, // 1-5
    val issueType: String, // "Dirty Water", "Yellow Water", etc.
    val description: String,
    val imagePath: String?, // Mock local photo URI or path
    val hostelBlock: String,
    val roomNumber: String,
    val timestamp: Long = System.currentTimeMillis(),
    val status: String = "PENDING", // "PENDING", "RESOLVED"
    val remarks: String? = null,
    val assignedStaff: String? = null
)

@Entity(tableName = "hostel_feedback")
data class HostelFeedback(
    @PrimaryKey val id: String,
    val category: String, // "Washrooms", "WiFi", etc.
    val priority: String, // "LOW", "MEDIUM", "HIGH", "CRITICAL"
    val description: String,
    val imagePath: String?,
    val hostelBlock: String,
    val roomNumber: String,
    val timestamp: Long = System.currentTimeMillis(),
    val status: String = "PENDING", // "PENDING", "RESOLVED"
    val remarks: String? = null,
    val assignedStaff: String? = null
)

@Entity(tableName = "reports")
data class WaterQualityReport(
    @PrimaryKey val id: String,
    val title: String, // e.g. "Weekly Report - June W4"
    val summary: String,
    val generatedAt: Long = System.currentTimeMillis(),
    val avgPh: Float,
    val avgTurbidity: Float,
    val avgTds: Float,
    val totalAlerts: Int,
    val totalComplaints: Int
)

@Entity(tableName = "audit_logs")
data class AuditLog(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val adminEmail: String,
    val action: String, // e.g. "Updated sensor thresholds", "Resolved alert #1"
    val timestamp: Long = System.currentTimeMillis()
)
