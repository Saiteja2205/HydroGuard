package com.aistudio.hydroguard.wxqpzx.data.repository;

import android.os.Handler;
import android.os.Looper;

import com.aistudio.hydroguard.wxqpzx.data.api.ApiCallback;
import com.aistudio.hydroguard.wxqpzx.data.api.ApiFailure;
import com.aistudio.hydroguard.wxqpzx.data.api.ApiRepository;
import com.aistudio.hydroguard.wxqpzx.data.database.HydroDao;
import com.aistudio.hydroguard.wxqpzx.data.database.SensorReading;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.text.ParseException;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class HydroRepository {
    public interface DataCallback {
        void onSuccess(String json, boolean fromCache, ApiFailure apiWarning);
        void onFailure(ApiFailure failure);
    }

    private final HydroDao dao;
    private final ApiRepository api;
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());

    public HydroRepository(HydroDao dao, ApiRepository api) {
        this.dao = dao;
        this.api = api;
    }

    public void loadLatest(String nodeId, DataCallback callback) {
        api.getLatestReading(nodeId, new ApiCallback() {
            @Override public void onSuccess(String json) {
                io.execute(() -> {
                    try {
                        dao.insertReading(fromJson(new JSONObject(json)));
                        main.post(() -> callback.onSuccess(json, false, null));
                    } catch (Exception error) {
                        main.post(() -> callback.onSuccess(json, false, null));
                    }
                });
            }
            @Override public void onFailure(ApiFailure failure) {
                io.execute(() -> {
                    SensorReading cached = dao.getLatestReading(nodeId);
                    if (cached == null) main.post(() -> callback.onFailure(failure));
                    else main.post(() -> callback.onSuccess(toJson(cached).toString(), true, failure));
                });
            }
        });
    }

    public void loadHistory(String nodeId, int limit, DataCallback callback) {
        api.getReadingHistory(nodeId, limit, new ApiCallback() {
            @Override public void onSuccess(String json) {
                io.execute(() -> {
                    try {
                        JSONArray readings = new JSONObject(json).optJSONArray("readings");
                        if (readings != null) {
                            List<SensorReading> mapped = new ArrayList<>();
                            for (int i = 0; i < readings.length(); i++) {
                                JSONObject value = readings.optJSONObject(i);
                                if (value != null) mapped.add(fromJson(value));
                            }
                            dao.insertReadings(mapped);
                        }
                    } catch (Exception ignored) { }
                    main.post(() -> callback.onSuccess(json, false, null));
                });
            }
            @Override public void onFailure(ApiFailure failure) {
                io.execute(() -> {
                    List<SensorReading> cached = dao.getHistoricalReadings(nodeId);
                    if (cached.isEmpty()) {
                        main.post(() -> callback.onFailure(failure));
                        return;
                    }
                    JSONArray readings = new JSONArray();
                    for (SensorReading row : cached) readings.put(toJson(row));
                    JSONObject result = new JSONObject();
                    try { result.put("readings", readings); result.put("count", readings.length()); }
                    catch (JSONException ignored) { }
                    main.post(() -> callback.onSuccess(result.toString(), true, failure));
                });
            }
        });
    }

    public void loadAlerts(String nodeId, ApiCallback callback) { api.getAlerts(nodeId, callback); }

    private SensorReading fromJson(JSONObject json) {
        SensorReading row = new SensorReading();
        row.nodeId = json.optString("node_id", "node_overhead_a");
        row.timestamp = parseTimestamp(json.optString("timestamp", ""));
        row.ph = (float) json.optDouble("ph", 0.0);
        row.tds = (float) json.optDouble("tds", 0.0);
        row.turbidity = (float) json.optDouble("turbidity", 0.0);
        row.temperature = (float) json.optDouble("temperature", 0.0);
        row.red = nullableInt(json, "red");
        row.green = nullableInt(json, "green");
        row.blue = nullableInt(json, "blue");
        row.clear = nullableInt(json, "clear");
        row.opticalColourIndex = nullableFloat(json, "optical_colour_index");
        row.calibrationId = nullableInt(json, "calibration_id");
        row.source = json.optString("source", "UNKNOWN");
        return row;
    }

    private JSONObject toJson(SensorReading row) {
        JSONObject json = new JSONObject();
        try {
            json.put("node_id", row.nodeId);
            json.put("timestamp", timestampText(row.timestamp));
            json.put("ph", row.ph);
            json.put("tds", row.tds);
            json.put("turbidity", row.turbidity);
            json.put("temperature", row.temperature);
            json.put("red", row.red == null ? JSONObject.NULL : row.red);
            json.put("green", row.green == null ? JSONObject.NULL : row.green);
            json.put("blue", row.blue == null ? JSONObject.NULL : row.blue);
            json.put("clear", row.clear == null ? JSONObject.NULL : row.clear);
            json.put("optical_colour_index", row.opticalColourIndex == null ? JSONObject.NULL : row.opticalColourIndex);
            json.put("calibration_id", row.calibrationId == null ? JSONObject.NULL : row.calibrationId);
            json.put("source", row.source);
        } catch (JSONException ignored) { }
        return json;
    }

    private Integer nullableInt(JSONObject object, String key) {
        return object.has(key) && !object.isNull(key) ? object.optInt(key) : null;
    }

    private Float nullableFloat(JSONObject object, String key) {
        if (!object.has(key) || object.isNull(key)) return null;
        double value = object.optDouble(key, Double.NaN);
        return Double.isNaN(value) ? null : (float) value;
    }

    private long parseTimestamp(String value) {
        if (value == null || value.isEmpty()) return System.currentTimeMillis();
        String normalized = value.endsWith("Z") ? value.substring(0, value.length() - 1) + "+0000" : value;
        SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssZ", Locale.US);
        format.setTimeZone(TimeZone.getTimeZone("UTC"));
        try { Date parsed = format.parse(normalized); return parsed == null ? System.currentTimeMillis() : parsed.getTime(); }
        catch (ParseException ignored) { return System.currentTimeMillis(); }
    }

    private String timestampText(long value) {
        SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US);
        format.setTimeZone(TimeZone.getTimeZone("UTC"));
        return format.format(new Date(value));
    }
}
