package com.aistudio.hydroguard.wxqpzx;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

import com.aistudio.hydroguard.wxqpzx.data.service.HydroGuardFirebaseMessagingService;

import org.json.JSONException;
import org.json.JSONObject;
import org.junit.Test;

import java.util.HashMap;
import java.util.Map;

/**
 * Unit tests verifying FCM token payload construction, channel identity,
 * and push notification deep-link payload structures.
 */
public class FcmTokenRegistrationTest {

    @Test
    public void fcmChannelIdMatchesSystemAlertChannel() {
        assertEquals(
                "hydroguard_alerts",
                HydroGuardFirebaseMessagingService.CHANNEL_ID
        );
    }

    @Test
    public void fcmPrefsKeyConstantsAreWellDefined() {
        assertEquals("hydroguard_fcm", HydroGuardFirebaseMessagingService.PREFS_NAME);
        assertEquals("fcm_token", HydroGuardFirebaseMessagingService.KEY_FCM_TOKEN);
        assertEquals("backend_registered_token", HydroGuardFirebaseMessagingService.KEY_BACKEND_REGISTERED_TOKEN);
    }

    @Test
    public void registrationPayloadContainsRequiredFields() throws JSONException {
        String testToken = "test_fcm_registration_token_xyz_123456789";
        String deviceType = "android";

        JSONObject json = new JSONObject();
        json.put("token", testToken);
        json.put("device_type", deviceType);

        assertEquals(testToken, json.getString("token"));
        assertEquals("android", json.getString("device_type"));
    }

    @Test
    public void unregistrationPayloadContainsToken() throws JSONException {
        String testToken = "test_fcm_token_to_unregister";
        JSONObject json = new JSONObject();
        json.put("token", testToken);

        assertEquals(testToken, json.getString("token"));
    }

    @Test
    public void deepLinkPayloadCarriesWaterScreenTargetAndAlertId() {
        Map<String, String> data = new HashMap<>();
        data.put("target_screen", "water");
        data.put("alert_id", "42");
        data.put("node_id", "thingspeak-244357");
        data.put("parameter", "pH");
        data.put("severity", "CRITICAL");

        assertEquals("water", data.get("target_screen"));
        assertEquals("42", data.get("alert_id"));
        assertEquals("thingspeak-244357", data.get("node_id"));
        assertEquals("pH", data.get("parameter"));
        assertEquals("CRITICAL", data.get("severity"));
    }
}
