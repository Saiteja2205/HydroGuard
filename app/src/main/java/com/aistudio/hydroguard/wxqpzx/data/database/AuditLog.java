package com.aistudio.hydroguard.wxqpzx.data.database;

import androidx.annotation.NonNull;
import androidx.room.Entity;
import androidx.room.PrimaryKey;

@Entity(tableName = "audit_logs")
public class AuditLog {
    @PrimaryKey(autoGenerate = true) public long id;
    @NonNull public String adminEmail = "";
    @NonNull public String action = "";
    public long timestamp = System.currentTimeMillis();

    public AuditLog() { }
}
