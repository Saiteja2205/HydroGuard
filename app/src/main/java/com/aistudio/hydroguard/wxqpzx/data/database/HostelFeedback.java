package com.aistudio.hydroguard.wxqpzx.data.database;

import androidx.annotation.NonNull;
import androidx.room.Entity;
import androidx.room.PrimaryKey;

@Entity(tableName = "hostel_feedback")
public class HostelFeedback {
    @PrimaryKey @NonNull public String id = "";
    @NonNull public String category = "";
    @NonNull public String priority = "MEDIUM";
    @NonNull public String description = "";
    public String imagePath;
    @NonNull public String hostelBlock = "";
    @NonNull public String roomNumber = "";
    public long timestamp = System.currentTimeMillis();
    @NonNull public String status = "PENDING";
    public String remarks;
    public String assignedStaff;

    public HostelFeedback() { }
}
