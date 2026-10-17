package com.aistudio.hydroguard.wxqpzx.data.service;

import org.json.JSONObject;

/**
 * Service for optical RGB sensor telemetry (TCS34725 relative channel intensities).
 * Provides mathematically correct display color mapping and validation.
 *
 * NOTE: Optical RGB intensities represent ambient/reflected light across optical channels.
 * They are NOT validated water-quality measurements (e.g. turbidity or contamination).
 */
public final class OpticalRgbService {

    private OpticalRgbService() { }

    /**
     * Converts optical channel intensities (0–100%) to an 8-bit sRGB color integer.
     * Uses linear scaling: C_255 = round(clamp(0, 100, P) * 2.55).
     * Does not blow out saturation or distort hue via artificial peak-normalization.
     */
    public static int toDisplayColor(int rPercent, int gPercent, int bPercent) {
        int r = clamp255(rPercent);
        int g = clamp255(gPercent);
        int b = clamp255(bPercent);
        return 0xFF000000 | (r << 16) | (g << 8) | b;
    }

    private static int clamp255(int percent) {
        int clamped = Math.max(0, Math.min(100, percent));
        return Math.round(clamped * 2.55f);
    }

    /**
     * Checks if a channel intensity value falls within the valid sensor range [0, 100].
     */
    public static boolean isValidChannel(int percent) {
        return percent >= 0 && percent <= 100;
    }

    /**
     * Resolves the RGB object from a reading JSON (nested under "rgb" or at root).
     */
    public static JSONObject getRgbObject(JSONObject reading) {
        if (reading == null) return null;
        if (reading.has("rgb") && !reading.isNull("rgb")) {
            return reading.optJSONObject("rgb");
        }
        return reading;
    }

    /**
     * Returns true if all three RGB channels (red, green, blue) are present, non-null,
     * and within the valid [0, 100] percentage range.
     */
    public static boolean hasValidRgb(JSONObject reading) {
        JSONObject obj = getRgbObject(reading);
        if (obj == null) return false;
        String[] keys = {"red", "green", "blue"};
        for (String k : keys) {
            if (!obj.has(k) || obj.isNull(k)) return false;
            int val = obj.optInt(k, -1);
            if (!isValidChannel(val)) return false;
        }
        return true;
    }

    /**
     * Extracts [red, green, blue] channel percentages from reading.
     * Returns null if any channel is missing or out of valid range.
     */
    public static int[] extractRgb(JSONObject reading) {
        if (!hasValidRgb(reading)) return null;
        JSONObject obj = getRgbObject(reading);
        return new int[] {
                obj.optInt("red", 0),
                obj.optInt("green", 0),
                obj.optInt("blue", 0)
        };
    }

    /**
     * Formats channel percentage avoiding text-wrap on narrow screens.
     */
    public static String formatPercent(int percent) {
        if (!isValidChannel(percent)) return "--%";
        return percent + "%";
    }

    /**
     * Formats a concise summary string.
     */
    public static String formatSummary(int r, int g, int b) {
        return "R: " + formatPercent(r) + "  G: " + formatPercent(g) + "  B: " + formatPercent(b);
    }
}
