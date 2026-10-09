package com.aistudio.hydroguard.wxqpzx.data.database;

import androidx.annotation.NonNull;
import androidx.room.Entity;
import androidx.room.Ignore;
import androidx.room.PrimaryKey;

@Entity(tableName = "sensor_readings")
public class SensorReading {
    @PrimaryKey(autoGenerate = true) public long id;
    @NonNull public String nodeId = "";
    public long timestamp = System.currentTimeMillis();
    public float ph;
    public float turbidity;
    public float tds;
    public float temperature;
    public float flowRate;
    public Integer red;
    public Integer green;
    public Integer blue;
    public Integer clear;
    public Float opticalColourIndex;
    public Integer calibrationId;
    @NonNull public String source = "DEMO";

    public SensorReading() { }

    @Ignore public SensorReading(@NonNull String nodeId, long timestamp, float ph, float turbidity,
                         float tds, float temperature, Integer red, Integer green, Integer blue,
                         Integer clear, Float opticalColourIndex, Integer calibrationId,
                         @NonNull String source) {
        this.nodeId = nodeId;
        this.timestamp = timestamp;
        this.ph = ph;
        this.turbidity = turbidity;
        this.tds = tds;
        this.temperature = temperature;
        this.red = red;
        this.green = green;
        this.blue = blue;
        this.clear = clear;
        this.opticalColourIndex = opticalColourIndex;
        this.calibrationId = calibrationId;
        this.source = source;
    }
}
