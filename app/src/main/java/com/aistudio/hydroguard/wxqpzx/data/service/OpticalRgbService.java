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
     * Maximum supported channel value for TCS34725 raw 16-bit register counts.
     */
    public static final int MAX_CHANNEL_VALUE = 65535;

    /**
     * Converts optical channel intensities (percentages 0-100%, 8-bit RGB 0-255,
     * or raw sensor counts 0-65535) to a valid 8-bit sRGB color integer.
     * Preserves hue and relative balance without clipping or saturation blowout.
     */
    public static int toDisplayColor(int rIn, int gIn, int bIn) {
        int r = Math.max(0, rIn);
        int g = Math.max(0, gIn);
        int b = Math.max(0, bIn);

        int max = Math.max(r, Math.max(g, b));
        int rOut, gOut, bOut;

        if (max > 255) {
            // Raw 16-bit sensor counts (e.g. 522, 640, 605)
            rOut = Math.min(255, Math.round((r / (float) max) * 255f));
            gOut = Math.min(255, Math.round((g / (float) max) * 255f));
            bOut = Math.min(255, Math.round((b / (float) max) * 255f));
        } else if (max > 100) {
            // Standard 8-bit RGB color (e.g. 120, 145, 110)
            rOut = Math.min(255, r);
            gOut = Math.min(255, g);
            bOut = Math.min(255, b);
        } else {
            // Relative percentage intensities [0, 100] (e.g. 40, 29, 30 from ThingSpeak)
            rOut = Math.min(255, Math.round(r * 2.55f));
            gOut = Math.min(255, Math.round(g * 2.55f));
            bOut = Math.min(255, Math.round(b * 2.55f));
        }
        return 0xFF000000 | (rOut << 16) | (gOut << 8) | bOut;
    }

    /**
     * Checks if a channel value falls within the valid physical sensor range [0, 65535].
     */
    public static boolean isValidChannel(int value) {
        return value >= 0 && value <= MAX_CHANNEL_VALUE;
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
     * and within the valid sensor range [0, 65535].
     */
    public static boolean hasValidRgb(JSONObject reading) {
        JSONObject obj = getRgbObject(reading);
        if (obj == null) return false;

        // Check standard "red", "green", "blue"
        if (hasChannel(obj, "red") && hasChannel(obj, "green") && hasChannel(obj, "blue")) {
            return true;
        }
        // Fallback for raw "rgb_red", "rgb_green", "rgb_blue"
        return hasChannel(obj, "rgb_red") && hasChannel(obj, "rgb_green") && hasChannel(obj, "rgb_blue");
    }

    private static boolean hasChannel(JSONObject obj, String key) {
        if (!obj.has(key) || obj.isNull(key)) return false;
        int val = obj.optInt(key, -1);
        return isValidChannel(val);
    }

    /**
     * Extracts [red, green, blue] channel values from reading.
     * Returns null if any channel is missing or out of valid range.
     */
    public static int[] extractRgb(JSONObject reading) {
        if (!hasValidRgb(reading)) return null;
        JSONObject obj = getRgbObject(reading);
        if (hasChannel(obj, "red") && hasChannel(obj, "green") && hasChannel(obj, "blue")) {
            return new int[] {
                    obj.optInt("red", 0),
                    obj.optInt("green", 0),
                    obj.optInt("blue", 0)
            };
        }
        return new int[] {
                obj.optInt("rgb_red", 0),
                obj.optInt("rgb_green", 0),
                obj.optInt("rgb_blue", 0)
        };
    }

    /**
     * Formats channel value as a clean numerical string.
     */
    public static String formatChannelValue(int value) {
        if (!isValidChannel(value)) return "--";
        return String.valueOf(value);
    }

    /**
     * Formats channel percentage (legacy support).
     */
    public static String formatPercent(int percent) {
        if (!isValidChannel(percent)) return "--%";
        return percent + "%";
    }

    /**
     * Formats a concise summary string of RGB measurements.
     */
    public static String formatSummary(int r, int g, int b) {
        return "R: " + formatChannelValue(r) + "  G: " + formatChannelValue(g) + "  B: " + formatChannelValue(b);
    }
}
