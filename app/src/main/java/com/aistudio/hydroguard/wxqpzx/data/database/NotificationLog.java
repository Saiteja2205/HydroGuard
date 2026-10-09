package com.aistudio.hydroguard.wxqpzx.data.database;

import androidx.annotation.NonNull;
import androidx.room.Entity;
import androidx.room.PrimaryKey;

@Entity(tableName = "notifications")
public class NotificationLog {
    @PrimaryKey(autoGenerate = true) public long id;
    @NonNull public String title = "";
    @NonNull public String body = "";
    public long timestamp = System.currentTimeMillis();
    public boolean isRead;
    @NonNull public String type = "SYSTEM";

    public NotificationLog() { }
}
