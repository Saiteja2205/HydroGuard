package com.aistudio.hydroguard.wxqpzx.data.api;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotEquals;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class ApiErrorClassificationTest {
    private static final String BASE_URL = "http://10.239.220.152:8000/";
    private static final String BOOTSTRAP_ENDPOINT = "/api/v1/auth/bootstrap";

    @Test
    public void http401ReturnsAuthenticationKindWithServerDetail() {
        String jsonBody = "{\"detail\":\"Firebase bearer token is invalid or expired.\"}";
        ApiFailure failure = ApiRepository.classifyResponse(401, BOOTSTRAP_ENDPOINT, jsonBody);

        assertEquals(ApiFailure.Kind.AUTHENTICATION, failure.kind);
        assertEquals(Integer.valueOf(401), failure.statusCode);
        assertEquals(BOOTSTRAP_ENDPOINT, failure.endpoint);
        assertEquals("Firebase bearer token is invalid or expired.", failure.getMessage());
    }

    @Test
    public void http401WithEmptyBodyProvidesActionableAuthMessage() {
        ApiFailure failure = ApiRepository.classifyResponse(401, BOOTSTRAP_ENDPOINT, "");

        assertEquals(ApiFailure.Kind.AUTHENTICATION, failure.kind);
        assertEquals(Integer.valueOf(401), failure.statusCode);
        assertTrue(failure.getMessage().contains("HydroGuard did not accept this session"));
        assertNotEquals(ApiFailure.Kind.SERVER_UNREACHABLE, failure.kind);
    }

    @Test
    public void http403ReturnsAuthenticationKind() {
        String jsonBody = "{\"detail\":\"Use a verified college Google account to continue.\"}";
        ApiFailure failure = ApiRepository.classifyResponse(403, BOOTSTRAP_ENDPOINT, jsonBody);

        assertEquals(ApiFailure.Kind.AUTHENTICATION, failure.kind);
        assertEquals(Integer.valueOf(403), failure.statusCode);
        assertEquals("Use a verified college Google account to continue.", failure.getMessage());
    }

    @Test
    public void http500ReturnsApiErrorKind() {
        String jsonBody = "{\"detail\":\"Internal server error\"}";
        ApiFailure failure = ApiRepository.classifyResponse(500, BOOTSTRAP_ENDPOINT, jsonBody);

        assertEquals(ApiFailure.Kind.API_ERROR, failure.kind);
        assertEquals(Integer.valueOf(500), failure.statusCode);
        assertTrue(failure.getMessage().contains("Internal server error"));
    }

    @Test
    public void authFailuresAreNeverConfusedWithServerUnreachable() {
        ApiFailure authFailure = ApiRepository.classifyResponse(401, BOOTSTRAP_ENDPOINT,
                "{\"detail\":\"Token used too early\"}");

        assertEquals(ApiFailure.Kind.AUTHENTICATION, authFailure.kind);
        assertNotEquals(ApiFailure.Kind.SERVER_UNREACHABLE, authFailure.kind);

        // Verify that failureMessage for transport timeout is separate
        String timeoutMessage = ApiRepository.failureMessage(
                new java.net.SocketTimeoutException("Read timed out"), BASE_URL, true);
        assertTrue(timeoutMessage.contains("did not respond even though the phone is on Wi-Fi"));

        // Auth failure message must NOT contain timeout / firewall instructions
        assertTrue(!authFailure.getMessage().contains("Windows Firewall"));
        assertTrue(!authFailure.getMessage().contains("did not respond even though the phone is on Wi-Fi"));
    }
}
