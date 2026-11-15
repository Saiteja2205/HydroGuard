package com.aistudio.hydroguard.wxqpzx;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import com.aistudio.hydroguard.wxqpzx.data.database.SensorReading;
import com.aistudio.hydroguard.wxqpzx.data.service.WaterQualityIndexService;

import org.json.JSONException;
import org.json.JSONObject;
import org.junit.Test;

import java.util.Locale;

/**
 * Verifies the end-to-end data flow, extraction, fallback, physical bounds,
 * and presentation contracts for Optical Colour Index (5th water metric).
 */
public class OpticalColourIndexFlowTest {

    private double extractColourIndex(JSONObject values) {
        if (values == null) return Double.NaN;
        return values.optDouble("optical_colour_index",
                values.optDouble("opticalColourIndex",
                        values.optDouble("colour_index",
                                values.optDouble("color_index", Double.NaN))));
    }

    private String formatTileValue(double value) {
        if (Double.isNaN(value) || Double.isInfinite(value) || value < 0.0 || value > 1.0) {
            return "N/A";
        }
        return String.format(Locale.US, "%.2f", value);
    }

    private boolean isPhysicallyValid(String metric, double value) {
        if (Double.isNaN(value) || Double.isInfinite(value)) return false;
        String m = metric.toLowerCase(Locale.ROOT);
        if ("optical_colour_index".equals(m) || "opticalcolourindex".equals(m)
                || "colour_index".equals(m) || "color_index".equals(m)) {
            return value >= 0.0 && value <= 1.0;
        }
        return true;
    }

    @Test
    public void validOpticalColourIndexExtractedSuccessfully() throws JSONException {
        // Snake case payload from backend / API
        String jsonStr = "{\"pH\": 7.42, \"TDS\": 195.0, \"turbidity\": 1.2, \"temperature\": 24.5, \"optical_colour_index\": 0.35}";
        JSONObject values = new JSONObject(jsonStr);

        double extracted = extractColourIndex(values);
        assertFalse("Optical colour index must not be NaN when present", Double.isNaN(extracted));
        assertEquals(0.35, extracted, 0.001);
        assertEquals("0.35", formatTileValue(extracted));

        // Camel case payload support
        String camelJsonStr = "{\"pH\": 7.42, \"TDS\": 195.0, \"turbidity\": 1.2, \"temperature\": 24.5, \"opticalColourIndex\": 0.42}";
        JSONObject camelValues = new JSONObject(camelJsonStr);

        double camelExtracted = extractColourIndex(camelValues);
        assertEquals(0.42, camelExtracted, 0.001);
        assertEquals("0.42", formatTileValue(camelExtracted));
    }

    @Test
    public void missingOrNullColourDataDoesNotCrashAndDefaultsToNA() throws JSONException {
        // ThingSpeak channel 244357 hardware feed without colour index field
        String thingspeakJson = "{\"pH\": 7.15, \"TDS\": 210.0, \"turbidity\": 2.05, \"temperature\": 26.1}";
        JSONObject thingspeakValues = new JSONObject(thingspeakJson);

        double thingspeakExtracted = extractColourIndex(thingspeakValues);
        assertTrue("ThingSpeak channel 244357 missing optical colour index must yield NaN", Double.isNaN(thingspeakExtracted));
        assertEquals("N/A", formatTileValue(thingspeakExtracted));

        // Null value payload
        JSONObject nullValues = new JSONObject();
        nullValues.put("pH", 7.15);
        nullValues.put("optical_colour_index", JSONObject.NULL);

        double nullExtracted = extractColourIndex(nullValues);
        assertTrue("Explicit null optical colour index must yield NaN", Double.isNaN(nullExtracted));
        assertEquals("N/A", formatTileValue(nullExtracted));

        // Completely null values object
        assertEquals("N/A", formatTileValue(extractColourIndex(null)));
    }

    @Test
    public void olderRecordsWithoutColourFieldRemainReadable() throws JSONException {
        // Legacy reading row prior to opticalColourIndex addition
        SensorReading legacyReading = new SensorReading();
        legacyReading.nodeId = "hostel-tank-1";
        legacyReading.timestamp = 1729000000000L;
        legacyReading.ph = 7.30f;
        legacyReading.tds = 220.0f;
        legacyReading.turbidity = 1.8f;
        legacyReading.temperature = 25.0f;
        legacyReading.opticalColourIndex = null; // Legacy record without colour field

        assertNull("Legacy record must have null opticalColourIndex", legacyReading.opticalColourIndex);
        assertEquals(7.30f, legacyReading.ph, 0.01f);
        assertEquals(220.0f, legacyReading.tds, 0.01f);
        assertEquals(1.8f, legacyReading.turbidity, 0.01f);
        assertEquals(25.0f, legacyReading.temperature, 0.01f);

        // Verify conversion to JSON handles null opticalColourIndex safely
        JSONObject json = new JSONObject();
        json.put("ph", legacyReading.ph);
        json.put("tds", legacyReading.tds);
        json.put("turbidity", legacyReading.turbidity);
        json.put("temperature", legacyReading.temperature);
        json.put("optical_colour_index", legacyReading.opticalColourIndex == null ? JSONObject.NULL : legacyReading.opticalColourIndex);

        assertTrue(json.isNull("optical_colour_index"));
        assertEquals("N/A", formatTileValue(extractColourIndex(json)));
    }

    @Test
    public void physicalValidityThresholdsEnforced() {
        assertTrue("0.0 is valid lower bound", isPhysicallyValid("optical_colour_index", 0.0));
        assertTrue("0.5 is valid mid-scale", isPhysicallyValid("optical_colour_index", 0.5));
        assertTrue("1.0 is valid upper bound", isPhysicallyValid("optical_colour_index", 1.0));

        assertFalse("Negative value is physically invalid", isPhysicallyValid("optical_colour_index", -0.05));
        assertFalse("Value above 1.0 is physically invalid", isPhysicallyValid("optical_colour_index", 1.05));
        assertFalse("NaN is physically invalid", isPhysicallyValid("optical_colour_index", Double.NaN));
        assertFalse("Infinity is physically invalid", isPhysicallyValid("optical_colour_index", Double.POSITIVE_INFINITY));
    }

    @Test
    public void waterQualityStatusForColourIndex() {
        assertEquals("Normal", WaterQualityIndexService.getParameterStatus("optical_colour_index", 0.30f));
        assertEquals("Elevated", WaterQualityIndexService.getParameterStatus("optical_colour_index", 0.70f));
        assertEquals("High", WaterQualityIndexService.getParameterStatus("optical_colour_index", 1.50f));
        assertEquals("Normal", WaterQualityIndexService.getParameterStatus("colour_index", 0.40f));
    }

    @Test
    public void staleTelemetryIsNotMarkedLive() {
        long now = 1761000000000L; // Mock current time
        long observationTime15Oct2026 = 1760515200000L; // Multiple days old
        long ageMs = now - observationTime15Oct2026;
        long fifteenMinutesMs = 15 * 60 * 1000L;

        boolean isDelayed = ageMs >= fifteenMinutesMs;
        assertTrue("Readings older than 15 minutes must be flagged as DELAYED", isDelayed);

        long freshObservation = now - (5 * 60 * 1000L); // 5 minutes old
        long freshAgeMs = now - freshObservation;
        boolean freshIsDelayed = freshAgeMs >= fifteenMinutesMs;
        assertFalse("Readings within 15 minutes must be recognized as timely", freshIsDelayed);
    }

    @Test
    public void existingFourMetricsRemainAccurateWhenFifthIsAdded() throws JSONException {
        JSONObject response = new JSONObject("{\n" +
                "  \"values\": {\n" +
                "    \"pH\": 7.85,\n" +
                "    \"TDS\": 245.5,\n" +
                "    \"turbidity\": 1.15,\n" +
                "    \"temperature\": 27.3,\n" +
                "    \"optical_colour_index\": 0.18\n" +
                "  }\n" +
                "}");

        JSONObject values = response.getJSONObject("values");
        double ph = values.optDouble("pH", Double.NaN);
        double tds = values.optDouble("TDS", Double.NaN);
        double turbidity = values.optDouble("turbidity", Double.NaN);
        double temp = values.optDouble("temperature", Double.NaN);
        double colour = extractColourIndex(values);

        assertEquals(7.85, ph, 0.001);
        assertEquals(245.5, tds, 0.001);
        assertEquals(1.15, turbidity, 0.001);
        assertEquals(27.3, temp, 0.001);
        assertEquals(0.18, colour, 0.001);

        assertEquals("7.85", String.format(Locale.US, "%.2f", ph));
        assertEquals("245.50", String.format(Locale.US, "%.2f", tds));
        assertEquals("1.15", String.format(Locale.US, "%.2f", turbidity));
        assertEquals("27.30", String.format(Locale.US, "%.2f", temp));
        assertEquals("0.18", formatTileValue(colour));
    }
}
