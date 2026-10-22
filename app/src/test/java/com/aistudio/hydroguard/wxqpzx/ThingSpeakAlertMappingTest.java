package com.aistudio.hydroguard.wxqpzx;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotEquals;
import static org.junit.Assert.assertTrue;

import com.aistudio.hydroguard.wxqpzx.data.config.HostelConfig;
import com.aistudio.hydroguard.wxqpzx.ui.WaterScreen;

import org.junit.Test;

/**
 * Tests for the node mapping between ThingSpeak telemetry and Android Water screen alert retrieval.
 *
 * Verifies:
 * 1. Default initialization directs alert queries to the ThingSpeak hardware node (e.g. thingspeak-244357).
 * 2. Water screen does not query unrelated database node (e.g. node_overhead_a) when displaying ThingSpeak readings.
 * 3. Legitimate physical/database nodes (e.g. node_overhead_b) retain independent alert retrieval.
 * 4. Switching to/from ThingSpeak updates currentAlertNode() accordingly.
 */
public class ThingSpeakAlertMappingTest {

    @Test
    public void defaultSelectionResolvesToThingSpeakAlertNode() {
        WaterScreen screen = new WaterScreen(null, null, null, null, false, null);
        assertTrue("ThingSpeak must be selected by default", screen.isThingSpeakSelected());
        assertEquals("thingspeak-244357", screen.currentAlertNode());
        assertNotEquals("Should not query unrelated database node", "node_overhead_a", screen.currentAlertNode());
    }

    @Test
    public void primaryTankDefaultsToLiveThingSpeakNode() {
        String primaryId = HostelConfig.primaryTankNodeId(); // "node_overhead_a"
        WaterScreen screen = new WaterScreen(null, null, null, null, false, primaryId);
        assertTrue("Primary hostel tank selection must map to live ThingSpeak feed", screen.isThingSpeakSelected());
        assertEquals("thingspeak-244357", screen.currentAlertNode());
        assertNotEquals("Primary tank live mode must not query node_overhead_a for alerts", "node_overhead_a", screen.currentAlertNode());
    }

    @Test
    public void explicitThingSpeakNodeSelectionQueriesThingSpeakAlerts() {
        WaterScreen screen = new WaterScreen(null, null, null, null, false, "thingspeak-244357");
        assertTrue(screen.isThingSpeakSelected());
        assertEquals("thingspeak-244357", screen.currentAlertNode());
    }

    @Test
    public void distinctDatabaseNodeSelectionQueriesDatabaseAlerts() {
        WaterScreen screen = new WaterScreen(null, null, null, null, false, "node_overhead_b");
        assertFalse("Separate database node must not be flagged as ThingSpeak", screen.isThingSpeakSelected());
        assertEquals("node_overhead_b", screen.currentAlertNode());
        assertNotEquals("Must not query ThingSpeak for separate database node", "thingspeak-244357", screen.currentAlertNode());
    }

    @Test
    public void messTankNodeSelectionPreserved() {
        WaterScreen screen = new WaterScreen(null, null, null, null, false, "node_mess");
        assertFalse(screen.isThingSpeakSelected());
        assertEquals("node_mess", screen.currentAlertNode());
    }
}
