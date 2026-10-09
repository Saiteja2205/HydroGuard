package com.aistudio.hydroguard.wxqpzx.data.database;

import androidx.annotation.NonNull;
import androidx.room.Entity;
import androidx.room.PrimaryKey;

@Entity(tableName = "water_feedback")
public class WaterFeedback {
    @PrimaryKey @NonNull public String id = "";
    public int rating;
    @NonNull public String issueType = "";
    @NonNull public String description = "";
    public String imagePath;
    @NonNull public String hostelBlock = "";
    @NonNull public String roomNumber = "";
    public long timestamp = System.currentTimeMillis();
    @NonNull public String status = "PENDING";
    public String remarks;
    public String assignedStaff;

    public WaterFeedback() { }
}
