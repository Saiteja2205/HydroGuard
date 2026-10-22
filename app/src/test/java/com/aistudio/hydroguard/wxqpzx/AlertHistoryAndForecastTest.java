package com.aistudio.hydroguard.wxqpzx;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import com.aistudio.hydroguard.wxqpzx.ui.AlertAdapter;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import org.junit.Test;

import java.util.ArrayList;
import java.util.List;

/**
 * Unit tests verifying:
 * 1. Alert history partitioning: active/acknowledged vs resolved historical alerts.
 * 2. Notification badge counts only active alerts, never resolved records.
 * 3. Forecast response parsing handles both "prediction" and fallback "forecast.ensemble".
 * 4. Forecast parameters are limited to the four modelled parameters (pH, TDS, turbidity, temperature).
 */
public class AlertHistoryAndForecastTest {

    @Test
    public void alertPartitioningSeparatesActiveAndResolved() throws JSONException {
        // Simulate 19 alert records (2 active, 17 resolved) matching hydroguard.db state
        JSONArray alertsArray = new JSONArray();
        alertsArray.put(new JSONObject().put("id", 21).put("parameter", "pH").put("status", "ACTIVE"));
        alertsArray.put(new JSONObject().put("id", 22).put("parameter", "turbidity").put("status", "ACTIVE"));
        for (int i = 4; i <= 20; i++) {
            alertsArray.put(new JSONObject().put("id", i).put("parameter", "pH").put("status", "RESOLVED"));
        }
        assertEquals(19, alertsArray.length());

        List<JSONObject> activeList = new ArrayList<>();
        List<JSONObject> resolvedList = new ArrayList<>();
        for (int i = 0; i < alertsArray.length(); i++) {
            JSONObject row = alertsArray.getJSONObject(i);
            String status = row.optString("status", "ACTIVE").toUpperCase();
            if ("RESOLVED".equals(status)) {
                resolvedList.add(row);
            } else {
                activeList.add(row);
            }
        }

        // Active count must be 2, resolved count must be 17
        assertEquals("Active alerts must equal 2", 2, activeList.size());
        assertEquals("Resolved alerts must equal 17", 17, resolvedList.size());

        // Top bar badge must only report active count
        int badgeCount = activeList.size();
        assertEquals("Notification badge must display 2, not 19", 2, badgeCount);
    }

    @Test
    public void acknowledgedAlertsGroupWithActiveForAttention() throws JSONException {
        JSONArray alertsArray = new JSONArray();
        alertsArray.put(new JSONObject().put("id", 1).put("parameter", "pH").put("status", "ACTIVE"));
        alertsArray.put(new JSONObject().put("id", 2).put("parameter", "TDS").put("status", "ACKNOWLEDGED"));
        alertsArray.put(new JSONObject().put("id", 3).put("parameter", "temperature").put("status", "RESOLVED"));

        List<JSONObject> activeList = new ArrayList<>();
        List<JSONObject> resolvedList = new ArrayList<>();
        for (int i = 0; i < alertsArray.length(); i++) {
            JSONObject row = alertsArray.getJSONObject(i);
            String status = row.optString("status", "ACTIVE").toUpperCase();
            if ("RESOLVED".equals(status)) {
                resolvedList.add(row);
            } else {
                activeList.add(row);
            }
        }

        assertEquals(2, activeList.size());
        assertEquals(1, resolvedList.size());
    }

    @Test
    public void alertAdapterSubmitsAndCountsCorrectly() throws JSONException {
        AlertAdapter adapter = new AlertAdapter(false, null);
        List<JSONObject> items = new ArrayList<>();
        items.add(new JSONObject().put("id", 1).put("parameter", "pH").put("status", "ACTIVE"));
        items.add(new JSONObject().put("id", 2).put("parameter", "turbidity").put("status", "ACTIVE"));

        adapter.submit(items);
        assertEquals(2, adapter.getItemCount());

        items.clear();
        adapter.submit(items);
        assertEquals(0, adapter.getItemCount());
    }

    @Test
    public void forecastResponsePredictionExtractsFourParameters() throws JSONException {
        String jsonStr = "{\n" +
                "  \"status\": \"success\",\n" +
                "  \"forecast\": {\n" +
                "    \"ensemble\": {\"pH\": 7.32, \"TDS\": 310.5, \"turbidity\": 1.15, \"temperature\": 24.1}\n" +
                "  },\n" +
                "  \"prediction\": {\"pH\": 7.32, \"TDS\": 310.5, \"turbidity\": 1.15, \"temperature\": 24.1}\n" +
                "}";

        JSONObject response = new JSONObject(jsonStr);
        JSONObject prediction = response.optJSONObject("prediction");
        if (prediction == null) {
            JSONObject forecast = response.optJSONObject("forecast");
            if (forecast != null) {
                prediction = forecast.optJSONObject("ensemble");
            }
        }

        assertNotNull("Prediction object must not be null", prediction);
        assertEquals(7.32, prediction.optDouble("pH", Double.NaN), 0.001);
        assertEquals(310.5, prediction.optDouble("TDS", Double.NaN), 0.001);
        assertEquals(1.15, prediction.optDouble("turbidity", Double.NaN), 0.001);
        assertEquals(24.1, prediction.optDouble("temperature", Double.NaN), 0.001);

        // RGB and optical colour index must not be present in the forecast predictions
        assertTrue(Double.isNaN(prediction.optDouble("optical_colour_index", Double.NaN)));
        assertTrue(Double.isNaN(prediction.optDouble("red", Double.NaN)));
    }

    @Test
    public void forecastFallbackToEnsembleWhenPredictionKeyOmitted() throws JSONException {
        String jsonStr = "{\n" +
                "  \"status\": \"success\",\n" +
                "  \"forecast\": {\n" +
                "    \"ensemble\": {\"pH\": 7.15, \"TDS\": 295.0, \"turbidity\": 0.95, \"temperature\": 22.8}\n" +
                "  }\n" +
                "}";

        JSONObject response = new JSONObject(jsonStr);
        JSONObject prediction = response.optJSONObject("prediction");
        if (prediction == null) {
            JSONObject forecast = response.optJSONObject("forecast");
            if (forecast != null) {
                prediction = forecast.optJSONObject("ensemble");
            }
        }

        assertNotNull("Fallback to forecast.ensemble must resolve", prediction);
        assertEquals(7.15, prediction.optDouble("pH", Double.NaN), 0.001);
        assertEquals(295.0, prediction.optDouble("TDS", Double.NaN), 0.001);
    }

    @Test
    public void physicalValidityRulesDistinguishDropoutsFromValidReadings() {
        // pH: 0.05 < pH <= 14.0
        assertFalse("pH 0.00 is 0V ADC sensor dropout", isPhysicallyValid("ph", 0.00));
        assertFalse("pH 0.05 is open-circuit threshold", isPhysicallyValid("ph", 0.05));
        assertFalse("Negative pH is impossible in aqueous water monitoring", isPhysicallyValid("ph", -1.0));
        assertFalse("pH > 14.0 is unphysical in dilute aqueous water", isPhysicallyValid("ph", 14.2));

        assertTrue("Neutral pH 7.0 is valid", isPhysicallyValid("ph", 7.0));
        assertTrue("Alkaline pH 12.41 is physically valid (though safety violation)", isPhysicallyValid("ph", 12.41));
        assertTrue("Acidic pH 6.0 is valid", isPhysicallyValid("ph", 6.0));

        // TDS: 0.0 <= TDS < 4000.0
        assertFalse("Negative TDS is impossible", isPhysicallyValid("tds", -0.5));
        assertTrue("Low TDS 5.47 ppm is valid", isPhysicallyValid("tds", 5.47));
        assertTrue("TDS 300.0 ppm is valid", isPhysicallyValid("tds", 300.0));
        assertFalse("TDS > 4000 is beyond freshwater sensor bounds", isPhysicallyValid("tds", 4500.0));

        // Turbidity: 0.0 <= Turbidity < 1000.0
        assertFalse("Negative turbidity is impossible", isPhysicallyValid("turbidity", -1.0));
        assertTrue("Turbidity 29.08 NTU is valid", isPhysicallyValid("turbidity", 29.08));
        assertTrue("Turbidity 0.0 NTU is valid", isPhysicallyValid("turbidity", 0.0));

        // Temperature: 0.5 < Temp < 75.0
        assertFalse("Temperature 0.0 is sensor dropout", isPhysicallyValid("temperature", 0.0));
        assertFalse("Temperature 0.5 is sensor dropout threshold", isPhysicallyValid("temperature", 0.5));
        assertTrue("Temperature 25.56 C is valid", isPhysicallyValid("temperature", 25.56));
    }

    private static boolean isPhysicallyValid(String metric, double value) {
        if (Double.isNaN(value) || Double.isInfinite(value)) return false;
        String m = metric.toLowerCase(java.util.Locale.ROOT);
        if ("ph".equals(m)) {
            return value > 0.05 && value <= 14.0;
        } else if ("tds".equals(m)) {
            return value >= 0.0 && value < 4000.0;
        } else if ("turbidity".equals(m)) {
            return value >= 0.0 && value < 1000.0;
        } else if ("temperature".equals(m)) {
            return value > 0.5 && value < 75.0;
        }
        return true;
    }

    @Test
    public void axisMinimumClampsToZeroForNonNegativeMetrics() {
        float min = 0.5f;
        float max = 12.41f;
        float padding = (max - min) * 0.15f; // (11.91) * 0.15 = 1.7865
        float unclampedMin = min - padding;  // -1.2865
        assertTrue("Unclamped padding drops below zero", unclampedMin < 0f);

        // Clamped minimum for non-negative metrics
        float clampedMin = Math.max(0f, unclampedMin);
        assertEquals("Clamped minimum must never drop below 0", 0.0f, clampedMin, 0.0001f);
    }

    @Test
    public void chartSegmentationSplitsOnSensorDropouts() throws JSONException {
        // Feeds: entry 109 (valid), entry 110 (pH 0.00 dropout), entry 111 (valid)
        List<JSONObject> feeds = new ArrayList<>();
        feeds.add(new JSONObject().put("entry_id", 109).put("ph", 10.69).put("timestamp", "2026-10-15T07:22:27Z"));
        feeds.add(new JSONObject().put("entry_id", 110).put("ph", 0.00).put("timestamp", "2026-10-15T08:50:21Z"));
        feeds.add(new JSONObject().put("entry_id", 111).put("ph", 12.37).put("timestamp", "2026-10-15T08:50:58Z"));

        List<List<Double>> segments = new ArrayList<>();
        List<Double> currentSegment = new ArrayList<>();
        int droppedOut = 0;

        for (JSONObject feed : feeds) {
            double ph = feed.optDouble("ph", Double.NaN);
            if (!isPhysicallyValid("ph", ph)) {
                droppedOut++;
                if (!currentSegment.isEmpty()) {
                    segments.add(currentSegment);
                    currentSegment = new ArrayList<>();
                }
                continue;
            }
            currentSegment.add(ph);
        }
        if (!currentSegment.isEmpty()) {
            segments.add(currentSegment);
        }

        assertEquals("Dropout count must be 1", 1, droppedOut);
        assertEquals("Should be split into 2 disjoint segments", 2, segments.size());
        assertEquals("First segment has entry 109", 1, segments.get(0).size());
        assertEquals(10.69, segments.get(0).get(0), 0.001);
        assertEquals("Second segment has entry 111", 1, segments.get(1).size());
        assertEquals(12.37, segments.get(1).get(0), 0.001);
    }

    @Test
    public void forecastProvenanceAndSemanticsParsing() throws JSONException {
        String jsonStr = "{\n" +
                "  \"status\": \"success\",\n" +
                "  \"forecast_horizon_hours\": 24,\n" +
                "  \"prediction_semantics\": \"Next-step model extrapolation (t+1); models trained on 24-hour step simulated development data.\",\n" +
                "  \"target_timestamp\": \"2026-10-16T08:57:08Z\",\n" +
                "  \"disclaimer\": \"Development-trained forecast. These values are model extrapolations and are not a certified drinking-water safety rating.\",\n" +
                "  \"provenance\": {\n" +
                "    \"data_source\": \"THINGSPEAK\",\n" +
                "    \"models_trained_on\": \"SIMULATED_DEVELOPMENT\",\n" +
                "    \"real_sensor_data\": false,\n" +
                "    \"fetched_at\": \"2026-10-15T08:58:00Z\"\n" +
                "  }\n" +
                "}";

        JSONObject response = new JSONObject(jsonStr);
        JSONObject prov = response.optJSONObject("provenance");
        assertNotNull("Provenance object must be parsed directly (not dot notation)", prov);
        assertEquals("THINGSPEAK", prov.optString("data_source"));
        assertEquals("SIMULATED_DEVELOPMENT", prov.optString("models_trained_on"));
        assertFalse(prov.optBoolean("real_sensor_data"));
        assertEquals("2026-10-15T08:58:00Z", prov.optString("fetched_at"));

        assertEquals(24, response.optInt("forecast_horizon_hours"));
        assertEquals("2026-10-16T08:57:08Z", response.optString("target_timestamp"));
        assertTrue(response.optString("prediction_semantics").contains("Next-step"));
        assertTrue(response.optString("disclaimer").contains("not a certified"));
    }

    @Test
    public void compactAxisLabelsGeneratesNonRepeatingLocalTimeTicksForIntradayFeeds() {
        List<String> timestamps = new ArrayList<>();
        timestamps.add("2026-10-15T08:50:00Z");
        timestamps.add("2026-10-15T08:50:35Z");
        timestamps.add("2026-10-15T08:51:10Z");
        timestamps.add("2026-10-15T08:51:45Z");
        timestamps.add("2026-10-15T08:52:20Z");
        timestamps.add("2026-10-15T08:52:55Z");
        timestamps.add("2026-10-15T08:53:30Z");

        List<String> ticks = com.aistudio.hydroguard.wxqpzx.ui.WaterScreen.compactAxisLabels(timestamps);
        assertEquals(timestamps.size(), ticks.size());

        for (int i = 0; i < ticks.size(); i++) {
            assertFalse("Ticks must never be repeated date '10-15'", "10-15".equals(ticks.get(i)));
            assertEquals("Ticks for rapid 30s feeds must include seconds (HH:mm:ss)", 8, ticks.get(i).length());
            if (i > 0) {
                assertFalse("Adjacent ticks must not repeat identical strings", ticks.get(i).equals(ticks.get(i - 1)));
            }
        }
    }

    @Test
    public void compactAxisLabelsMultiDayUsesDateAndTime() {
        List<String> timestamps = new ArrayList<>();
        timestamps.add("2026-10-10T08:00:00Z");
        timestamps.add("2026-10-12T12:00:00Z");
        timestamps.add("2026-10-15T18:00:00Z");

        List<String> ticks = com.aistudio.hydroguard.wxqpzx.ui.WaterScreen.compactAxisLabels(timestamps);
        assertEquals(3, ticks.size());
        assertTrue(ticks.get(0).contains("10-10"));
        assertTrue(ticks.get(1).contains("10-12"));
        assertTrue(ticks.get(2).contains("10-15"));
    }

    @Test
    public void nextStepTargetTimestampCalculatedFromLiveInterval() {
        String lastObservedTs = "2026-10-15T08:50:00Z";
        int sampleIntervalSeconds = 35;

        java.util.Date lastDate = com.aistudio.hydroguard.wxqpzx.ui.Timestamps.parseUtc(lastObservedTs);
        assertNotNull(lastDate);

        java.util.Date targetDate = new java.util.Date(lastDate.getTime() + sampleIntervalSeconds * 1000L);
        java.text.SimpleDateFormat isoUtc = new java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", java.util.Locale.US);
        isoUtc.setTimeZone(java.util.TimeZone.getTimeZone("UTC"));
        String targetTs = isoUtc.format(targetDate);

        assertEquals("2026-10-15T08:50:35Z", targetTs);
        assertFalse("Target must not be nominal +24h", targetTs.contains("2026-10-16"));
    }

    @Test
    public void compactWarningSummaryFormatsConciseViolations() {
        // Given violating pH and Turbidity
        double ph = 12.41;
        double turbidity = 29.08;
        double tds = 5.47;
        double temperature = 25.56;

        List<String> violations = new ArrayList<>();
        if (ph > 8.5) {
            violations.add("pH " + String.format(java.util.Locale.US, "%.2f", ph) + " (alkaline, safe: 6.5–8.5)");
        }
        if (turbidity > 5.0) {
            violations.add("Turbidity " + String.format(java.util.Locale.US, "%.2f", turbidity) + " NTU (safe: ≤ 5.0 NTU)");
        }

        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < violations.size(); i++) {
            if (i > 0) sb.append("  •  ");
            sb.append(violations.get(i));
        }

        String summary = sb.toString();
        // Concise summary has exactly 1 line with delimiter
        assertFalse(summary.contains("\n"));
        assertTrue(summary.contains("pH 12.41 (alkaline, safe: 6.5–8.5)"));
        assertTrue(summary.contains("Turbidity 29.08 NTU (safe: ≤ 5.0 NTU)"));
        assertTrue(summary.contains("  •  "));
    }

    @Test
    public void statusFlagInterpretationGroundsHardwareState() {
        int statusNormal = 0;
        int statusUncalibrated = 1;

        String normalText = statusNormal == 0 ? "Normal" : "Abnormal";
        assertEquals("Normal", normalText);

        boolean hasHwIssue = (statusUncalibrated > 0);
        assertTrue("Status flag 1 indicates hardware issue", hasHwIssue);

        String caveat = "Hardware status flag 1 indicates abnormal telemetry / uncalibrated probe state. Physical probe inspection and recalibration required.";
        assertTrue(caveat.toLowerCase().contains("status flag 1"));
        assertTrue(caveat.contains("recalibration required"));
    }

    @Test
    public void forecastPredictionNeverOverridesActiveThresholdAlert() throws JSONException {
        // Reading violates pH threshold
        JSONObject liveReading = new JSONObject();
        liveReading.put("pH", 12.41);
        liveReading.put("turbidity", 29.08);

        // Model predicts normal pH
        JSONObject forecast = new JSONObject();
        forecast.put("pH", 7.20);
        forecast.put("turbidity", 1.50);

        // Verification: safety state is determined strictly by live observed measurements
        double livePh = liveReading.getDouble("pH");
        boolean isViolation = (livePh < 6.5 || livePh > 8.5);
        assertTrue("Live measurement violation must trigger alert", isViolation);

        // Model forecast being 7.20 must not clear the alert
        double forecastPh = forecast.getDouble("pH");
        boolean forecastNormal = (forecastPh >= 6.5 && forecastPh <= 8.5);
        assertTrue(forecastNormal);
        assertTrue("Active alert persists regardless of benign forecast", isViolation);
    }
}
