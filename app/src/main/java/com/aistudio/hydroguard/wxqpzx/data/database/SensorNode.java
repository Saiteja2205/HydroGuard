package com.aistudio.hydroguard.wxqpzx.data.database;

import androidx.annotation.NonNull;
import androidx.room.Entity;
import androidx.room.Ignore;
import androidx.room.PrimaryKey;

@Entity(tableName = "sensor_nodes")
public class SensorNode {
    @PrimaryKey @NonNull public String nodeId = "";
    @NonNull public String name = "";
    @NonNull public String location = "";
    @NonNull public String status = "OFFLINE";
    public long lastSeen = System.currentTimeMillis();

    public SensorNode() { }

    @Ignore public SensorNode(@NonNull String nodeId, @NonNull String name, @NonNull String location,
                      @NonNull String status) {
        this.nodeId = nodeId;
        this.name = name;
        this.location = location;
        this.status = status;
    }
}
