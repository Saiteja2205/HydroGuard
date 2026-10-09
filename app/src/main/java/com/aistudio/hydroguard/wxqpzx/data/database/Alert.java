package com.aistudio.hydroguard.wxqpzx.data.database;

import androidx.annotation.NonNull;
import androidx.room.Entity;
import androidx.room.PrimaryKey;

@Entity(tableName = "alerts")
public class Alert {
    @PrimaryKey @NonNull public String id = "";
    @NonNull public String nodeId = "";
    public long timestamp = System.currentTimeMillis();
    @NonNull public String parameterName = "";
    public float value;
    public float thresholdLimit;
    @NonNull public String riskLevel = "WARNING";
    @NonNull public String title = "";
    @NonNull public String recommendation = "";
    public boolean isResolved;
    public Long resolvedAt;
    public String remarks;

    public Alert() { }
}
