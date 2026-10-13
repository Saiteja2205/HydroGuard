package com.aistudio.hydroguard.wxqpzx.data.config;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Canonical configuration for the deployed hostel: one building, one block, one water tank.
 *
 * <p>This mirrors {@code hydroguard-backend/app/core/hostel_config.py} so the student UI, the
 * admin UI, the Water screen and the report forms all describe the same deployment. The
 * constants below are the offline fallback used on a cold start or when the server is
 * unreachable; {@link #applyServerJson(String)} refreshes them from
 * {@code GET /api/v1/hostel/configuration}, which is authoritative.
 *
 * <p>The old build shipped three example tanks ("Overhead Tank A", "Overhead Tank B",
 * "Mess Ground Water") for blocks that do not exist here. They are deliberately absent so a
 * configuration change here — not another hardcoded list — is all that is needed to add
 * tanks later.
 */
public final class HostelConfig {

    /** One configured water tank and the sensor node that reports it. */
    public static final class Tank {
        public final String id;
        public final String nodeId;
        public final String name;
        public final String location;

        Tank(String id, String nodeId, String name, String location) {
            this.id = id;
            this.nodeId = nodeId;
            this.name = name;
            this.location = location;
        }
    }

    private static final String DEFAULT_BUILDING_ID = "main-building";
    private static final String DEFAULT_BUILDING_NAME = "Main Hostel Building";
    private static final String DEFAULT_BLOCK_ID = "main-block";
    private static final String DEFAULT_BLOCK_NAME = "Hostel Block";

    /** The single deployed tank. Its node id must match the backend configuration. */
    private static final Tank DEFAULT_TANK = new Tank(
            "main-tank", "node_overhead_a", "Hostel Water Tank", DEFAULT_BLOCK_NAME);

    private static final Object LOCK = new Object();
    private static final List<Tank> DEFAULT_TANKS =
            Collections.unmodifiableList(Collections.singletonList(DEFAULT_TANK));

    private static String buildingId = DEFAULT_BUILDING_ID;
    private static String buildingName = DEFAULT_BUILDING_NAME;
    private static String blockId = DEFAULT_BLOCK_ID;
    private static String blockName = DEFAULT_BLOCK_NAME;
    private static List<Tank> tanks = DEFAULT_TANKS;

    private HostelConfig() {
    }

    /** Configured tanks, in display order. Never empty. */
    public static List<Tank> tanks() {
        synchronized (LOCK) {
            return tanks;
        }
    }

    /** Sensor node ids for the configured tanks, used to filter server responses. */
    public static List<String> tankNodeIds() {
        List<String> ids = new ArrayList<>();
        for (Tank tank : tanks()) {
            ids.add(tank.nodeId);
        }
        return ids;
    }

    /** The tank the app loads first. */
    public static String primaryTankNodeId() {
        return tanks().get(0).nodeId;
    }

    /** Display label for the primary tank. */
    public static String tankName() {
        return tanks().get(0).name;
    }

    public static String blockName() {
        synchronized (LOCK) {
            return blockName;
        }
    }

    public static String buildingName() {
        synchronized (LOCK) {
            return buildingName;
        }
    }

    /** Ids used by tests and assertions; never rendered directly to users. */
    public static String blockId() {
        synchronized (LOCK) {
            return blockId;
        }
    }

    public static String buildingId() {
        synchronized (LOCK) {
            return buildingId;
        }
    }

    /**
     * Applies the authoritative server configuration.
     *
     * <p>A missing, empty or malformed response keeps the current configuration rather than
     * blanking the screen, and an empty tank list is rejected for the same reason.
     */
    public static void applyServerJson(String json) {
        if (json == null || json.trim().isEmpty()) {
            return;
        }
        try {
            JSONObject root = new JSONObject(json);

            List<Tank> parsed = new ArrayList<>();
            JSONArray rows = root.optJSONArray("tanks");
            if (rows != null) {
                for (int i = 0; i < rows.length(); i++) {
                    JSONObject row = rows.optJSONObject(i);
                    if (row == null) {
                        continue;
                    }
                    String nodeId = text(row, "node_id");
                    String name = text(row, "name");
                    if (nodeId.isEmpty() || name.isEmpty()) {
                        continue;
                    }
                    String id = text(row, "id");
                    String location = text(row, "location");
                    parsed.add(new Tank(id.isEmpty() ? nodeId : id, nodeId, name, location));
                }
            }

            String newBuildingId = firstId(root.optJSONArray("buildings"));
            String newBuildingName = firstName(root.optJSONArray("buildings"));
            String newBlockId = firstId(root.optJSONArray("blocks"));
            String newBlockName = firstName(root.optJSONArray("blocks"));

            synchronized (LOCK) {
                if (!parsed.isEmpty()) {
                    tanks = Collections.unmodifiableList(parsed);
                }
                if (!newBuildingName.isEmpty()) {
                    buildingName = newBuildingName;
                }
                if (!newBuildingId.isEmpty()) {
                    buildingId = newBuildingId;
                }
                if (!newBlockName.isEmpty()) {
                    blockName = newBlockName;
                }
                if (!newBlockId.isEmpty()) {
                    blockId = newBlockId;
                }
            }
        } catch (JSONException ignored) {
            // Never let a bad payload wipe the deployment shown on screen.
        }
    }

    /** Resets to the built-in deployment. Only for tests. */
    public static void resetToDefaults() {
        synchronized (LOCK) {
            buildingId = DEFAULT_BUILDING_ID;
            buildingName = DEFAULT_BUILDING_NAME;
            blockId = DEFAULT_BLOCK_ID;
            blockName = DEFAULT_BLOCK_NAME;
            tanks = DEFAULT_TANKS;
        }
    }

    /**
     * Reads a string field, treating the literal {@code "null"} that {@code optString} yields for
     * a JSON null as absent so a label never renders as "null".
     */
    private static String text(JSONObject row, String key) {
        String value = row.optString(key, "").trim();
        return "null".equalsIgnoreCase(value) ? "" : value;
    }

    private static String firstName(JSONArray rows) {
        if (rows == null || rows.length() == 0) {
            return "";
        }
        JSONObject first = rows.optJSONObject(0);
        return first == null ? "" : text(first, "name");
    }

    private static String firstId(JSONArray rows) {
        if (rows == null || rows.length() == 0) {
            return "";
        }
        JSONObject first = rows.optJSONObject(0);
        return first == null ? "" : text(first, "id");
    }
}
