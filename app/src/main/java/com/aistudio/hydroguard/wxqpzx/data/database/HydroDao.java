package com.aistudio.hydroguard.wxqpzx.data.database;

import androidx.lifecycle.LiveData;
import androidx.room.Dao;
import androidx.room.Insert;
import androidx.room.OnConflictStrategy;
import androidx.room.Query;
import androidx.room.Update;

import java.util.List;

@Dao
public interface HydroDao {
    @Query("SELECT * FROM users WHERE email = :email LIMIT 1")
    User getUserByEmail(String email);

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    void insertUser(User user);

    @Query("SELECT * FROM users")
    LiveData<List<User>> observeUsers();

    @Query("SELECT * FROM sensor_nodes ORDER BY nodeId")
    LiveData<List<SensorNode>> observeNodes();

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    void insertNode(SensorNode node);

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    void insertNodes(List<SensorNode> nodes);

    @Query("SELECT * FROM sensor_readings WHERE nodeId = :nodeId ORDER BY timestamp DESC LIMIT 500")
    LiveData<List<SensorReading>> observeHistoricalReadings(String nodeId);

    @Query("SELECT * FROM sensor_readings WHERE nodeId = :nodeId ORDER BY timestamp DESC LIMIT 500")
    List<SensorReading> getHistoricalReadings(String nodeId);

    @Query("SELECT COUNT(*) FROM sensor_readings WHERE nodeId = :nodeId AND source = :source")
    int countReadings(String nodeId, String source);

    @Query("SELECT * FROM sensor_readings WHERE nodeId = :nodeId ORDER BY timestamp DESC LIMIT 1")
    LiveData<SensorReading> observeLatestReading(String nodeId);

    @Query("SELECT * FROM sensor_readings WHERE nodeId = :nodeId ORDER BY timestamp DESC LIMIT 1")
    SensorReading getLatestReading(String nodeId);

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    void insertReading(SensorReading reading);

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    void insertReadings(List<SensorReading> readings);

    @Query("SELECT * FROM predictions WHERE nodeId = :nodeId LIMIT 1")
    LiveData<Prediction> observePrediction(String nodeId);

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    void insertPrediction(Prediction prediction);

    @Query("SELECT * FROM alerts ORDER BY timestamp DESC")
    LiveData<List<Alert>> observeAllAlerts();

    @Query("SELECT * FROM alerts WHERE isResolved = 0 ORDER BY timestamp DESC")
    LiveData<List<Alert>> observeActiveAlerts();

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    void insertAlert(Alert alert);

    @Query("UPDATE alerts SET isResolved = 1, resolvedAt = :resolvedAt, remarks = :remarks WHERE id = :alertId")
    void resolveAlert(String alertId, long resolvedAt, String remarks);

    @Query("SELECT * FROM notifications ORDER BY timestamp DESC")
    LiveData<List<NotificationLog>> observeNotifications();

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    void insertNotification(NotificationLog notification);

    @Query("UPDATE notifications SET isRead = 1 WHERE id = :id")
    void markNotificationAsRead(long id);

    @Query("SELECT * FROM water_feedback ORDER BY timestamp DESC")
    LiveData<List<WaterFeedback>> observeWaterFeedback();

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    void insertWaterFeedback(WaterFeedback feedback);

    @Query("UPDATE water_feedback SET status = :status, remarks = :remarks, assignedStaff = :staff WHERE id = :id")
    void updateWaterFeedbackStatus(String id, String status, String remarks, String staff);

    @Query("SELECT * FROM hostel_feedback ORDER BY timestamp DESC")
    LiveData<List<HostelFeedback>> observeHostelFeedback();

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    void insertHostelFeedback(HostelFeedback feedback);

    @Query("UPDATE hostel_feedback SET status = :status, remarks = :remarks, assignedStaff = :staff WHERE id = :id")
    void updateHostelFeedbackStatus(String id, String status, String remarks, String staff);

    @Query("SELECT * FROM reports ORDER BY generatedAt DESC")
    LiveData<List<WaterQualityReport>> observeReports();

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    void insertReport(WaterQualityReport report);

    @Query("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 100")
    LiveData<List<AuditLog>> observeAuditLogs();

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    void insertAuditLog(AuditLog log);
}
