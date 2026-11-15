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
    public void toDisplayColorHandlesStandard8BitRgb() {
        // Red: 120, Green: 145, Blue: 110
        int color = OpticalRgbService.toDisplayColor(120, 145, 110);
        int expected = 0xFF000000 | (120 << 16) | (145 << 8) | 110;
        assertEquals(expected, color);
    }

    @Test
    public void toDisplayColorHandlesRaw16BitCounts() {
        int color = OpticalRgbService.toDisplayColor(522, 640, 605);
        int expectedR = Math.round((522 / 640f) * 255f);
        int expectedG = 255;
        int expectedB = Math.round((605 / 640f) * 255f);
        int expected = 0xFF000000 | (expectedR << 16) | (expectedG << 8) | expectedB;
        assertEquals(expected, color);
    }

    @Test
    public void toDisplayColorClampsNegativeChannels() {
        int color = OpticalRgbService.toDisplayColor(-10, 100, 50);
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
    public void hasValidRgbDetectsValid8BitStructure() throws JSONException {
        // Red: 120, Green: 145, Blue: 110 from sensor or user model
        JSONObject reading = new JSONObject("{\"rgb\": {\"red\": 120, \"green\": 145, \"blue\": 110}}");
        assertTrue(OpticalRgbService.hasValidRgb(reading));

        int[] rgb = OpticalRgbService.extractRgb(reading);
        assertNotNull(rgb);
        assertEquals(120, rgb[0]);
        assertEquals(145, rgb[1]);
        assertEquals(110, rgb[2]);
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

        // Out of 16-bit range (> 65535)
        JSONObject overMax = new JSONObject("{\"rgb\": {\"red\": 70000, \"green\": 30, \"blue\": 30}}");
        assertFalse(OpticalRgbService.hasValidRgb(overMax));
    }

    @Test
    public void formatChannelValueHandlesValidAndInvalid() {
        assertEquals("120", OpticalRgbService.formatChannelValue(120));
        assertEquals("0", OpticalRgbService.formatChannelValue(0));
        assertEquals("--", OpticalRgbService.formatChannelValue(-1));
        assertEquals("--", OpticalRgbService.formatChannelValue(70000));
    }

    @Test
    public void formatSummaryCreatesReadableString() {
        String summary = OpticalRgbService.formatSummary(120, 145, 110);
        assertEquals("R: 120  G: 145  B: 110", summary);
    }
}
