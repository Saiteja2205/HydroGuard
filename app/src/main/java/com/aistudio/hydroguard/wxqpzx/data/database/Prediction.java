package com.aistudio.hydroguard.wxqpzx.data.database;

import androidx.annotation.NonNull;
import androidx.room.Entity;
import androidx.room.PrimaryKey;

@Entity(tableName = "predictions")
public class Prediction {
    @PrimaryKey @NonNull public String nodeId = "";
    public long timestamp = System.currentTimeMillis();
    public float contaminationProbability;
    public float riskScore;
    public float confidence;
    @NonNull public String predictionText = "";
    public float predictedPh;
    public float predictedTurbidity;
    public float predictedTds;

    public Prediction() { }
}
