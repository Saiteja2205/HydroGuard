package com.aistudio.hydroguard.wxqpzx.data.config;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * The issue lifecycle exactly as the HydroGuard backend defines it.
 *
 * <p>The backend owns the truth: {@code GET /api/v1/hostel/issues/workflow}
 * returns the transition graph, the labels and which fields each target
 * requires. This class carries an identical built-in default so the
 * Hostel Operations screen can render buttons before (or even if) that request
 * arrives, and {@link #applyServerJson(String)} replaces the defaults with the
 * server's answer. Buttons are therefore only ever offered for transitions the
 * backend will accept, so an administrator can never produce a 409 by tapping
 * something the UI presented to them.</p>
 *
 * <p>Keep in sync with {@code ISSUE_TRANSITIONS} / {@code ISSUE_STATUS_LABELS}
 * in {@code hydroguard-backend/app/api/hostel.py}. The backend test
 * {@code test_issue_workflow.py} pins that table; {@code IssueWorkflowTest}
 * pins this one.</p>
 */
public final class IssueWorkflow {

    /** The status the backend writes when a student files a report. */
    public static final String OPEN = "SUBMITTED";

    private static final Map<String, String> LABELS = new LinkedHashMap<>();
    private static final Map<String, List<String>> TRANSITIONS = new LinkedHashMap<>();
    private static final Map<String, String> ACTIONS = new LinkedHashMap<>();

    static {
        LABELS.put("SUBMITTED", "Open");
        LABELS.put("ACKNOWLEDGED", "Acknowledged");
        LABELS.put("ASSIGNED", "Assigned");
        LABELS.put("IN_PROGRESS", "In progress");
        LABELS.put("WAITING", "Waiting");
        LABELS.put("RESOLVED", "Resolved");
        LABELS.put("CLOSED", "Closed");
        LABELS.put("REOPENED", "Reopened");

        // Presentation order: the productive step before the parked one.
        TRANSITIONS.put("SUBMITTED", listOf("ACKNOWLEDGED", "IN_PROGRESS", "WAITING"));
        TRANSITIONS.put("ACKNOWLEDGED", listOf("ASSIGNED", "IN_PROGRESS", "WAITING"));
        TRANSITIONS.put("ASSIGNED", listOf("IN_PROGRESS", "WAITING"));
        TRANSITIONS.put("IN_PROGRESS", listOf("RESOLVED", "WAITING"));
        TRANSITIONS.put("WAITING", listOf("ACKNOWLEDGED", "ASSIGNED", "IN_PROGRESS", "RESOLVED"));
        TRANSITIONS.put("RESOLVED", listOf("CLOSED", "REOPENED"));
        TRANSITIONS.put("CLOSED", listOf("REOPENED"));
        TRANSITIONS.put("REOPENED", listOf("ACKNOWLEDGED", "ASSIGNED", "IN_PROGRESS", "WAITING"));

        ACTIONS.put("ACKNOWLEDGED", "Acknowledge");
        ACTIONS.put("ASSIGNED", "Assign");
        ACTIONS.put("IN_PROGRESS", "Start work");
        ACTIONS.put("WAITING", "Mark waiting");
        ACTIONS.put("RESOLVED", "Resolve");
        ACTIONS.put("CLOSED", "Close");
        ACTIONS.put("REOPENED", "Reopen");
    }

    private static Map<String, String> labels = new LinkedHashMap<>(LABELS);
    private static Map<String, List<String>> transitions = new LinkedHashMap<>(TRANSITIONS);
    private static Map<String, String> actions = new LinkedHashMap<>(ACTIONS);
    private static List<String> reopenable = listOf("RESOLVED", "CLOSED");

    private IssueWorkflow() {
    }

    private static List<String> listOf(String... values) {
        List<String> list = new ArrayList<>(values.length);
        Collections.addAll(list, values);
        return Collections.unmodifiableList(list);
    }

    /** Human-readable status name; the persisted {@code SUBMITTED} reads as "Open". */
    public static synchronized String statusLabel(String status) {
        String label = labels.get(status);
        return label != null ? label : titleCase(status);
    }

    /** The button caption for moving from {@code from} to {@code to}. */
    public static String actionLabel(String from, String to) {
        // Coming back from a parked issue is a resumption, not a fresh start.
        if ("WAITING".equals(from) && "IN_PROGRESS".equals(to)) return "Resume work";
        String action = actions.get(to);
        return action != null ? action : "Move to " + statusLabel(to);
    }

    /** Statuses reachable from {@code status}, in presentation order. Empty when terminal. */
    public static synchronized List<String> nextStatuses(String status) {
        List<String> targets = transitions.get(status);
        return targets == null ? Collections.<String>emptyList() : targets;
    }

    /** Whether {@code target} is a legal move out of {@code status}. */
    public static boolean canTransition(String status, String target) {
        return nextStatuses(status).contains(target);
    }

    /** Resolved and closed issues are the only ones a reporter/admin may reopen. */
    public static boolean isReopenable(String status) {
        return reopenable.contains(status);
    }

    /** The backend rejects {@code RESOLVED} unless a summary is supplied. */
    public static boolean requiresResolution(String status) {
        return "RESOLVED".equals(status);
    }

    /** The backend rejects {@code ASSIGNED} unless a staff uid is supplied. */
    public static boolean requiresAssignee(String status) {
        return "ASSIGNED".equals(status);
    }

    /**
     * Adopt the authoritative graph published by the backend. Empty, malformed
     * or {@code null} payloads are ignored so a bad response can never blank
     * out the workflow the screen is about to render.
     */
    public static synchronized void applyServerJson(String json) {
        if (json == null || json.trim().isEmpty() || "null".equals(json.trim())) return;
        try {
            JSONObject payload = new JSONObject(json);

            JSONObject serverLabels = payload.optJSONObject("labels");
            if (serverLabels != null && serverLabels.length() > 0) {
                Map<String, String> next = new LinkedHashMap<>();
                java.util.Iterator<String> keys = serverLabels.keys();
                while (keys.hasNext()) {
                    String key = keys.next();
                    String value = serverLabels.optString(key, "");
                    if (!value.isEmpty() && !"null".equals(value)) next.put(key, value);
                }
                if (!next.isEmpty()) labels = next;
            }

            JSONObject serverTransitions = payload.optJSONObject("transitions");
            if (serverTransitions != null && serverTransitions.length() > 0) {
                Map<String, List<String>> next = new LinkedHashMap<>();
                java.util.Iterator<String> keys = serverTransitions.keys();
                while (keys.hasNext()) {
                    String key = keys.next();
                    org.json.JSONArray targets = serverTransitions.optJSONArray(key);
                    if (targets == null) continue;
                    List<String> list = new ArrayList<>(targets.length());
                    for (int i = 0; i < targets.length(); i++) {
                        String value = targets.optString(i, "");
                        if (!value.isEmpty() && !"null".equals(value)) list.add(value);
                    }
                    next.put(key, Collections.unmodifiableList(list));
                }
                if (!next.isEmpty()) transitions = next;
            }

            org.json.JSONArray serverReopenable = payload.optJSONArray("reopenable");
            if (serverReopenable != null && serverReopenable.length() > 0) {
                List<String> next = new ArrayList<>(serverReopenable.length());
                for (int i = 0; i < serverReopenable.length(); i++) {
                    String value = serverReopenable.optString(i, "");
                    if (!value.isEmpty() && !"null".equals(value)) next.add(value);
                }
                if (!next.isEmpty()) reopenable = Collections.unmodifiableList(next);
            }
        } catch (Exception ignored) {
            // org.json raises JSONException (a checked Exception); the JVM stub in
            // unit tests raises RuntimeException. Either way the built-in
            // defaults must survive an unparsable payload.
        }
    }

    /** Restore the built-in table; used by tests. */
    public static synchronized void reset() {
        labels = new LinkedHashMap<>(LABELS);
        transitions = new LinkedHashMap<>(TRANSITIONS);
        actions = new LinkedHashMap<>(ACTIONS);
        reopenable = listOf("RESOLVED", "CLOSED");
    }

    private static String titleCase(String value) {
        if (value == null || value.isEmpty()) return "Unknown";
        return value.charAt(0) + value.substring(1).toLowerCase(java.util.Locale.US).replace('_', ' ');
    }
}
