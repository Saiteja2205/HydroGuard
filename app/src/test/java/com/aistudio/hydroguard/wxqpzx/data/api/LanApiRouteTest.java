package com.aistudio.hydroguard.wxqpzx.data.api;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.assertEquals;

import java.net.SocketTimeoutException;
import java.net.UnknownHostException;

import org.junit.Test;

public class LanApiRouteTest {
    private static final String LAN_URL = "http://10.246.50.152:8000/";
    private static final String PUBLIC_URL = "https://hydroguard.example.com/";

    @Test public void lanHostsAreRoutedThroughWifi() {
        assertTrue(LanApiRoute.isLanApiHost("http://10.246.50.152:8000/"));
        assertTrue(LanApiRoute.isLanApiHost("http://192.168.1.5:8000/"));
        assertTrue(LanApiRoute.isLanApiHost("http://172.16.0.9:8000/"));
        assertTrue(LanApiRoute.isLanApiHost("http://172.31.255.255:8000/"));
    }

    @Test public void nonLanHostsKeepDefaultRouting() {
        assertFalse(LanApiRoute.isLanApiHost("http://10.0.2.2:8000/"));
        assertFalse(LanApiRoute.isLanApiHost("http://127.0.0.1:8000/"));
        assertFalse(LanApiRoute.isLanApiHost("http://localhost:8000/"));
        assertFalse(LanApiRoute.isLanApiHost("http://172.32.0.1:8000/"));
        assertFalse(LanApiRoute.isLanApiHost("http://172.15.0.1:8000/"));
        assertFalse(LanApiRoute.isLanApiHost("https://hydroguard.example.com/"));
        assertFalse(LanApiRoute.isLanApiHost("http://8.8.8.8/"));
        assertFalse(LanApiRoute.isLanApiHost("http://10.0.0/"));
        assertFalse(LanApiRoute.isLanApiHost("http://256.1.1.1/"));
        assertFalse(LanApiRoute.isLanApiHost("not a url"));
        assertFalse(LanApiRoute.isLanApiHost(null));
    }

    @Test public void missingWifiRouteExplainsItself() {
        LanApiRoute.LanRouteUnavailableException error =
                new LanApiRoute.LanRouteUnavailableException("The phone is not connected to Wi-Fi.");
        String message = ApiRepository.failureMessage(error, LAN_URL, false);
        assertTrue(message, message.contains("not connected to Wi-Fi"));
    }

    @Test public void lanTimeoutWithWifiPointsAtBackendOrFirewall() {
        String message = ApiRepository.failureMessage(
                new SocketTimeoutException("timeout"), LAN_URL, true);
        assertTrue(message, message.contains("Windows Firewall"));
    }

    @Test public void lanTimeoutWithoutWifiExplainsRouting() {
        String message = ApiRepository.failureMessage(
                new SocketTimeoutException("timeout"), LAN_URL, false);
        assertTrue(message, message.contains("timed out"));
    }

    @Test public void refusedConnectionWithoutWifiMentionsMobileDataLimits() {
        String message = ApiRepository.failureMessage(
                new java.net.ConnectException("refused"), LAN_URL, false);
        assertTrue(message, message.contains("mobile data"));
    }

    @Test public void publicHostKeepsGenericMessages() {
        String timeout = ApiRepository.failureMessage(
                new SocketTimeoutException("timeout"), PUBLIC_URL, true);
        assertTrue(timeout, timeout.contains("timed out"));
        String unknownHost = ApiRepository.failureMessage(
                new UnknownHostException("host"), PUBLIC_URL, false);
        assertTrue(unknownHost, unknownHost.contains("could not be resolved"));
    }

    // ===== Network security configuration =====
    //
    // A networkSecurityConfig in the manifest overrides the
    // usesCleartextTraffic attribute entirely, so the manifest flag is dead
    // text once a config is declared. These tests pin the actual policy files
    // so a release build can never silently regain cleartext HTTP (which
    // would send bearer tokens over plain text).

    /** Strips XML comments so assertions inspect the effective policy, not prose. */
    private static String stripXmlComments(String xml) {
        return xml.replaceAll("(?s)<!--.*?-->", "");
    }

    private static String readResourceFile(String relativePath) throws Exception {
        java.io.File cwd = new java.io.File(System.getProperty("user.dir"));
        java.io.File[] candidates = {
            new java.io.File(cwd, relativePath),
            new java.io.File(cwd, "app/" + relativePath),
        };
        for (java.io.File candidate : candidates) {
            if (candidate.isFile()) {
                return stripXmlComments(new String(
                        java.nio.file.Files.readAllBytes(candidate.toPath()),
                        java.nio.charset.StandardCharsets.UTF_8));
            }
        }
        throw new AssertionError("Could not locate " + relativePath
                + " from working directory " + cwd.getAbsolutePath());
    }

    @Test public void releaseCleartextIsDenied() throws Exception {
        String releaseCfg = readResourceFile("src/main/res/xml/network_security_config.xml");
        assertTrue("release config must deny cleartext",
                releaseCfg.contains("cleartextTrafficPermitted=\"false\""));
        assertFalse("release config must not permit cleartext",
                releaseCfg.contains("cleartextTrafficPermitted=\"true\""));
        String manifest = readResourceFile("src/main/AndroidManifest.xml");
        assertFalse("release manifest must not grant a cleartext exception",
                manifest.contains("usesCleartextTraffic=\"true\""));
    }

    @Test public void debugCleartextCarveOutKeepsUserCaTrust() throws Exception {
        String debugCfg = readResourceFile("src/debug/res/xml/network_security_config.xml");
        assertTrue("debug config must keep the cleartext carve-out for the local dev server",
                debugCfg.contains("cleartextTrafficPermitted=\"true\""));
        assertTrue("debug config must keep trusting user-installed CAs",
                debugCfg.contains("<certificates src=\"user\" />"));
        assertTrue("debug config must keep the system CA anchor",
                debugCfg.contains("<certificates src=\"system\" />"));
    }
}
