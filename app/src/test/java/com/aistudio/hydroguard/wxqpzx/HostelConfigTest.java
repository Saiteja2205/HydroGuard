package com.aistudio.hydroguard.wxqpzx;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import com.aistudio.hydroguard.wxqpzx.data.config.HostelConfig;

import org.junit.Before;
import org.junit.Test;

import java.util.Collections;
import java.util.List;

/**
 * The app must describe the real deployment: one building, one block, one water tank.
 *
 * <p>These assertions mirror {@code hydroguard-backend/tests/test_hostel_configuration.py} so a
 * change to either side that reintroduces the retired example tanks fails the build.
 */
public class HostelConfigTest {

    @Before
    public void resetConfiguration() {
        HostelConfig.resetToDefaults();
    }

    @Test
    public void deploymentIsOneBuildingOneBlockOneTank() {
        assertEquals("Main Hostel Building", HostelConfig.buildingName());
        assertEquals("Hostel Block", HostelConfig.blockName());
        assertEquals(1, HostelConfig.tanks().size());
        assertEquals(1, HostelConfig.tankNodeIds().size());
    }

    @Test
    public void theSingleTankUsesTheApprovedDisplayName() {
        HostelConfig.Tank tank = HostelConfig.tanks().get(0);
        assertEquals("Hostel Water Tank", tank.name);
        assertEquals("Hostel Block", tank.location);
        // The node id must match the backend so readings and forecasts stay attached.
        assertEquals("node_overhead_a", HostelConfig.primaryTankNodeId());
        assertEquals("Hostel Water Tank", HostelConfig.tankName());
    }

    @Test
    public void retiredExampleTanksAreNotConfigured() {
        List<String> nodeIds = HostelConfig.tankNodeIds();
        assertEquals(Collections.singletonList("node_overhead_a"), nodeIds);
        assertTrue(!nodeIds.contains("node_overhead_b"));
        assertTrue(!nodeIds.contains("node_mess_ground"));
        for (HostelConfig.Tank tank : HostelConfig.tanks()) {
            assertTrue(!"Overhead Tank B".equals(tank.name));
            assertTrue(!"Mess Ground Water".equals(tank.name));
        }
    }

    @Test
    public void aMissingConfigurationNeverBlanksTheScreen() {
        List<String> before = HostelConfig.tankNodeIds();
        HostelConfig.applyServerJson(null);
        HostelConfig.applyServerJson("");
        HostelConfig.applyServerJson("   ");
        assertEquals(before, HostelConfig.tankNodeIds());
        assertEquals(1, HostelConfig.tanks().size());
        assertEquals("Hostel Water Tank", HostelConfig.tankName());
    }
}
