package com.aistudio.hydroguard.wxqpzx.ui;

import android.app.Activity;
import android.content.Intent;
import android.content.res.ColorStateList;
import android.graphics.Typeface;
import android.net.Uri;
import android.text.InputType;
import android.view.LayoutInflater;
import android.view.View;
import android.widget.ArrayAdapter;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.Spinner;
import android.widget.TextView;

import androidx.core.content.FileProvider;
import androidx.core.content.res.ResourcesCompat;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

import com.aistudio.hydroguard.wxqpzx.R;
import com.aistudio.hydroguard.wxqpzx.data.api.ApiCallback;
import com.aistudio.hydroguard.wxqpzx.data.api.ApiFailure;
import com.aistudio.hydroguard.wxqpzx.data.api.ApiRepository;
import com.aistudio.hydroguard.wxqpzx.data.api.RetrofitClient;
import com.aistudio.hydroguard.wxqpzx.data.config.HostelConfig;
import com.aistudio.hydroguard.wxqpzx.data.repository.HydroRepository;
import com.aistudio.hydroguard.wxqpzx.data.service.AlertNotifier;
import com.aistudio.hydroguard.wxqpzx.data.service.OpticalRgbService;
import com.aistudio.hydroguard.wxqpzx.data.service.WaterQualityIndexService;
import com.google.android.material.progressindicator.LinearProgressIndicator;
import com.github.mikephil.charting.charts.LineChart;
import com.github.mikephil.charting.components.Legend;
import com.github.mikephil.charting.components.LimitLine;
import com.github.mikephil.charting.components.XAxis;
import com.github.mikephil.charting.components.YAxis;
import com.github.mikephil.charting.data.Entry;
import com.github.mikephil.charting.data.LineData;
import com.github.mikephil.charting.data.LineDataSet;
import com.github.mikephil.charting.formatter.ValueFormatter;
import com.google.android.material.chip.Chip;
import com.google.android.material.chip.ChipGroup;
import com.google.android.material.button.MaterialButtonToggleGroup;
import com.google.android.material.dialog.MaterialAlertDialogBuilder;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TimeZone;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import okhttp3.ResponseBody;
import retrofit2.Call;
import retrofit2.Response;

/** Owns the water monitoring screen: readings, thresholds, charts, alerts, forecasts and admin actions. */
public class WaterScreen {
    private static final String[] RANGE_LABELS = {"24 hours", "7 days", "30 days", "All"};
    private static final int[] RANGE_DAYS = {1, 7, 30, 0};
    /** Gutter between telemetry tiles, in dp. Matches @dimen/card_gap. */
    private static final int COLUMN_GAP_DP = 8;
    private static final String[][] METRICS = {
            {"ph", "pH", ""},
            {"tds", "TDS", " ppm"},
            {"turbidity", "Turbidity", " NTU"},
            {"temperature", "Temperature", " °C"},
    };

    /** Raw sensor channels; displayed only when the reading actually contains them. */
    private static final String[][] SENSOR_CHANNELS = {
            {"red", "Red", " %"},
            {"green", "Green", " %"},
            {"blue", "Blue", " %"},
    };

    /** One worker for CSV downloads: serialises exports and keeps them off the main thread. */
    private static final ExecutorService CSV_EXPORT_EXECUTOR = Executors.newSingleThreadExecutor();

    private final Activity activity;
    private final ApiRepository api;
    private final HydroRepository hydro;
    private final AlertNotifier notifier;
    private final boolean admin;
    private final SimpleDateFormat isoUtc = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US);

    private View screen;
    private String selectedNode;
    private String selectedMetric = "ph";
    private int selectedRange = 1;
    private List<JSONObject> history = new ArrayList<>();
    private JSONObject latestForecast;
    private final Map<String, double[]> thresholds = new HashMap<>();
    private boolean isThingSpeakLoading = false;
    private boolean historySourceThingSpeak = true;


    public WaterScreen(Activity activity, ApiRepository api, HydroRepository hydro,
                       AlertNotifier notifier, boolean admin, String selectedNode) {
        this.activity = activity;
        this.api = api;
        this.hydro = hydro;
        this.notifier = notifier;
        this.admin = admin;
        this.selectedNode = selectedNode;
        isoUtc.setTimeZone(TimeZone.getTimeZone("UTC"));
    }

    public String currentNode() {
        return selectedNode;
    }

    public void attach(View screenView) {
        this.screen = screenView;
        setUpNodeSpinner();
        setUpChips();
        RecyclerView alerts = screen.findViewById(R.id.alerts_list);
        alerts.setLayoutManager(new LinearLayoutManager(activity));
        alerts.setAdapter(new AlertAdapter(admin, (alertId, button) ->
                api.updateAlertStatus(alertId, "ACKNOWLEDGED", new ApiCallback() {
                    @Override public void onSuccess(String json) { loadAlerts(); }
                    @Override public void onFailure(ApiFailure failure) {
                        button.setEnabled(true);
                        toast(failure.getMessage());
                    }
                })));
        SwipeRefreshLayout refresh = screen.findViewById(R.id.water_refresh);
        refresh.setOnRefreshListener(this::refreshAll);
        View headerRefresh = screen.findViewById(R.id.btn_refresh_live);
        if (headerRefresh != null) {
            headerRefresh.setOnClickListener(view -> refreshAll());
        }
        View tsForecastBtn = screen.findViewById(R.id.load_thingspeak_forecast);
        if (tsForecastBtn != null) {
            tsForecastBtn.setOnClickListener(view -> loadThingSpeakForecast());
        }
        if (admin) {
            screen.findViewById(R.id.admin_controls).setVisibility(View.VISIBLE);
            screen.findViewById(R.id.edit_thresholds).setOnClickListener(view -> showThresholdEditor());
            screen.findViewById(R.id.export_csv).setOnClickListener(view -> exportCsv());
        }
        refreshAll();
    }

    private void setUpNodeSpinner() {
        Spinner nodes = screen.findViewById(R.id.node_selector);
        loadNodes(nodes);
    }

    private void loadNodes(Spinner spinner) {
        applyNodeNames(spinner, fallbackNodeNames());
        // The backend deployment description is authoritative. When it cannot be
        // reached the built-in single-tank configuration keeps the screen correct.
        api.getHostelConfiguration(new ApiCallback() {
            @Override public void onSuccess(String json) {
                HostelConfig.applyServerJson(json);
                applyNodeNames(spinner, fallbackNodeNames());
                loadConfiguredNodes(spinner);
            }
            @Override public void onFailure(ApiFailure failure) { loadConfiguredNodes(spinner); }
        });
        spinner.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener() {
            private boolean initialSelectionFired = false;

            @Override public void onItemSelected(android.widget.AdapterView<?> parent, View view, int position, long id) {
                List<String> ids = (List<String>) parent.getTag();
                List<String> fallback = HostelConfig.tankNodeIds();
                String target = ids == null || position >= ids.size()
                        ? fallback.get(Math.min(position, fallback.size() - 1))
                        : ids.get(position);
                if (!initialSelectionFired) {
                    initialSelectionFired = true;
                    selectedNode = target;
                    return;
                }
                if (target != null && !target.equals(selectedNode)) {
                    selectedNode = target;
                    refreshAll();
                }
            }
            @Override public void onNothingSelected(android.widget.AdapterView<?> parent) { }
        });
    }

    private void loadConfiguredNodes(Spinner spinner) {
        api.getNodes(new ApiCallback() {
            @Override public void onSuccess(String json) {
                try {
                    JSONArray rows = new JSONObject(json).optJSONArray("nodes");
                    if (rows == null || rows.length() == 0) return;
                    // Only tanks in the canonical configuration are shown, so an
                    // example tank left over from an old seed can never surface.
                    List<String> configured = HostelConfig.tankNodeIds();
                    List<String> names = new ArrayList<>();
                    List<String> ids = new ArrayList<>();
                    List<JSONObject> visible = new ArrayList<>();
                    for (int i = 0; i < rows.length(); i++) {
                        JSONObject row = rows.getJSONObject(i);
                        String nodeId = row.getString("node_id");
                        if (!configured.contains(nodeId)) continue;
                        ids.add(nodeId);
                        names.add(row.optString("name", nodeId)
                                + " · " + row.optString("status", "offline"));
                        visible.add(row);
                    }
                    if (ids.isEmpty()) return;
                    spinner.setTag(ids);
                    applyNodeNames(spinner, names);
                    if (admin) renderSensorHealth(new JSONArray(visible));
                    if (screen != spinner.getRootView()) return;
                    for (int i = 0; i < ids.size(); i++) {
                        if (ids.get(i).equals(selectedNode)) {
                            spinner.setSelection(i);
                            break;
                        }
                    }
                } catch (JSONException ignored) { }
            }
            @Override public void onFailure(ApiFailure failure) { /* spinner keeps configured tanks */ }
        });
    }

    private List<String> fallbackNodeNames() {
        List<String> names = new ArrayList<>();
        List<String> ids = new ArrayList<>();
        for (HostelConfig.Tank tank : HostelConfig.tanks()) {
            names.add(tank.name);
            ids.add(tank.nodeId);
        }
        spinnerTagIds(ids);
        return names;
    }

    private void spinnerTagIds(List<String> ids) {
        Spinner spinner = screen.findViewById(R.id.node_selector);
        if (spinner != null) spinner.setTag(ids);
    }

    private void applyNodeNames(Spinner spinner, List<String> names) {
        spinner.setAdapter(new ArrayAdapter<>(activity, android.R.layout.simple_spinner_dropdown_item, names));
    }

    private void setUpChips() {
        ChipGroup metricGroup = screen.findViewById(R.id.history_parameter_group);
        metricGroup.removeAllViews();
        for (String[] metric : METRICS) {
            Chip chip = new Chip(activity);
            chip.setText(metric[1]);
            chip.setCheckable(true);
            chip.setChecked(metric[0].equals(selectedMetric));
            chip.setId(View.generateViewId());
            chip.setOnCheckedChangeListener((button, checked) -> {
                if (checked) {
                    selectedMetric = metric[0];
                    renderHistoryChart();
                    renderForecastChart();
                }
            });
            metricGroup.addView(chip);
        }
        TextView parameterCount = screen.findViewById(R.id.history_parameter_count);
        if (parameterCount != null) {
            // Written from METRICS rather than hard-coded, so the caption can
            // never promise a series the app does not offer.
            parameterCount.setText(METRICS.length + " available");
        }
        View sourceLabel = screen.findViewById(R.id.history_source_label);
        View sourceCard = screen.findViewById(R.id.history_source_card);
        if (!admin) {
            if (sourceLabel != null) sourceLabel.setVisibility(View.GONE);
            if (sourceCard != null) sourceCard.setVisibility(View.GONE);
        }
        MaterialButtonToggleGroup sourceGroup = screen.findViewById(R.id.history_source_group);
        if (sourceGroup != null) {
            sourceGroup.addOnButtonCheckedListener((group, checkedId, isChecked) -> {
                if (!isChecked) return;
                boolean useThingSpeak = checkedId == R.id.source_thingspeak;
                if (useThingSpeak == historySourceThingSpeak) return;
                historySourceThingSpeak = useThingSpeak;
                loadHistory();
            });
        }

        // The horizon is a segmented control declared in the layout, so its four
        // buttons already exist and app:checkedButton has already selected the
        // default. Only the listener is attached here: building the buttons here
        // as well would fire a second, redundant history load on first attach.
        MaterialButtonToggleGroup rangeGroup = screen.findViewById(R.id.history_range_group);
        rangeGroup.addOnButtonCheckedListener((group, checkedId, isChecked) -> {
            if (!isChecked) return;
            int index = rangeIndex(checkedId);
            if (index < 0 || index == selectedRange) return;
            selectedRange = index;
            loadHistory();
        });
    }


    /** Maps a horizon segment id back onto RANGE_DAYS, or -1 for anything else. */
    private int rangeIndex(int buttonId) {
        if (buttonId == R.id.range_24h) return 0;
        if (buttonId == R.id.range_7d) return 1;
        if (buttonId == R.id.range_30d) return 2;
        if (buttonId == R.id.range_all) return 3;
        return -1;
    }

    private void refreshAll() {
        loadThingSpeakLive();
        loadThresholds();
        loadHistory();
        loadAlerts();
    }

    private void loadLatest() {
        TextView status = screen.findViewById(R.id.reading_status);
        status.setText("Loading database reading…");
        hydro.loadLatest(selectedNode, new HydroRepository.DataCallback() {
            @Override public void onSuccess(String json, boolean cached, ApiFailure warning) {
                if (!isCurrent()) return;
                try {
                    renderReading(new JSONObject(json), cached, warning);
                } catch (JSONException error) {
                    status.setText("The server returned an unexpected reading.");
                    updateAdvisoryScoreCard(null, null, null, null, false);
                    updateOpticalRgbCard(null);
                }
            }
            @Override public void onFailure(ApiFailure failure) {
                if (isCurrent()) {
                    status.setText(failure.getMessage());
                    updateAdvisoryScoreCard(null, null, null, null, false);
                    updateOpticalRgbCard(null);
                }
            }
        });
    }

    private void loadThresholds() {
        api.getThresholds(new ApiCallback() {
            @Override public void onSuccess(String json) {
                try {
                    JSONArray rows = new JSONObject(json).optJSONArray("thresholds");
                    if (rows == null) return;
                    for (int i = 0; i < rows.length(); i++) {
                        JSONObject row = rows.getJSONObject(i);
                        double min = row.isNull("min") ? Double.NaN : row.getDouble("min");
                        double max = row.isNull("max") ? Double.NaN : row.getDouble("max");
                        thresholds.put(row.getString("parameter"), new double[]{min, max});
                    }
                } catch (JSONException ignored) { }
                // The chart's threshold reference lines come from this response, so
                // redraw once they are known rather than waiting for the next load.
                // Guarded on a non-empty history: thresholds usually arrive before the
                // readings, and re-rendering at that moment would clear the chart to
                // its empty state for as long as the gap lasts. The history callback
                // draws the chart anyway, so an empty history needs no help here.
                if (isCurrent() && !history.isEmpty()) renderHistoryChart();
            }
            @Override public void onFailure(ApiFailure failure) { /* metric cards fall back to index status */ }
        });
    }

    private void loadHistory() {
        TextView chartStatus = screen.findViewById(R.id.history_chart_status);
        chartStatus.setText(historySourceThingSpeak ? "Loading live ThingSpeak feeds…" : "Loading database reading history…");
        String start = isoUtc.format(new Date(System.currentTimeMillis() - RANGE_DAYS[selectedRange] * 86_400_000L));
        ApiCallback callback = new ApiCallback() {
            @Override public void onSuccess(String json) {
                if (!isCurrent()) return;
                try {
                    JSONArray rows = new JSONObject(json).optJSONArray("readings");
                    history = new ArrayList<>();
                    if (rows != null) {
                        for (int i = 0; i < rows.length(); i++) {
                            JSONObject row = rows.optJSONObject(i);
                            if (row != null) history.add(row);
                        }
                    }
                    history.sort((a, b) -> a.optString("timestamp", "").compareTo(b.optString("timestamp", "")));
                    String sourceLabel = historySourceThingSpeak ? "THINGSPEAK" : "DATABASE";
                    chartStatus.setText(describeRange(history.size()) + " · " + sourceLabel);
                    renderHistoryChart();
                    renderForecastChart();
                    JSONObject newest = history.isEmpty() ? null : history.get(history.size() - 1);
                    notifyStale(newest == null ? 0 : parseTimestamp(newest.optString("timestamp")),
                            newest == null ? "" : (historySourceThingSpeak ? "THINGSPEAK" : newest.optString("source")));
                } catch (JSONException error) {
                    chartStatus.setText("Reading history is unavailable.");
                }
            }
            @Override public void onFailure(ApiFailure failure) {
                if (isCurrent()) chartStatus.setText(failure.getMessage());
            }
        };

        if (historySourceThingSpeak) {
            int limit = 30;
            if (selectedRange == 0) limit = 30;
            else if (selectedRange == 1) limit = 50;
            else limit = 100;
            api.getThingSpeakHistory(null, limit, callback);
        } else if (RANGE_DAYS[selectedRange] == 0) {
            api.getReadingHistory(selectedNode, 1000, callback);
        } else {
            api.getReadingHistoryRange(selectedNode, start, null, 1000, callback);
        }
    }


    private long parseTimestamp(String iso) {
        if (iso == null || iso.trim().isEmpty()) return 0;
        String value = iso.trim();
        try {
            return isoUtc.parse(value).getTime();
        } catch (Exception ignored) { }
        try {
            return java.time.Instant.parse(value).toEpochMilli();
        } catch (Exception ignored) { }
        try {
            SimpleDateFormat naiveUtc = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US);
            naiveUtc.setTimeZone(TimeZone.getTimeZone("UTC"));
            return naiveUtc.parse(value).getTime();
        } catch (Exception ignored) { }
        return 0;
    }

    private void notifyStale(long newestMillis, String source) {
        TextView sensorStatus = screen.findViewById(R.id.sensor_status);
        if (sensorStatus == null || !isCurrent()) return;
        if (newestMillis <= 0) {
            sensorStatus.setText("No timestamped readings are available for this range.");
            return;
        }
        long age = Math.max(0, System.currentTimeMillis() - newestMillis);
        if (isLiveSource(source)) {
            if (age > 48 * 3_600_000L) {
                notifier.notifyStaleSensor(selectedNode, newestMillis, 48 * 3_600_000L,
                        Math.round(age / 3_600_000.0) + " hours");
            }
            sensorStatus.setText(age > 48 * 3_600_000L
                    ? "Sensor connection: no reading for " + Math.round(age / 3_600_000.0) + " hours"
                    : "Sensor connection: up to date");
        } else {
            sensorStatus.setText("No live sensor feed · " + getSourceBadge(source)
                    + " (" + describeAge(age) + ")");
        }
    }

    private void renderReading(JSONObject reading, boolean cached, ApiFailure warning) {
        TextView status = screen.findViewById(R.id.reading_status);
        LinearLayout cards = screen.findViewById(R.id.metric_cards);
        cards.removeAllViews();
        String source = reading.optString("source", "");
        String sourceBadge = getSourceBadge(source);
        String timestamp = reading.optString("timestamp", "");
        long readTime = parseTimestamp(timestamp);
        String freshness = getNodeFreshness(readTime, source);

        if (cached) {
            status.setText("Saved reading · " + (warning == null ? "offline" : warning.getMessage())
                    + " · " + sourceBadge);
        } else {
            status.setText("Database reading · " + (readTime > 0 ? shortDate(timestamp) : "time unknown")
                    + " · " + freshness + " · " + sourceBadge);
        }
        // Two tiles per row rather than one flat list of five rows. Cells are weighted so a
        // row always divides evenly: a row that ends up holding a single tile (a metric the
        // reading did not include) expands to full width instead of leaving a hole.
        LinearLayout metricRow = null;
        int cellsInRow = 0;

        // Render primary water-quality metrics (pH, TDS, Turbidity, Temperature).
        for (String[] metric : METRICS) {
            double value = reading.optDouble(metric[0], Double.NaN);
            if (Double.isNaN(value)) continue;
            if (metricRow == null || cellsInRow == 2) {
                boolean firstRow = cards.getChildCount() == 0;
                metricRow = new LinearLayout(activity);
                metricRow.setOrientation(LinearLayout.HORIZONTAL);
                LinearLayout.LayoutParams rowParams = new LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
                if (!firstRow) rowParams.topMargin = dp(COLUMN_GAP_DP);
                cards.addView(metricRow, rowParams);
                cellsInRow = 0;
            }
            cellsInRow = addMetricTile(metricRow, metric[1], format(value) + metric[2], metric[0], reading, value, cellsInRow);
        }

        // Update HydroGuard Advisory Score card and Optical colour (RGB) card
        double phVal = getMetricValue(reading, "ph");
        double tdsVal = getMetricValue(reading, "tds");
        double turbVal = getMetricValue(reading, "turbidity");
        double tempVal = getMetricValue(reading, "temperature");

        boolean isStale = (readTime <= 0) || ((System.currentTimeMillis() - readTime) > (15 * 60 * 1000L));
        updateAdvisoryScoreCard(
                Double.isNaN(phVal) ? null : phVal,
                Double.isNaN(tdsVal) ? null : tdsVal,
                Double.isNaN(turbVal) ? null : turbVal,
                Double.isNaN(tempVal) ? null : tempVal,
                isStale);

        updateOpticalRgbCard(reading);
    }

    private String describeBounds(double[] bounds) {
        boolean hasMin = !Double.isNaN(bounds[0]);
        boolean hasMax = !Double.isNaN(bounds[1]);
        if (hasMin && hasMax) return format(bounds[0]) + " – " + format(bounds[1]);
        if (hasMin) return "above " + format(bounds[0]);
        if (hasMax) return "up to " + format(bounds[1]);
        return "not configured";
    }

    /** Density-independent pixels to raw pixels, for layout params built in code. */
    private int dp(int value) {
        return Math.round(value * activity.getResources().getDisplayMetrics().density);
    }

    private String stateFor(double value, double[] bounds) {
        if (!Double.isNaN(bounds[0]) && value < bounds[0]) return "Below range";
        if (!Double.isNaN(bounds[1]) && value > bounds[1]) return "Above range";
        return "Within range";
    }

    /** Adds a primary metric tile (pH, TDS, Turbidity, Temperature) with threshold support.
     *  Returns the updated cellsInRow count. */
    private int addMetricTile(LinearLayout row, String label, String valueText, String metricKey,
                              JSONObject reading, double value, int cellsInRow) {
        View tile = LayoutInflater.from(activity).inflate(R.layout.item_metric, row, false);
        ((TextView) tile.findViewById(R.id.metric_label)).setText(label);
        ((TextView) tile.findViewById(R.id.metric_value)).setText(valueText);
        double[] bounds = thresholds.get(metricKey);
        TextView thresholdView = tile.findViewById(R.id.metric_threshold);
        TextView statusView = tile.findViewById(R.id.metric_status);
        if (bounds != null) {
            thresholdView.setText("Acceptable " + describeBounds(bounds));
            String state = stateFor(value, bounds);
            statusView.setText(state);
            statusView.setTextColor(activity.getColor("Within range".equals(state)
                    ? R.color.hydroguard_green : R.color.hydroguard_orange));
        } else {
            thresholdView.setText("");
            statusView.setText(WaterQualityIndexService.getParameterStatus(metricKey, (float) value));
            statusView.setTextColor(activity.getColor(R.color.hydroguard_muted));
        }
        LinearLayout.LayoutParams cellParams =
                (LinearLayout.LayoutParams) tile.getLayoutParams();
        cellParams.width = 0;
        cellParams.weight = 1f;
        if (cellsInRow == 1) cellParams.leftMargin = dp(COLUMN_GAP_DP);
        row.addView(tile, cellParams);
        return cellsInRow + 1;
    }

    /** Resolves the object containing RGB channels, whether nested under "rgb" or at the root. */
    private JSONObject getRgbObject(JSONObject reading) {
        if (reading == null) return null;
        if (reading.has("rgb") && !reading.isNull("rgb")) {
            return reading.optJSONObject("rgb");
        }
        return reading;
    }

    /** Extracts metric value case-insensitively, handling "pH"/"ph", "TDS"/"tds", etc. */
    private double getMetricValue(JSONObject values, String key) {
        if (values == null || key == null) return Double.NaN;
        if (values.has(key)) return values.optDouble(key, Double.NaN);
        if ("ph".equalsIgnoreCase(key)) {
            if (values.has("pH")) return values.optDouble("pH", Double.NaN);
            if (values.has("PH")) return values.optDouble("PH", Double.NaN);
        } else if ("tds".equalsIgnoreCase(key)) {
            if (values.has("TDS")) return values.optDouble("TDS", Double.NaN);
        } else if ("turbidity".equalsIgnoreCase(key)) {
            if (values.has("Turbidity")) return values.optDouble("Turbidity", Double.NaN);
        } else if ("temperature".equalsIgnoreCase(key)) {
            if (values.has("Temperature")) return values.optDouble("Temperature", Double.NaN);
            if (values.has("temp")) return values.optDouble("temp", Double.NaN);
        }
        return values.optDouble(key.toLowerCase(Locale.US),
                values.optDouble(key.toUpperCase(Locale.US), Double.NaN));
    }

    /** Updates the HydroGuard Advisory Score card with prominent score, badge, gauge, and contributing summary. */
    private void updateAdvisoryScoreCard(Double ph, Double tds, Double turbidity, Double temperature, boolean isStale) {
        View card = screen.findViewById(R.id.card_advisory_score);
        if (card == null) return;

        WaterQualityIndexService.AdvisoryEvaluation eval =
                WaterQualityIndexService.evaluateAdvisoryScore(ph, tds, turbidity, temperature, isStale);

        TextView badge = screen.findViewById(R.id.advisory_score_badge);
        TextView number = screen.findViewById(R.id.advisory_score_number);
        TextView status = screen.findViewById(R.id.advisory_score_status);
        LinearProgressIndicator progress = screen.findViewById(R.id.advisory_score_progress);
        TextView breakdown = screen.findViewById(R.id.advisory_score_breakdown);
        TextView disclaimer = screen.findViewById(R.id.advisory_score_disclaimer);
        TextView indexSummary = screen.findViewById(R.id.index_summary);

        // Keep hidden index_summary updated for backwards compatibility with tests / accessibility
        if (indexSummary != null) {
            if (eval.score >= 0) {
                indexSummary.setText("Water Quality Index " + eval.score + "/100 · " + eval.badgeText + " (Advisory Indicator)");
            } else {
                indexSummary.setText("Water Quality Index Unavailable (Advisory Indicator)");
            }
        }

        if (badge != null) {
            badge.setText(eval.badgeText);
            int badgeBg;
            int badgeFg;
            if (eval.category != null) {
                switch (eval.category) {
                    case EXCELLENT:
                        badgeBg = activity.getColor(R.color.hydroguard_safe_surface);
                        badgeFg = activity.getColor(R.color.hydroguard_green);
                        break;
                    case GOOD:
                        badgeBg = activity.getColor(R.color.hydroguard_safe_surface);
                        badgeFg = activity.getColor(R.color.hydroguard_teal);
                        break;
                    case MODERATE:
                        badgeBg = activity.getColor(R.color.hydroguard_subsurface);
                        badgeFg = activity.getColor(R.color.hydroguard_blue);
                        break;
                    case POOR:
                        badgeBg = activity.getColor(R.color.hydroguard_caution_surface);
                        badgeFg = activity.getColor(R.color.hydroguard_orange);
                        break;
                    case CRITICAL:
                    default:
                        badgeBg = activity.getColor(R.color.hydroguard_critical_surface);
                        badgeFg = activity.getColor(R.color.hydroguard_red);
                        break;
                }
            } else {
                badgeBg = activity.getColor(R.color.hydroguard_subsurface);
                badgeFg = activity.getColor(R.color.hydroguard_muted);
            }
            if (eval.state == WaterQualityIndexService.ScoreState.PROVISIONAL) {
                badgeBg = activity.getColor(R.color.hydroguard_caution_surface);
                badgeFg = activity.getColor(R.color.hydroguard_orange);
            }
            badge.setBackgroundTintList(ColorStateList.valueOf(badgeBg));
            badge.setTextColor(badgeFg);
        }

        if (number != null) {
            if (eval.score >= 0) {
                number.setText(String.valueOf(eval.score));
            } else {
                number.setText("—");
            }
        }

        if (status != null) {
            status.setText(eval.statusText);
        }

        if (progress != null) {
            if (eval.score >= 0) {
                progress.setProgressCompat(Math.max(0, Math.min(100, eval.score)), true);
                int progressColor;
                if (eval.category != null) {
                    switch (eval.category) {
                        case EXCELLENT: progressColor = activity.getColor(R.color.hydroguard_green); break;
                        case GOOD: progressColor = activity.getColor(R.color.hydroguard_teal); break;
                        case MODERATE: progressColor = activity.getColor(R.color.hydroguard_blue); break;
                        case POOR: progressColor = activity.getColor(R.color.hydroguard_orange); break;
                        case CRITICAL:
                        default: progressColor = activity.getColor(R.color.hydroguard_red); break;
                    }
                } else {
                    progressColor = activity.getColor(R.color.hydroguard_muted);
                }
                if (eval.state == WaterQualityIndexService.ScoreState.PROVISIONAL) {
                    progressColor = activity.getColor(R.color.hydroguard_orange);
                }
                progress.setIndicatorColor(progressColor);
            } else {
                progress.setProgressCompat(0, false);
                progress.setIndicatorColor(activity.getColor(R.color.hydroguard_muted));
            }
        }

        if (breakdown != null) {
            breakdown.setText(eval.breakdownText);
        }

        if (disclaimer != null) {
            disclaimer.setText(eval.disclaimer);
        }
    }

    /** Updates the Optical colour (RGB) card with accurate linear sRGB swatch and 3 aligned mini-metrics. */
    private void updateOpticalRgbCard(JSONObject reading) {
        View card = screen.findViewById(R.id.card_optical_rgb);
        if (card == null) return;

        TextView redView = screen.findViewById(R.id.rgb_red_value);
        TextView greenView = screen.findViewById(R.id.rgb_green_value);
        TextView blueView = screen.findViewById(R.id.rgb_blue_value);
        View swatchView = screen.findViewById(R.id.rgb_swatch_view);
        View swatchCard = screen.findViewById(R.id.rgb_swatch_card);
        TextView footerNote = screen.findViewById(R.id.rgb_footer_note);

        if (OpticalRgbService.hasValidRgb(reading)) {
            int[] rgb = OpticalRgbService.extractRgb(reading);
            int r = rgb[0];
            int g = rgb[1];
            int b = rgb[2];

            if (redView != null) redView.setText(OpticalRgbService.formatPercent(r));
            if (greenView != null) greenView.setText(OpticalRgbService.formatPercent(g));
            if (blueView != null) blueView.setText(OpticalRgbService.formatPercent(b));

            int displayColor = OpticalRgbService.toDisplayColor(r, g, b);
            if (swatchView != null) swatchView.setBackgroundColor(displayColor);
            if (swatchCard instanceof com.google.android.material.card.MaterialCardView) {
                ((com.google.android.material.card.MaterialCardView) swatchCard).setCardBackgroundColor(displayColor);
            }

            if (footerNote != null) {
                footerNote.setText("Relative optical intensity, normalised to 0–100% · Not a validated water-quality measurement");
                footerNote.setTextColor(activity.getColor(R.color.hydroguard_muted));
            }
        } else {
            // Optical readings missing, null, or out of range
            if (redView != null) redView.setText("--%");
            if (greenView != null) greenView.setText("--%");
            if (blueView != null) blueView.setText("--%");

            int neutralColor = activity.getColor(R.color.hydroguard_subsurface);
            if (swatchView != null) swatchView.setBackgroundColor(neutralColor);
            if (swatchCard instanceof com.google.android.material.card.MaterialCardView) {
                ((com.google.android.material.card.MaterialCardView) swatchCard).setCardBackgroundColor(neutralColor);
            }

            if (footerNote != null) {
                footerNote.setText("Optical colour channels unavailable · Sensor not detected or reading pending");
                footerNote.setTextColor(activity.getColor(R.color.hydroguard_muted));
            }
        }
    }

    private void loadAlerts() {
        TextView alertsStatus = screen.findViewById(R.id.alerts_status);
        alertsStatus.setText("Loading alerts…");
        api.getAlerts(selectedNode, new ApiCallback() {
            @Override public void onSuccess(String json) {
                if (!isCurrent()) return;
                try {
                    JSONArray rows = new JSONObject(json).optJSONArray("alerts");
                    List<JSONObject> list = new ArrayList<>();
                    for (int i = 0; rows != null && i < rows.length(); i++) {
                        JSONObject row = rows.optJSONObject(i);
                        if (row != null) list.add(row);
                    }
                    RecyclerView alerts = screen.findViewById(R.id.alerts_list);
                    ((AlertAdapter) alerts.getAdapter()).submit(list);
                    alertsStatus.setText(list.isEmpty()
                            ? "No alerts are currently recorded for this node."
                            : list.size() + " alert records");
                    // Same figure the screen just displayed feeds the top-bar badge, so
                    // the two can never disagree.
                    reportAlertCount(list.size());
                    for (JSONObject row : list) notifier.notifyServerAlert(selectedNode, row);
                } catch (JSONException error) {
                    alertsStatus.setText("The server returned an invalid alert list.");
                    reportAlertCount(0);
                }
            }
            @Override public void onFailure(ApiFailure failure) {
                if (isCurrent()) {
                    alertsStatus.setText(failure.getMessage());
                    // Nothing can be substantiated now, so the badge is cleared rather than
                    // left showing a number from an unverified earlier response.
                    reportAlertCount(0);
                }
            }
        });
    }

    /** Feeds the app bar's alerts badge. Only ever called with a figure from a real response. */
    private void reportAlertCount(int count) {
        if (activity instanceof AlertCountListener) {
            ((AlertCountListener) activity).onAlertCountChanged(count);
        }
    }

    private void loadThingSpeakForecast() {
        TextView forecastStatus = screen.findViewById(R.id.forecast_status);
        forecastStatus.setText("Fetching ThingSpeak data and checking 24-hour forecast…");
        View tsBtn = screen.findViewById(R.id.load_thingspeak_forecast);
        if (tsBtn != null) tsBtn.setEnabled(false);
        api.generateThingSpeakForecast(null, new ApiCallback() {
            @Override public void onSuccess(String json) {
                if (tsBtn != null) tsBtn.setEnabled(true);
                if (!isCurrent()) return;
                try {
                    JSONObject response = new JSONObject(json);
                    if ("not_configured".equals(response.optString("status"))) {
                        forecastStatus.setText("ThingSpeak not configured: " + response.optString("detail"));
                        return;
                    }
                    if ("forecast_unavailable".equals(response.optString("status"))) {
                        String detail = response.optString("detail", "Forecasting requires five features including Optical Colour Index, which is not measured by the hardware. Predictions are withheld.");
                        StringBuilder sb = new StringBuilder();
                        sb.append("Forecast unavailable — more validated sensor history is needed.\n\n");
                        sb.append("Reason: ").append(detail).append("\n\n");
                        sb.append("• Model requirement: Checkpoints (LSTM, PatchTST, TimeMixer) require 5 validated input features.\n");
                        sb.append("• Hardware status: Physical sensor provides 4 parameters (pH, TDS, Turbidity, Temp) plus raw TCS34725 RGB light intensity.\n");
                        sb.append("• Integrity policy: Optical colour index cannot be derived or fabricated from RGB, and current telemetry feeds are insufficient to train and validate a separate model.");
                        JSONObject latestReading = response.optJSONObject("latest_reading");
                        if (latestReading != null) {
                            JSONObject values = latestReading.optJSONObject("values");
                            if (values != null) {
                                sb.append("\n\nLatest measured baseline:\n")
                                        .append("pH ").append(format(getMetricValue(values, "ph")))
                                        .append(" · TDS ").append(format(getMetricValue(values, "tds"))).append(" ppm")
                                        .append(" · Turbidity ").append(format(getMetricValue(values, "turbidity"))).append(" NTU")
                                        .append(" · Temp ").append(format(getMetricValue(values, "temperature"))).append(" °C");
                            }
                            JSONObject rgb = latestReading.optJSONObject("rgb");
                            if (rgb != null && rgb.length() > 0) {
                                sb.append("\nRGB: R=").append(rgb.optInt("red", 0)).append("%")
                                        .append(" G=").append(rgb.optInt("green", 0)).append("%")
                                        .append(" B=").append(rgb.optInt("blue", 0)).append("%");
                            }
                        }
                        forecastStatus.setText(sb.toString());
                        View chartCard = screen.findViewById(R.id.forecast_chart_card);
                        if (chartCard != null) chartCard.setVisibility(View.GONE);
                        TextView badge = screen.findViewById(R.id.forecast_source_badge);
                        if (badge != null) {
                            badge.setVisibility(View.VISIBLE);
                            badge.setText("UNAVAILABLE");
                        }
                        return;
                    }
                    latestForecast = response;
                    JSONObject latestReading = response.optJSONObject("latest_reading");
                    JSONObject forecast = response.optJSONObject("forecast");
                    String dataSource = response.optString("provenance.data_source", "THINGSPEAK");
                    String modelsTrainedOn = response.optString("provenance.models_trained_on", "SIMULATED_DEVELOPMENT");
                    boolean realSensorData = response.optBoolean("provenance.real_sensor_data", false);
                    int horizon = response.optInt("forecast_horizon_hours", 24);
                    String provenanceNote;
                    if (dataSource.equals("THINGSPEAK")) {
                        provenanceNote = "ThingSpeak channel · Models trained on " + modelsTrainedOn +
                                (realSensorData ? " (real sensor training)" : " (simulated training)");
                    } else {
                        provenanceNote = "Source: " + dataSource;
                    }
                    String forecastDate = response.optString("provenance.fetched_at", "");
                    StringBuilder sb = new StringBuilder();
                    sb.append("ThingSpeak Forecast");
                    if (!forecastDate.isEmpty()) {
                        sb.append(" · Fetched ").append(Timestamps.readable(forecastDate));
                    }
                    sb.append("\nHorizon: next ").append(horizon).append(" hours");
                    sb.append("\nModels: LSTM, PatchTST, TimeMixer with adaptive ensemble");
                    if (forecast != null) {
                        JSONObject ensemble = forecast.optJSONObject("ensemble");
                        if (ensemble != null) {
                            sb.append("\nEnsemble: pH ").append(format(getMetricValue(ensemble, "ph")))
                                    .append(" · TDS ").append(format(getMetricValue(ensemble, "tds"))).append(" ppm")
                                    .append(" · Turbidity ").append(format(getMetricValue(ensemble, "turbidity"))).append(" NTU")
                                    .append(" · Temp ").append(format(getMetricValue(ensemble, "temperature"))).append(" °C")
                                    .append(" · OCI ").append(format(ensemble.optDouble("optical_colour_index", Double.NaN)));
                        }
                    }
                    sb.append("\n").append(provenanceNote);
                    if (latestReading != null) {
                        JSONObject values = latestReading.optJSONObject("values");
                        if (values != null) {
                            sb.append("\nLatest: pH ").append(format(getMetricValue(values, "ph")))
                                    .append(" · TDS ").append(format(getMetricValue(values, "tds"))).append(" ppm")
                                    .append(" · Turbidity ").append(format(getMetricValue(values, "turbidity"))).append(" NTU")
                                    .append(" · Temp ").append(format(getMetricValue(values, "temperature"))).append(" °C");
                            JSONObject rgb = latestReading.optJSONObject("rgb");
                            if (rgb != null && rgb.length() > 0) {
                                sb.append("\nRGB: R=").append(rgb.optInt("red", 0)).append("%")
                                        .append(" G=").append(rgb.optInt("green", 0)).append("%")
                                        .append(" B=").append(rgb.optInt("blue", 0)).append("%");
                            }
                        }
                    }
                    forecastStatus.setText(sb.toString());
                    View chartCard = screen.findViewById(R.id.forecast_chart_card);
                    if (chartCard != null) chartCard.setVisibility(View.VISIBLE);
                    renderForecastProvenance();
                    renderForecastChart();
                } catch (JSONException error) {
                    forecastStatus.setText("The server returned an invalid ThingSpeak forecast.");
                }
            }

            @Override public void onFailure(ApiFailure failure) {
                if (tsBtn != null) tsBtn.setEnabled(true);
                if (isCurrent()) forecastStatus.setText(failure.getMessage());
            }
        });
    }

    /** Load the latest live reading from ThingSpeak without running a forecast. */
    private void loadThingSpeakLive() {
        if (isThingSpeakLoading) return;
        isThingSpeakLoading = true;
        TextView status = screen.findViewById(R.id.reading_status);
        if (status != null) {
            status.setText("Fetching live ThingSpeak reading…");
        }
        View headerRefresh = screen.findViewById(R.id.btn_refresh_live);
        if (headerRefresh != null) headerRefresh.setEnabled(false);
        SwipeRefreshLayout refresh = screen.findViewById(R.id.water_refresh);

        api.getLatestThingSpeakReading(null, new ApiCallback() {
            @Override public void onSuccess(String json) {
                isThingSpeakLoading = false;
                if (headerRefresh != null) headerRefresh.setEnabled(true);
                if (refresh != null) refresh.setRefreshing(false);
                if (!isCurrent()) return;
                try {
                    JSONObject response = new JSONObject(json);
                    renderThingSpeakLiveReading(response);
                } catch (JSONException error) {
                    showLiveReadingError("The server returned an invalid ThingSpeak reading.");
                }
            }

            @Override public void onFailure(ApiFailure failure) {
                isThingSpeakLoading = false;
                if (headerRefresh != null) headerRefresh.setEnabled(true);
                if (refresh != null) refresh.setRefreshing(false);
                if (!isCurrent()) return;
                showLiveReadingError(failure.getMessage());
            }
        });
    }

    private void showLiveReadingError(String message) {
        TextView status = screen.findViewById(R.id.reading_status);
        if (status != null) {
            status.setText("Live ThingSpeak fetch failed: " + message + " · Tap Refresh above to retry.");
        }
        TextView sensorStatus = screen.findViewById(R.id.sensor_status);
        if (sensorStatus != null) {
            sensorStatus.setText("ThingSpeak Channel 244357 · Telemetry unreachable");
        }
        LinearLayout cards = screen.findViewById(R.id.metric_cards);
        if (cards != null) {
            cards.removeAllViews();
            LinearLayout errorCard = new LinearLayout(activity);
            errorCard.setOrientation(LinearLayout.VERTICAL);
            errorCard.setPadding(dp(16), dp(20), dp(16), dp(20));
            errorCard.setGravity(android.view.Gravity.CENTER);
            errorCard.setBackgroundColor(activity.getColor(R.color.hydroguard_surface));

            TextView errorTitle = new TextView(activity);
            errorTitle.setText("Live Telemetry Unavailable");
            errorTitle.setTextColor(activity.getColor(R.color.hydroguard_text));
            errorTitle.setTextSize(14f);
            errorTitle.setTypeface(null, android.graphics.Typeface.BOLD);
            errorTitle.setGravity(android.view.Gravity.CENTER);
            errorCard.addView(errorTitle);

            TextView errorDesc = new TextView(activity);
            errorDesc.setText("Could not retrieve latest readings from ThingSpeak channel 244357.\nVerify network connection or server status and tap Refresh above.\nSimulated or cached records are withheld in production.");
            errorDesc.setTextColor(activity.getColor(R.color.hydroguard_muted));
            errorDesc.setTextSize(12f);
            errorDesc.setGravity(android.view.Gravity.CENTER);
            LinearLayout.LayoutParams descParams = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
            descParams.topMargin = dp(6);
            errorCard.addView(errorDesc, descParams);

            cards.addView(errorCard);
        }
        TextView indexSummary = screen.findViewById(R.id.index_summary);
        if (indexSummary != null) {
            indexSummary.setText("HydroGuard index unavailable · Live sensor telemetry required");
        }
        updateAdvisoryScoreCard(null, null, null, null, false);
        updateOpticalRgbCard(null);
    }

    /** Render a live ThingSpeak reading in the metric cards with correct units. */
    private void renderThingSpeakLiveReading(JSONObject reading) {
        TextView status = screen.findViewById(R.id.reading_status);
        LinearLayout cards = screen.findViewById(R.id.metric_cards);
        cards.removeAllViews();

        String timestamp = reading.optString("timestamp", "");
        long readTime = parseTimestamp(timestamp);
        String observedAt = reading.optString("observed_at", "");
        long observedTime = parseTimestamp(observedAt);

        String freshness = "up to date";
        if (readTime > 0) {
            long age = Math.max(0, System.currentTimeMillis() - readTime);
            if (age < 5 * 60 * 1000L) freshness = "up to date";
            else if (age < 30 * 60 * 1000L) freshness = "stale";
            else freshness = "no reading for " + Math.round(age / 3_600_000.0) + " hours";
        } else {
            freshness = "time unknown";
        }

        status.setText("Hostel Water Tank · " + (readTime > 0 ? shortDate(timestamp) : "time unknown")
                + " · " + freshness);

        TextView sensorStatus = screen.findViewById(R.id.sensor_status);
        if (sensorStatus != null) {
            int entryId = reading.optInt("entry_id", 0);
            int statusFlag = reading.optInt("status_flag", -1);
            String hwStatus = statusFlag == 0 ? "Normal" : (statusFlag > 0 ? "Flag " + statusFlag : "");
            sensorStatus.setText("Hostel Telemetry Feed · Channel 244357" + (entryId > 0 ? " · #" + entryId : "")
                    + (!hwStatus.isEmpty() ? " · " + hwStatus : "") + " · Source: ThingSpeak");
        }

        // Render primary water-quality metrics
        LinearLayout metricRow = null;
        int cellsInRow = 0;

        JSONObject values = reading.optJSONObject("values");
        if (values != null) {
            for (String[] metric : METRICS) {
                String key = metric[0];
                double value = getMetricValue(values, key);
                if (Double.isNaN(value)) continue;
                if (metricRow == null || cellsInRow == 2) {
                    boolean firstRow = cards.getChildCount() == 0;
                    metricRow = new LinearLayout(activity);
                    metricRow.setOrientation(LinearLayout.HORIZONTAL);
                    LinearLayout.LayoutParams rowParams = new LinearLayout.LayoutParams(
                            LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
                    if (!firstRow) rowParams.topMargin = dp(COLUMN_GAP_DP);
                    cards.addView(metricRow, rowParams);
                    cellsInRow = 0;
                }
                cellsInRow = addMetricTile(metricRow, metric[1], format(value) + metric[2], key, reading, value, cellsInRow);
            }

            // Update HydroGuard Advisory Score card
            double ph = getMetricValue(values, "ph");
            double tds = getMetricValue(values, "tds");
            double turbidity = getMetricValue(values, "turbidity");
            double temperature = getMetricValue(values, "temperature");

            boolean isStale = (readTime <= 0) || ((System.currentTimeMillis() - readTime) > (15 * 60 * 1000L));
            updateAdvisoryScoreCard(
                    Double.isNaN(ph) ? null : ph,
                    Double.isNaN(tds) ? null : tds,
                    Double.isNaN(turbidity) ? null : turbidity,
                    Double.isNaN(temperature) ? null : temperature,
                    isStale);
        } else {
            updateAdvisoryScoreCard(null, null, null, null, false);
        }

        // Update Optical colour (RGB) card
        updateOpticalRgbCard(reading);

        notifyStale(readTime, "THINGSPEAK");
    }

    /**
     * Checks if a measured sensor value represents a physically valid aqueous observation
     * rather than an open-circuit / 0V ADC sensor dropout or unphysical artifact.
     */
    private static boolean isPhysicallyValid(String metric, double value) {
        if (Double.isNaN(value) || Double.isInfinite(value)) return false;
        String m = metric.toLowerCase(Locale.ROOT);
        if ("ph".equals(m)) {
            // Natural aqueous water: 0.5 <= pH <= 14.0. pH <= 0.05 is an open-circuit 0V analog probe dropout.
            return value > 0.05 && value <= 14.0;
        } else if ("tds".equals(m)) {
            return value >= 0.0 && value < 4000.0;
        } else if ("turbidity".equals(m)) {
            return value >= 0.0 && value < 1000.0;
        } else if ("temperature".equals(m)) {
            return value > 0.5 && value < 75.0;
        }
        return true;
    }

    private String metricUnit(String metric) {
        for (String[] candidate : METRICS) {
            if (candidate[0].equalsIgnoreCase(metric)) return candidate[2].trim();
        }
        for (String[] candidate : SENSOR_CHANNELS) {
            if (candidate[0].equalsIgnoreCase(metric)) return candidate[2].trim();
        }
        return "";
    }

    private void renderHistoryChart() {
        LineChart chart = screen.findViewById(R.id.history_chart);
        TextView title = screen.findViewById(R.id.history_chart_title);
        TextView status = screen.findViewById(R.id.history_chart_status);

        List<Entry> entries = new ArrayList<>();
        List<String> labels = new ArrayList<>();
        int index = 0;
        int droppedOut = 0;
        double latestVal = Double.NaN;

        for (JSONObject row : history) {
            double value = row.optDouble(selectedMetric, Double.NaN);
            if (Double.isNaN(value) && "ph".equalsIgnoreCase(selectedMetric)) {
                value = row.optDouble("pH", Double.NaN);
            } else if (Double.isNaN(value) && "tds".equalsIgnoreCase(selectedMetric)) {
                value = row.optDouble("TDS", Double.NaN);
            }
            if (Double.isNaN(value)) continue;

            if (!isPhysicallyValid(selectedMetric, value)) {
                droppedOut++;
                continue;
            }

            entries.add(new Entry(index++, (float) value));
            String timeStr = shortDate(row.optString("timestamp", ""));
            labels.add(timeStr);
            latestVal = value;
        }

        if (title != null) {
            String unit = metricUnit(selectedMetric);
            String latestStr = Double.isNaN(latestVal) ? "--" : (format(latestVal) + (unit.isEmpty() ? "" : " " + unit));
            title.setText(metricLabel(selectedMetric) + " · " + RANGE_LABELS[selectedRange] + " (Latest: " + latestStr + ")");
        }

        if (status != null) {
            if (entries.isEmpty()) {
                status.setText("No valid observations found for this range.");
            } else {
                float first = entries.get(0).getY();
                float last = entries.get(entries.size() - 1).getY();
                float delta = last - first;
                String unit = metricUnit(selectedMetric);
                String trend = (Math.abs(delta) < 0.05 ? "→ Stable" : (delta > 0 ? "↗ +" : "↘ ") + format(delta) + (unit.isEmpty() ? "" : " " + unit));
                String qualityNote = droppedOut > 0 ? " · " + droppedOut + " dropout" + (droppedOut > 1 ? "s" : "") + " filtered" : "";
                status.setText(entries.size() + " points · " + trend + " · Tap point to inspect" + qualityNote);
            }
        }

        if (entries.isEmpty()) {
            chart.clear();
            return;
        }

        String datasetLabel = historySourceThingSpeak ? "Observed Telemetry" : "Observed (Saved DB)";
        chart.setData(buildData(entries, labels, datasetLabel,
                activity.getColor(R.color.hydroguard_chart_observed), false));
        applyThresholdLines(chart, entries);
        styleChart(chart, labels);
        redrawAfterLayout(chart);
    }


    /**
     * Re-notifies the chart on the next layout pass.
     *
     * <p>Both charts live inside a ScrollView, and the first {@code setData} can
     * land before the first layout, when the view still measures zero. The data
     * is set correctly but the placeholder text stays on screen. Posting a
     * re-notify to the next pass clears that stale state.</p>
     */
    private void redrawAfterLayout(LineChart chart) {
        chart.post(() -> {
            if (chart.getData() == null) return;
            chart.notifyDataSetChanged();
            chart.invalidate();
        });
    }

    /**
     * Draws the configured bounds for the selected parameter as dashed reference
     * lines, exactly as the reference draws its permissible threshold.
     *
     * <p>The axis is widened to include a bound that falls outside the plotted
     * data. MPAndroidChart does not expand an axis to fit a LimitLine, so a 300 ppm
     * limit on a series that only reaches 180 would otherwise be drawn beyond the
     * plot area and clipped away — configured, but invisible.</p>
     */
    private void applyThresholdLines(LineChart chart, List<Entry> entries) {
        YAxis axis = chart.getAxisLeft();
        axis.removeAllLimitLines();
        float dataMin = Float.MAX_VALUE;
        float dataMax = -Float.MAX_VALUE;
        for (Entry entry : entries) {
            dataMin = Math.min(dataMin, entry.getY());
            dataMax = Math.max(dataMax, entry.getY());
        }
        double[] bounds = thresholds.get(selectedMetric);
        float min = dataMin;
        float max = dataMax;
        if (bounds != null) {
            if (!Double.isNaN(bounds[1])) {
                max = Math.max(max, (float) bounds[1]);
                addValueLimitLine(axis, (float) bounds[1], "Limit " + format(bounds[1]));
            }
            if (!Double.isNaN(bounds[0])) {
                min = Math.min(min, (float) bounds[0]);
                addValueLimitLine(axis, (float) bounds[0], "Minimum " + format(bounds[0]));
            }
        }
        // A series of identical readings has no range, so give the axis one rather
        // than leaving a zero-height plot.
        if (max <= min) {
            min -= 1f;
            max += 1f;
        }
        float padding = (max - min) * 0.15f;
        axis.setAxisMinimum(min - padding);
        axis.setAxisMaximum(max + padding);
    }

    private void addValueLimitLine(YAxis axis, float value, String label) {
        LimitLine line = new LimitLine(value, label);
        line.setLineWidth(1f);
        line.enableDashedLine(6f, 6f, 0f);
        line.setLineColor(activity.getColor(R.color.hydroguard_chart_threshold));
        line.setTextColor(activity.getColor(R.color.hydroguard_chart_threshold));
        line.setTextSize(10f);
        line.setLabelPosition(LimitLine.LimitLabelPosition.RIGHT_TOP);
        axis.addLimitLine(line);
    }

    private void renderForecastChart() {
        if (latestForecast == null) return;
        LineChart chart = screen.findViewById(R.id.forecast_chart);
        JSONObject prediction = latestForecast.optJSONObject("prediction");
        if (prediction == null) return;
        double value = prediction.optDouble(metricKeyForForecast(selectedMetric), Double.NaN);
        if (Double.isNaN(value)) return;
        ((TextView) screen.findViewById(R.id.forecast_chart_title))
                .setText(metricLabel(selectedMetric) + " · history and predicted next value");
        List<Entry> observed = new ArrayList<>();
        List<Entry> predicted = new ArrayList<>();
        List<String> observedLabels = new ArrayList<>();
        List<String> predictedLabels = new ArrayList<>();
        int shown = 0;
        int start = Math.max(0, history.size() - 15);
        for (int i = start; i < history.size(); i++) {
            double metricValue = history.get(i).optDouble(selectedMetric, Double.NaN);
            if (Double.isNaN(metricValue)) continue;
            observed.add(new Entry(shown, (float) metricValue));
            observedLabels.add(shortDate(history.get(i).optString("timestamp", "")));
            shown++;
        }
        if (observed.isEmpty()) return;
        // The predicted point is a separate series, so the legend can tell the two
        // apart instead of blending history and forecast into one line.
        predicted.add(new Entry(shown, (float) value));
        predictedLabels.add("Forecast");
        chart.setData(buildForecastData(observed, observedLabels, predicted, predictedLabels));
        // Same bounds as the history chart. The legend states the permissible
        // threshold, so the chart beside it has to draw it; leaving it out would
        // make the legend promise a line the plot never shows.
        List<Entry> axisRange = new ArrayList<>(observed);
        axisRange.addAll(predicted);
        applyThresholdLines(chart, axisRange);
        styleChart(chart, observedLabels);
        markNowBoundary(chart, observed.size() - 1);
        redrawAfterLayout(chart);
        renderForecastProvenance();
    }

    /**
     * Draws the observed/predicted boundary. Everything left of it is a recorded
     * reading and the predicted point sits to its right, so the divider states
     * plainly where measurement stops and the model starts.
     */
    private void markNowBoundary(LineChart chart, int lastObservedIndex) {
        XAxis axis = chart.getXAxis();
        axis.removeAllLimitLines();
        if (lastObservedIndex <= 0) return;
        LimitLine now = new LimitLine(lastObservedIndex, "NOW");
        now.setLineWidth(1f);
        now.enableDashedLine(2f, 2f, 0f);
        now.setLineColor(activity.getColor(R.color.hydroguard_navy));
        now.setTextColor(activity.getColor(R.color.hydroguard_navy));
        now.setTextSize(10f);
        // Labelled to the left: the boundary sits one point from the right edge,
        // so a right-aligned label would run off the plot.
        now.setLabelPosition(LimitLine.LimitLabelPosition.LEFT_TOP);
        axis.addLimitLine(now);
    }

    /**
     * Fills the provenance legend and the notice badge from real response fields.
     *
     * <p>The observed badge reports the source tag of the readings actually
     * plotted, and the notice badge reports the forecast's own declared
     * data_source. Neither is inferred from the fact that a request succeeded, and
     * no confidence figure or model version is displayed because the backend does
     * not send one.</p>
     */
    private void renderForecastProvenance() {
        View observedBadge = screen.findViewById(R.id.legend_observed_badge);
        if (observedBadge != null) {
            String source = null;
            for (int i = history.size() - 1; i >= 0; i--) {
                String candidate = history.get(i).optString("source", "").trim();
                if (!candidate.isEmpty()) {
                    source = candidate;
                    break;
                }
            }
            if (source == null) {
                // Nothing plotted has a provenance tag, so no badge is shown.
                observedBadge.setVisibility(View.GONE);
            } else {
                applyProvenanceBadge((TextView) observedBadge, source);
            }
        }

        applyForecastSourceBadge(latestForecast == null
                ? "" : latestForecast.optString("data_source", "").trim());

        // The threshold row only appears when the server has actually configured
        // one for the selected parameter.
        View thresholdRow = screen.findViewById(R.id.legend_threshold_row);
        if (thresholdRow != null) {
            double[] bounds = thresholds.get(selectedMetric);
            if (bounds == null) {
                thresholdRow.setVisibility(View.GONE);
            } else {
                thresholdRow.setVisibility(View.VISIBLE);
                ((TextView) screen.findViewById(R.id.legend_threshold_label))
                        .setText("Permissible threshold");
                ((TextView) screen.findViewById(R.id.legend_threshold_badge))
                        .setText(describeBounds(bounds));
            }
        }
    }

    /** Colours a provenance badge to agree with the source tag it is showing. */
    private void applyProvenanceBadge(TextView badge, String source) {
        boolean live = isLiveSource(source);
        String label = getSourceBadge(source);
        int text;
        int fill;
        if (live) {
            text = activity.getColor(R.color.hydroguard_provenance_live);
            fill = activity.getColor(R.color.hydroguard_provenance_live_bg);
        } else if ("DEMO DATA".equals(label)) {
            text = activity.getColor(R.color.hydroguard_provenance_simulated_text);
            fill = activity.getColor(R.color.hydroguard_provenance_simulated_bg);
        } else {
            text = activity.getColor(R.color.hydroguard_provenance_unknown);
            fill = activity.getColor(R.color.hydroguard_provenance_unknown_bg);
        }
        badge.setText(label);
        badge.setTextColor(text);
        badge.setBackgroundTintList(ColorStateList.valueOf(fill));
        badge.setVisibility(View.VISIBLE);
    }

    /**
     * Labels the notice card with the class of data the forecast was built from.
     *
     * <p>An unrecognised tag is reported as "SOURCE RECORDED" rather than being
     * forced into one of the known classes, and an absent tag hides the badge — a
     * forecast whose basis the server did not state must not be given one.</p>
     */
    private void applyForecastSourceBadge(String dataSource) {
        TextView badge = screen.findViewById(R.id.forecast_source_badge);
        if (badge == null) return;
        if (dataSource.isEmpty()) {
            badge.setVisibility(View.GONE);
            return;
        }
        String upper = dataSource.toUpperCase(Locale.ROOT);
        String label;
        int text;
        int fill;
        if (upper.contains("REAL") || upper.contains("LIVE") || upper.contains("THINGSPEAK")) {
            label = "LIVE SOURCE";
            text = activity.getColor(R.color.hydroguard_provenance_live);
            fill = activity.getColor(R.color.hydroguard_provenance_live_bg);
        } else if (upper.contains("SIMULATED") || upper.contains("DEVELOPMENT")
                || upper.contains("DEMO")) {
            label = "DEMO DATA";
            text = activity.getColor(R.color.hydroguard_provenance_simulated_text);
            fill = activity.getColor(R.color.hydroguard_provenance_simulated_bg);
        } else if (upper.contains("HISTORICAL")) {
            label = "HISTORICAL DATA";
            text = activity.getColor(R.color.hydroguard_provenance_unknown);
            fill = activity.getColor(R.color.hydroguard_provenance_unknown_bg);
        } else {
            label = "SOURCE RECORDED";
            text = activity.getColor(R.color.hydroguard_provenance_unknown);
            fill = activity.getColor(R.color.hydroguard_provenance_unknown_bg);
        }
        badge.setText(label);
        badge.setTextColor(text);
        badge.setBackgroundTintList(ColorStateList.valueOf(fill));
        badge.setVisibility(View.VISIBLE);
    }

    /**
     * Builds two series — observed history and the predicted next value — so they are
     * visually and legibly distinct. The forecast series is drawn as points only, with
     * no connecting line, because a single predicted point has no trend behind it.
     */
    private LineData buildForecastData(List<Entry> observed, List<String> observedLabels,
                                       List<Entry> predicted, List<String> predictedLabels) {
        int observedColor = activity.getColor(R.color.hydroguard_chart_observed);
        int forecastColor = activity.getColor(R.color.hydroguard_chart_forecast);

        LineDataSet observedSet = new LineDataSet(observed, "Observed Telemetry");
        observedSet.setColor(observedColor);
        observedSet.setCircleColor(observedColor);
        observedSet.setCircleRadius(3.5f);
        observedSet.setCircleHoleRadius(2.0f);
        observedSet.setCircleHoleColor(activity.getColor(R.color.hydroguard_surface));
        observedSet.setDrawValues(false);
        observedSet.setLineWidth(2.5f);
        observedSet.setMode(LineDataSet.Mode.LINEAR);
        observedSet.setDrawFilled(true);
        observedSet.setFillColor(observedColor);
        observedSet.setFillAlpha(25);

        LineDataSet forecastSet = new LineDataSet(predicted, "24h Forecast");
        forecastSet.setColor(forecastColor);
        forecastSet.setCircleColor(forecastColor);
        forecastSet.setCircleRadius(5f);
        forecastSet.setCircleHoleRadius(2.5f);
        forecastSet.setCircleHoleColor(activity.getColor(R.color.hydroguard_surface));
        forecastSet.setDrawValues(false);
        // No line: a lone predicted point must not look like a measured trend.
        forecastSet.setLineWidth(0f);
        forecastSet.enableDashedLine(6f, 6f, 0f);

        LineData data = new LineData(observedSet, forecastSet);
        data.setValueFormatter(new ValueFormatter() {
            @Override public String getPointLabel(Entry entry) {
                int i = (int) entry.getX();
                if (entry == observed.get(observed.size() - 1)) {
                    return observedLabels.isEmpty() ? "" : observedLabels.get(observedLabels.size() - 1);
                }
                if (!predicted.isEmpty() && entry == predicted.get(0)) {
                    return predictedLabels.isEmpty() ? "" : predictedLabels.get(0);
                }
                return i < observedLabels.size() ? observedLabels.get(i) : "";
            }
        });
        return data;
    }

    private LineData buildData(List<Entry> entries, List<String> labels, String name, int color, boolean showLast) {
        LineDataSet set = new LineDataSet(entries, name);
        set.setColor(color);
        set.setCircleColor(color);
        set.setCircleRadius(3.5f);
        set.setCircleHoleRadius(2.0f);
        set.setCircleHoleColor(activity.getColor(R.color.hydroguard_surface));
        set.setDrawValues(false);
        set.setLineWidth(2.5f);
        set.setMode(LineDataSet.Mode.LINEAR);
        set.setDrawFilled(true);
        set.setFillColor(color);
        set.setFillAlpha(25);
        set.setDrawHighlightIndicators(true);
        set.setHighLightColor(activity.getColor(R.color.hydroguard_cerulean));
        set.setHighlightLineWidth(1.2f);
        set.enableDashedHighlightLine(4f, 3f, 0f);

        LineData data = new LineData(set);
        data.setValueFormatter(new ValueFormatter() {
            @Override public String getPointLabel(Entry entry) {
                int i = (int) entry.getX();
                return i < labels.size() ? labels.get(i) : "";
            }
        });
        return data;
    }

    /**
     * Shared chart appearance: mono telemetry axes, a single gridline colour and
     * at most six time ticks.
     *
     * <p>The tick cap matters. "All" returns up to a thousand readings, and an
     * uncapped axis draws a label per point — an unreadable smear. Ticks are
     * therefore spaced by a step derived from the data, and a point that is not on
     * the step returns an empty label.</p>
     */
    private void styleChart(LineChart chart, final List<String> labels) {
        chart.getDescription().setEnabled(false);
        chart.getLegend().setEnabled(true);
        chart.getLegend().setVerticalAlignment(Legend.LegendVerticalAlignment.BOTTOM);
        chart.getLegend().setHorizontalAlignment(Legend.LegendHorizontalAlignment.LEFT);
        chart.getLegend().setTextSize(11f);
        chart.getLegend().setTextColor(activity.getColor(R.color.hydroguard_muted));

        // Numerals are JetBrains Mono per the typography rule. A missing font must
        // not blank the chart, so the axes simply keep the theme's default family.
        Typeface mono = ResourcesCompat.getFont(activity, R.font.hydroguard_mono);
        // Ticks are compacted to time-of-day when the span fits inside one day and
        // to the date otherwise. A full "MM-DD HH:mm" at every tick overruns the
        // axis and the labels collide into an unreadable smear.
        final List<String> ticks = compactAxisLabels(labels);
        final int step = Math.max(1, (int) Math.ceil(ticks.size() / 5.0));

        XAxis xAxis = chart.getXAxis();
        xAxis.setPosition(XAxis.XAxisPosition.BOTTOM);
        xAxis.setDrawGridLines(false);
        xAxis.setDrawLabels(true);
        xAxis.setTextColor(activity.getColor(R.color.hydroguard_muted));
        xAxis.setTextSize(10f);
        xAxis.setAvoidFirstLastClipping(true);
        if (mono != null) xAxis.setTypeface(mono);
        xAxis.setValueFormatter(new ValueFormatter() {
            @Override public String getFormattedValue(float value) {
                int i = Math.round(value);
                if (i < 0 || i >= ticks.size() || i % step != 0) return "";
                return ticks.get(i);
            }
        });

        YAxis yAxis = chart.getAxisLeft();
        yAxis.setDrawGridLines(true);
        yAxis.setGridColor(activity.getColor(R.color.hydroguard_chart_grid));
        yAxis.setGridLineWidth(1f);
        yAxis.setTextColor(activity.getColor(R.color.hydroguard_muted));
        yAxis.setTextSize(10f);
        yAxis.setAxisLineColor(activity.getColor(R.color.hydroguard_divider));
        yAxis.setLabelCount(4, true);
        if (mono != null) yAxis.setTypeface(mono);

        chart.getAxisRight().setEnabled(false);
        chart.setDrawGridBackground(false);
        chart.setScaleEnabled(false);
        chart.setTouchEnabled(true);
        chart.setDragEnabled(false);
        chart.setPinchZoom(false);
        chart.setDoubleTapToZoomEnabled(false);

        // Interactive inspection tooltip
        HydroGuardMarkerView marker = new HydroGuardMarkerView(activity, labels, metricUnit(selectedMetric));
        marker.setChartView(chart);
        chart.setMarker(marker);

        chart.setExtraTopOffset(10f);
        chart.setExtraBottomOffset(4f);
        chart.notifyDataSetChanged();
    }

    /**
     * Shortens axis ticks without inventing precision.
     *
     * <p>{@link #shortDate} produces "MM-DD HH:mm". When every plotted reading
     * falls on one day the date is redundant, so only the time is shown; across
     * days the time is redundant, so only the date is shown. Either way the tick
     * stays a value read off the reading's own timestamp.</p>
     */
    private List<String> compactAxisLabels(List<String> labels) {
        boolean sameDay = labels.size() > 1
                && labels.get(0).length() >= 6
                && labels.get(labels.size() - 1).length() >= 6
                && labels.get(0).substring(0, 5).equals(labels.get(labels.size() - 1).substring(0, 5));
        List<String> ticks = new ArrayList<>(labels.size());
        for (String label : labels) {
            if (sameDay) {
                ticks.add(label.length() > 6 ? label.substring(6) : label);
            } else {
                ticks.add(label.length() >= 5 ? label.substring(0, 5) : label);
            }
        }
        return ticks;
    }

    private String metricKeyForForecast(String metric) {
        switch (metric) {
            case "ph": return "pH";
            case "tds": return "TDS";
            default: return metric;
        }
    }

    private String metricLabel(String metric) {
        for (String[] candidate : METRICS) if (candidate[0].equals(metric)) return candidate[1];
        return metric;
    }

    private String shortDate(String timestamp) {
        String trimmed = timestamp.replace("T", " ");
        return trimmed.length() >= 16 ? trimmed.substring(5, 16) : trimmed;
    }

    private void showThresholdEditor() {
        String[] names = new String[METRICS.length];
        for (int i = 0; i < METRICS.length; i++) names[i] = METRICS[i][1];
        new MaterialAlertDialogBuilder(activity)
                .setTitle("Select a parameter")
                .setItems(names, (dialog, which) -> editThreshold(METRICS[which][0], METRICS[which][1]))
                .show();
    }

    private void editThreshold(String key, String label) {
        LinearLayout form = new LinearLayout(activity);
        form.setOrientation(LinearLayout.VERTICAL);
        int padding = Math.round(18 * activity.getResources().getDisplayMetrics().density);
        form.setPadding(padding, 0, padding, 0);
        EditText min = new EditText(activity);
        min.setHint("Minimum (leave empty for none)");
        min.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL);
        EditText max = new EditText(activity);
        max.setHint("Maximum (leave empty for none)");
        max.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL);
        double[] current = thresholds.get(key);
        if (current != null) {
            if (!Double.isNaN(current[0])) min.setText(format(current[0]));
            if (!Double.isNaN(current[1])) max.setText(format(current[1]));
        }
        form.addView(min);
        form.addView(max);
        new MaterialAlertDialogBuilder(activity)
                .setTitle("Thresholds · " + label)
                .setView(form)
                .setNegativeButton("Cancel", null)
                .setPositiveButton("Save", (dialog, which) -> {
                    try {
                        JSONObject bounds = new JSONObject();
                        if (min.getText().toString().trim().isEmpty()) bounds.put("min", JSONObject.NULL);
                        else bounds.put("min", Double.parseDouble(min.getText().toString().trim()));
                        if (max.getText().toString().trim().isEmpty()) bounds.put("max", JSONObject.NULL);
                        else bounds.put("max", Double.parseDouble(max.getText().toString().trim()));
                        JSONObject thresholdsPayload = new JSONObject();
                        thresholdsPayload.put(key, bounds);
                        JSONObject request = new JSONObject();
                        request.put("thresholds", thresholdsPayload);
                        api.updateThresholds(request, new ApiCallback() {
                            @Override public void onSuccess(String json) {
                                thresholds.clear();
                                loadThresholds();
                                loadLatest();
                                toast("Threshold updated.");
                            }
                            @Override public void onFailure(ApiFailure failure) { toast(failure.getMessage()); }
                        });
                    } catch (Exception error) {
                        toast("Enter valid numbers.");
                    }
                })
                .show();
    }

    /**
     * Downloads the research CSV and hands it to the system share sheet.
     *
     * <p>The whole transfer runs on a worker thread. Retrofit delivers {@code onResponse} on the
     * main thread, and reading {@code response.body().byteStream()} there performs socket I/O,
     * which Android aborts with {@code NetworkOnMainThreadException} — that was the
     * {@code FATAL EXCEPTION} behind the reported export crash. The button stays visible; only
     * its work moves off the UI thread. Nothing is reported as saved until the bytes are
     * actually on disk.</p>
     */
    private void exportCsv() {
        TextView exportStatus = screen.findViewById(R.id.export_status);
        com.google.android.material.button.MaterialButton exportButton = screen.findViewById(R.id.export_csv);
        if (exportStatus == null || exportButton == null || !exportButton.isEnabled()) return;

        exportStatus.setTextColor(activity.getColor(R.color.hydroguard_blue));
        exportStatus.setText("Exporting the research CSV…");
        exportButton.setEnabled(false);

        CSV_EXPORT_EXECUTOR.execute(() -> {
            File exported = null;
            String failure = null;
            try {
                Response<ResponseBody> response = RetrofitClient.api().exportResearchCsv().execute();
                if (!response.isSuccessful() || response.body() == null) {
                    failure = response.code() == 403
                            ? "Export requires an administrator account."
                            : "The export could not be downloaded (server replied " + response.code() + ").";
                } else {
                    File external = activity.getExternalFilesDir(null);
                    if (external == null) throw new IOException("External storage is unavailable.");
                    File directory = new File(external, "exports");
                    if (!directory.exists() && !directory.mkdirs()) {
                        throw new IOException("Could not create the export folder.");
                    }
                    File file = new File(directory, "hydroguard-export-" + System.currentTimeMillis() + ".csv");
                    try (InputStream input = response.body().byteStream();
                         OutputStream output = new FileOutputStream(file)) {
                        byte[] buffer = new byte[8192];
                        int read;
                        while ((read = input.read(buffer)) != -1) output.write(buffer, 0, read);
                    }
                    if (!file.isFile() || file.length() == 0L) {
                        // Never claim an export that contains nothing.
                        //noinspection ResultOfMethodCallIgnored
                        file.delete();
                        throw new IOException("The server returned an empty export.");
                    }
                    exported = file;
                }
            } catch (IOException | RuntimeException error) {
                if (failure == null) failure = "The export could not be saved on this device.";
            }

            final File ready = exported;
            final String problem = failure;
            activity.runOnUiThread(() -> {
                exportButton.setEnabled(true);
                if (problem != null) {
                    exportStatus.setTextColor(activity.getColor(R.color.hydroguard_red));
                    exportStatus.setText(problem);
                    return;
                }
                shareExportedCsv(ready, exportStatus);
            });
        });
    }

    /** Opens the real system chooser over the file that is already on disk. */
    private void shareExportedCsv(File file, TextView exportStatus) {
        try {
            Uri uri = FileProvider.getUriForFile(activity,
                    activity.getPackageName() + ".fileprovider", file);
            Intent share = new Intent(Intent.ACTION_SEND);
            share.setType("text/csv");
            share.putExtra(Intent.EXTRA_STREAM, uri);
            share.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            activity.startActivity(Intent.createChooser(share, "Open or save the CSV export"));
            exportStatus.setTextColor(activity.getColor(R.color.hydroguard_green));
            exportStatus.setText("Export saved · " + file.getName());
        } catch (RuntimeException error) {
            // No installed app can receive a CSV (or the FileProvider path is
            // unresolvable). Say so instead of crashing the screen.
            exportStatus.setTextColor(activity.getColor(R.color.hydroguard_red));
            exportStatus.setText("No app on this device can open the exported CSV.");
        }
    }

    private void renderSensorHealth(JSONArray rows) {
        LinearLayout container = screen.findViewById(R.id.sensor_health_container);
        if (container == null) return;
        container.removeAllViews();
        try {
            for (int i = 0; i < rows.length(); i++) {
                JSONObject node = rows.getJSONObject(i);
                View row = LayoutInflater.from(activity).inflate(R.layout.item_metric, container, false);
                ((TextView) row.findViewById(R.id.metric_label)).setText(
                        node.optString("name", node.optString("node_id")) + " · " + node.optString("node_id"));
                ((TextView) row.findViewById(R.id.metric_value)).setText(node.optString("status", "offline"));
                ((TextView) row.findViewById(R.id.metric_threshold)).setText(
                        "Last seen " + lastSeenLabel(node));
                TextView action = row.findViewById(R.id.metric_status);
                action.setText("Set online");
                action.setTextColor(activity.getColor(R.color.hydroguard_blue));
                // metric_status is an 11sp label; at its natural height that would be far
                // under the 48dp minimum touch target. It is only clickable here, so the
                // target is restored on this row alone.
                action.setMinHeight(dp(48));
                action.setGravity(android.view.Gravity.CENTER_VERTICAL);
                action.setOnClickListener(view -> api.updateNodeStatus(node.optString("node_id"), "online",
                        new ApiCallback() {
                            @Override public void onSuccess(String json) {
                                Spinner spinner = screen.findViewById(R.id.node_selector);
                                loadNodes(spinner);
                                toast("Sensor marked online.");
                            }
                            @Override public void onFailure(ApiFailure failure) { toast(failure.getMessage()); }
                        }));
                container.addView(row);
            }
        } catch (JSONException ignored) { }
    }

    private boolean isCurrent() {
        return screen != null && screen.isAttachedToWindow();
    }

    private String format(double value) {
        return String.format(Locale.US, value >= 100 ? "%.0f" : "%.2f", value);
    }

    /** Explains a thin range instead of leaving a one-point chart looking broken. */
    private String describeRange(int count) {
        if (count == 0) return "No readings in the selected range.";
        if (count == 1) return "Only 1 reading in this range · choose a wider range for a trend.";
        return count + " readings in range · newest first on the right";
    }

    /**
     * Reads a node's last-seen timestamp safely.
     *
     * <p>{@code optString} turns an explicit JSON {@code null} into the literal text
     * "null", which previously rendered as "Last seen null". A missing or null value
     * becomes "never", and a real timestamp is formatted in local time. The stored
     * value itself is never altered.</p>
     */
    private String lastSeenLabel(JSONObject node) {
        Object raw = node.opt("last_seen");
        if (raw == null || raw == JSONObject.NULL) return "never";
        String value = String.valueOf(raw).trim();
        if (value.isEmpty() || "null".equalsIgnoreCase(value)) return "never";
        String readable = Timestamps.readable(value);
        return "null".equalsIgnoreCase(readable) ? "never" : readable;
    }

    private void toast(String message) {
        android.widget.Toast.makeText(activity, message, android.widget.Toast.LENGTH_LONG).show();
    }

    /** Maps a backend provenance tag onto the compact badge shown to the user. */
    private String getSourceBadge(String source) {
        String normalized = source == null ? "" : source.trim().toUpperCase(Locale.ROOT);
        switch (normalized) {
            case "REAL_SENSOR":
            case "LIVE_SENSOR":
            case "SENSOR":
                return "LIVE SENSOR";
            case "THINGSPEAK":
                return "THINGSPEAK";
            case "SIMULATED_DEVELOPMENT":
            case "SIMULATED":
            case "DEMO":
            case "DEMO_DATA":
                return "DEMO DATA";
            case "HISTORICAL_DATA":
            case "HISTORICAL":
            case "MANUAL":
                return "HISTORICAL DATA";
            default:
                return "UNKNOWN";
        }
    }

    /** True only for provenance tags that represent a physical sensor feed. */
    private boolean isLiveSource(String source) {
        String normalized = source == null ? "" : source.trim().toUpperCase(Locale.ROOT);
        return "REAL_SENSOR".equals(normalized) || "LIVE_SENSOR".equals(normalized) || "SENSOR".equals(normalized) || "THINGSPEAK".equals(normalized);
    }

    private String describeAge(long age) {
        if (age < 60_000L) return "under a minute old";
        if (age < 2 * 3_600_000L) return Math.round(age / 60_000.0) + " minutes old";
        if (age < 48 * 3_600_000L) return Math.round(age / 3_600_000.0) + " hours old";
        return Math.round(age / 86_400_000.0) + " days old";
    }

    private String getNodeFreshness(long readTime, String source) {
        if (readTime <= 0) return "time unknown";
        long age = Math.max(0, System.currentTimeMillis() - readTime);
        if (isLiveSource(source)) {
            if (age < 5 * 60 * 1000L) return "up to date";
            if (age < 30 * 60 * 1000L) return "stale";
            return "no reading for " + Math.round(age / 3_600_000.0) + " hours";
        }
        return describeAge(age);
    }
}
