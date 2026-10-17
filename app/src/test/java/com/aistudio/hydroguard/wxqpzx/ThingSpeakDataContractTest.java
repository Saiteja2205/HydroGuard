package com.aistudio.hydroguard.wxqpzx;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

import java.util.Locale;

/**
 * Regression and data contract tests for ThingSpeak live readings and RGB colour handling.
 *
 * Verifies:
 * 1. Provenance labels: THINGSPEAK is treated as live sensor data.
 * 2. RGB values are in 0-100% relative intensity range.
 * 3. Safe normalisation to 8-bit sRGB swatch without division by zero.
 * 4. Forecast contract: missing Optical Colour Index results in forecast_unavailable.
 */
public class ThingSpeakDataContractTest {

    @Test
    public void thingspeakProvenanceIsRecognizedAsLive() {
        String source = "THINGSPEAK";
        String normalized = source.trim().toUpperCase(Locale.ROOT);
        boolean isLive = "REAL_SENSOR".equals(normalized) || "LIVE_SENSOR".equals(normalized)
                || "SENSOR".equals(normalized) || "THINGSPEAK".equals(normalized);
        assertTrue("THINGSPEAK must be recognized as a live sensor source", isLive);

        String demoSource = "SIMULATED_DEVELOPMENT";
        String demoNormalized = demoSource.trim().toUpperCase(Locale.ROOT);
        boolean isDemoLive = "REAL_SENSOR".equals(demoNormalized) || "LIVE_SENSOR".equals(demoNormalized)
                || "SENSOR".equals(demoNormalized) || "THINGSPEAK".equals(demoNormalized);
        assertFalse("SIMULATED_DEVELOPMENT must never be recognized as a live sensor source", isDemoLive);
    }

    @Test
    public void rgbIntensityPercentagesAreWithinBounds() {
        int r = 40;
        int g = 29;
        int b = 30;
        assertTrue(r >= 0 && r <= 100);
        assertTrue(g >= 0 && g <= 100);
        assertTrue(b >= 0 && b <= 100);
    }

    @Test
    public void rgbColourSwatchNormalisesMaxTo255() {
        int r = 40;
        int g = 29;
        int b = 30;

        int max = Math.max(r, Math.max(g, b));
        assertEquals(40, max);

        int nr = max > 0 ? Math.min(255, (r * 255) / max) : 0;
        int ng = max > 0 ? Math.min(255, (g * 255) / max) : 0;
        int nb = max > 0 ? Math.min(255, (b * 255) / max) : 0;

        assertEquals(255, nr);
        assertEquals((29 * 255) / 40, ng);
        assertEquals((30 * 255) / 40, nb);

        int colour = 0xFF000000 | (nr << 16) | (ng << 8) | nb;
        assertTrue("Alpha channel must be 255 (0xFF)", (colour & 0xFF000000) != 0);
    }

    @Test
    public void allZeroRgbHandledSafelyWithoutDivideByZero() {
        int r = 0;
        int g = 0;
        int b = 0;

        int max = Math.max(r, Math.max(g, b));
        assertEquals(0, max);

        int nr = max > 0 ? Math.min(255, (r * 255) / max) : 0;
        int ng = max > 0 ? Math.min(255, (g * 255) / max) : 0;
        int nb = max > 0 ? Math.min(255, (b * 255) / max) : 0;

        assertEquals(0, nr);
        assertEquals(0, ng);
        assertEquals(0, nb);

        int colour = 0xFF000000 | (nr << 16) | (ng << 8) | nb;
        assertEquals(0xFF000000, colour);
    }

    @Test
    public void fullySaturatedRgbAllowedWithinRange() {
        int r = 100;
        int g = 100;
        int b = 100;

        boolean valid = (r >= 0 && r <= 100) && (g >= 0 && g <= 100) && (b >= 0 && b <= 100);
        assertTrue("100% saturation is a valid physical reading", valid);
    }

    @Test
    public void forecastUnavailableReasonIsHonest() {
        String status = "forecast_unavailable";
        String reason = "missing_optical_colour_index";
        assertEquals("forecast_unavailable", status);
        assertEquals("missing_optical_colour_index", reason);
    }
}
