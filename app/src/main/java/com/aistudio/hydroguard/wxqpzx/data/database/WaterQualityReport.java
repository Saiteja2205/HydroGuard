package com.aistudio.hydroguard.wxqpzx.data.database;

import androidx.annotation.NonNull;
import androidx.room.Entity;
import androidx.room.PrimaryKey;

@Entity(tableName = "reports")
public class WaterQualityReport {
    @PrimaryKey @NonNull public String id = "";
    @NonNull public String title = "";
    @NonNull public String summary = "";
    public long generatedAt = System.currentTimeMillis();
    public float avgPh;
    public float avgTurbidity;
    public float avgTds;
    public int totalAlerts;
    public int totalComplaints;

    public WaterQualityReport() { }
}
