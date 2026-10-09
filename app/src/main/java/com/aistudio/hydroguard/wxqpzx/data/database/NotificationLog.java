package com.aistudio.hydroguard.wxqpzx.data.database;

import androidx.annotation.NonNull;
import androidx.room.Entity;
import androidx.room.Index;
import androidx.room.PrimaryKey;

@Entity(tableName = "notifications", indices = @Index(value = {"dedupeKey"}, unique = true))
public class NotificationLog {
    @PrimaryKey(autoGenerate = true) public long id;
    @NonNull public String title = "";
    @NonNull public String body = "";
    public long timestamp = System.currentTimeMillis();
    public boolean isRead;
    @NonNull public String type = "SYSTEM";
    /** Stable key used to deduplicate repeated notifications for the same ongoing issue. */
    @NonNull public String dedupeKey = "";

    public NotificationLog() { }
}
