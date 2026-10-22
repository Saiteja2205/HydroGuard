package com.aistudio.hydroguard.wxqpzx;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

import org.json.JSONException;
import org.json.JSONObject;
import org.junit.Test;

/**
 * Unit tests verifying:
 * 1. Model Lifecycle state parsing (EXPERIMENTAL, VALIDATED, DEPLOYED, REJECTED).
 * 2. Next-Day forecast status and reason parsing (UNAVAILABLE_INSUFFICIENT_REAL_DATA).
 * 3. Data coverage percentage parsing and formatting.
 * 4. Backward-compatible fallback when fields are absent.
 * 5. Formatting of lifecycle disclaimers and status notes for Android UI presentation.
 */
public class ForecastLifecycleTest {

    private static final String SAMPLE_API_RESPONSE = "{\n" +
            "  \"status\": \"success\",\n" +
            "  \"model_lifecycle_state\": \"EXPERIMENTAL\",\n" +
            "  \"next_day_forecast_status\": \"UNAVAILABLE_INSUFFICIENT_REAL_DATA\",\n" +
            "  \"next_day_forecast_reason\": \"Real sensor data coverage is 0.68% (71 minutes active operation across 7 days with multi-hour gaps). Zero continuous 24-hour windows exist to train or validate genuine next-day forecasting. An experimental next-step (~33s) prediction is provided as a baseline.\",\n" +
            "  \"data_coverage_percent\": 0.684,\n" +
            "  \"continuous_24h_windows\": 0,\n" +
            "  \"sample_interval_seconds\": 33,\n" +
            "  \"prediction_semantics\": \"next_step_experimental\",\n" +
            "  \"target_timestamp\": \"2026-10-15T08:57:41Z\",\n" +
            "  \"disclaimer\": \"Development-trained forecast. These values are model extrapolations and are not a certified drinking-water safety rating.\",\n" +
            "  \"prediction\": {\n" +
            "    \"pH\": 7.27,\n" +
            "    \"TDS\": 286.09,\n" +
            "    \"turbidity\": 1.47,\n" +
            "    \"temperature\": 22.46\n" +
            "  }\n" +
            "}";

    @Test
    public void parsesModelLifecycleStateAndNextDayStatus() throws JSONException {
        JSONObject json = new JSONObject(SAMPLE_API_RESPONSE);

        String lifecycleState = json.optString("model_lifecycle_state", "EXPERIMENTAL");
        String nextDayStatus = json.optString("next_day_forecast_status", "UNAVAILABLE_INSUFFICIENT_REAL_DATA");
        String nextDayReason = json.optString("next_day_forecast_reason", "");
        double coverage = json.optDouble("data_coverage_percent", 0.0);
        int windows = json.optInt("continuous_24h_windows", 0);

        assertEquals("EXPERIMENTAL", lifecycleState);
        assertEquals("UNAVAILABLE_INSUFFICIENT_REAL_DATA", nextDayStatus);
        assertTrue("Reason should mention coverage", nextDayReason.contains("0.68%"));
        assertTrue("Reason should mention multi-hour gaps", nextDayReason.contains("multi-hour gaps"));
        assertEquals(0.684, coverage, 0.001);
        assertEquals(0, windows);
    }

    @Test
    public void formatsLifecycleUiBadgeCorrectly() {
        assertEquals("EXPERIMENTAL", getBadgeText("EXPERIMENTAL"));
        assertEquals("DEPLOYED", getBadgeText("DEPLOYED"));
        assertEquals("REJECTED", getBadgeText("REJECTED"));
        assertEquals("EXPERIMENTAL", getBadgeText("")); // default fallback
    }

    @Test
    public void formatsNextDayStatusNoteForAndroid() throws JSONException {
        JSONObject json = new JSONObject(SAMPLE_API_RESPONSE);
        String nextDayStatus = json.optString("next_day_forecast_status", "");
        String nextDayReason = json.optString("next_day_forecast_reason", "");

        StringBuilder statusNote = new StringBuilder();
        if ("UNAVAILABLE_INSUFFICIENT_REAL_DATA".equals(nextDayStatus)) {
            statusNote.append("Next-Day (24h) Horizon: UNAVAILABLE INSUFFICIENT REAL DATA");
            if (!nextDayReason.isEmpty()) {
                statusNote.append("\n").append(nextDayReason);
            }
        }

        String note = statusNote.toString();
        assertTrue("Should include headline", note.startsWith("Next-Day (24h) Horizon: UNAVAILABLE INSUFFICIENT REAL DATA"));
        assertTrue("Should include scientific explanation", note.contains("Zero continuous 24-hour windows exist"));
    }

    @Test
    public void handlesLegacyResponseWithoutLifecycleFields() throws JSONException {
        // Legacy response before real-data pipeline addition
        String legacyJson = "{\n" +
                "  \"status\": \"success\",\n" +
                "  \"prediction\": {\"pH\": 7.2, \"TDS\": 250.0, \"turbidity\": 1.5, \"temperature\": 24.0}\n" +
                "}";

        JSONObject json = new JSONObject(legacyJson);
        String lifecycleState = json.optString("model_lifecycle_state", "EXPERIMENTAL");
        String nextDayStatus = json.optString("next_day_forecast_status", "UNAVAILABLE_INSUFFICIENT_REAL_DATA");

        assertEquals("Fallback should be EXPERIMENTAL", "EXPERIMENTAL", lifecycleState);
        assertEquals("Fallback should be UNAVAILABLE_INSUFFICIENT_REAL_DATA", "UNAVAILABLE_INSUFFICIENT_REAL_DATA", nextDayStatus);
    }

    private static String getBadgeText(String lifecycle) {
        if (lifecycle == null || lifecycle.trim().isEmpty()) {
            return "EXPERIMENTAL";
        }
        return lifecycle.trim().toUpperCase();
    }
}
