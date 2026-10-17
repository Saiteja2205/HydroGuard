package com.aistudio.hydroguard.wxqpzx;

import com.aistudio.hydroguard.wxqpzx.data.service.OpticalRgbService;

import org.json.JSONException;
import org.json.JSONObject;
import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

public class OpticalRgbServiceTest {

    @Test
    public void toDisplayColorConvertsWithoutSaturationBlowout() {
        // Zero light (0%, 0%, 0%) -> opaque black (0xFF000000)
        assertEquals(0xFF000000, OpticalRgbService.toDisplayColor(0, 0, 0));

        // Full light (100%, 100%, 100%) -> opaque white (0xFFFFFFFF)
        assertEquals(0xFFFFFFFF, OpticalRgbService.toDisplayColor(100, 100, 100));

        // Real observed telemetry: R=40%, G=29%, B=30%
        // r = round(40 * 2.55) = 102 (0x66)
        // g = round(29 * 2.55) = 74  (0x4A)
        // b = round(30 * 2.55) = 77  (0x4D)
        // Expected: 0xFF664A4D (dark muted optical tone, NOT 0xFFFFB9BF pastel pink)
        int color = OpticalRgbService.toDisplayColor(40, 29, 30);
        assertEquals(0xFF664A4D, color);
    }

    @Test
    public void toDisplayColorClampsOutOfRangeChannels() {
        // -10 clamps to 0, 150 clamps to 100
        int color = OpticalRgbService.toDisplayColor(-10, 150, 50);
        int expected = 0xFF000000 | (0 << 16) | (255 << 8) | 128;
        assertEquals(expected, color);
    }

    @Test
    public void hasValidRgbDetectsValidNestedStructure() throws JSONException {
        JSONObject reading = new JSONObject("{\"rgb\": {\"red\": 42, \"green\": 30, \"blue\": 31}}");
        assertTrue(OpticalRgbService.hasValidRgb(reading));

        int[] rgb = OpticalRgbService.extractRgb(reading);
        assertNotNull(rgb);
        assertEquals(3, rgb.length);
        assertEquals(42, rgb[0]);
        assertEquals(30, rgb[1]);
        assertEquals(31, rgb[2]);
    }

    @Test
    public void hasValidRgbDetectsValidRootStructure() throws JSONException {
        JSONObject reading = new JSONObject("{\"red\": 50, \"green\": 60, \"blue\": 70}");
        assertTrue(OpticalRgbService.hasValidRgb(reading));

        int[] rgb = OpticalRgbService.extractRgb(reading);
        assertNotNull(rgb);
        assertEquals(50, rgb[0]);
        assertEquals(60, rgb[1]);
        assertEquals(70, rgb[2]);
    }

    @Test
    public void hasValidRgbRejectsMissingOrNullChannels() throws JSONException {
        // Missing blue
        JSONObject missingBlue = new JSONObject("{\"rgb\": {\"red\": 40, \"green\": 30}}");
        assertFalse(OpticalRgbService.hasValidRgb(missingBlue));
        assertNull(OpticalRgbService.extractRgb(missingBlue));

        // Null green
        JSONObject nullGreen = new JSONObject("{\"rgb\": {\"red\": 40, \"green\": null, \"blue\": 30}}");
        assertFalse(OpticalRgbService.hasValidRgb(nullGreen));
        assertNull(OpticalRgbService.extractRgb(nullGreen));

        // Null reading
        assertFalse(OpticalRgbService.hasValidRgb(null));
        assertNull(OpticalRgbService.extractRgb(null));
    }

    @Test
    public void hasValidRgbRejectsNegativeOrOutOfRangeChannels() throws JSONException {
        JSONObject negative = new JSONObject("{\"rgb\": {\"red\": -5, \"green\": 30, \"blue\": 30}}");
        assertFalse(OpticalRgbService.hasValidRgb(negative));

        JSONObject overMax = new JSONObject("{\"rgb\": {\"red\": 120, \"green\": 30, \"blue\": 30}}");
        assertFalse(OpticalRgbService.hasValidRgb(overMax));
    }

    @Test
    public void formatPercentHandlesValidAndInvalid() {
        assertEquals("45%", OpticalRgbService.formatPercent(45));
        assertEquals("0%", OpticalRgbService.formatPercent(0));
        assertEquals("100%", OpticalRgbService.formatPercent(100));
        assertEquals("--%", OpticalRgbService.formatPercent(-1));
        assertEquals("--%", OpticalRgbService.formatPercent(105));
    }

    @Test
    public void formatSummaryCreatesReadableString() {
        String summary = OpticalRgbService.formatSummary(40, 29, 30);
        assertEquals("R: 40%  G: 29%  B: 30%", summary);
    }
}
