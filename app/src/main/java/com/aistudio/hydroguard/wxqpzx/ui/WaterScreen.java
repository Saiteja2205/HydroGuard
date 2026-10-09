package com.aistudio.hydroguard.wxqpzx.ui;

import android.app.Activity;
import android.content.Intent;
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
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

import com.aistudio.hydroguard.wxqpzx.R;
import com.aistudio.hydroguard.wxqpzx.data.api.ApiCallback;
import com.aistudio.hydroguard.wxqpzx.data.api.ApiFailure;
import com.aistudio.hydroguard.wxqpzx.data.api.ApiRepository;
import com.aistudio.hydroguard.wxqpzx.data.api.RetrofitClient;
import com.aistudio.hydroguard.wxqpzx.data.repository.HydroRepository;
import com.aistudio.hydroguard.wxqpzx.data.service.AlertNotifier;
import com.aistudio.hydroguard.wxqpzx.data.service.WaterQualityIndexService;
import com.github.mikephil.charting.charts.LineChart;
import com.github.mikephil.charting.components.Legend;
import com.github.mikephil.charting.data.Entry;
import com.github.mikephil.charting.data.LineData;
import com.github.mikephil.charting.data.LineDataSet;
import com.github.mikephil.charting.formatter.ValueFormatter;
import com.google.android.material.chip.Chip;
import com.google.android.material.chip.ChipGroup;
import com.google.android.material.dialog.MaterialAlertDialogBuilder;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TimeZone;

import okhttp3.ResponseBody;
import retrofit2.Call;
import retrofit2.Response;

/** Owns the water monitoring screen: readings, thresholds, charts, alerts, forecasts and admin actions. */
public class WaterScreen {
    private static final String[][] FALLBACK_NODES = {
            {"node_overhead_a", "Overhead Tank A"},
            {"node_overhead_b", "Overhead Tank B"},
            {"node_mess_ground", "Mess Ground Water"},
    };
    private static final String[] RANGE_LABELS = {"24 hours", "7 days", "30 days", "All"};
    private static final int[] RANGE_DAYS = {1, 7, 30, 0};
    private static final String[][] METRICS = {
            {"ph", "pH", ""},
            {"tds", "TDS", " ppm"},
            {"turbidity", "Turbidity", " NTU"},
            {"temperature", "Temperature", " °C"},
            {"optical_colour_index", "Optical colour index", " · Experimental"},
    };

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
        refresh.setOnRefreshListener(() -> {
            refreshAll();
            refresh.setRefreshing(false);
        });
        screen.findViewById(R.id.load_forecast).setOnClickListener(view -> loadForecast());
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
        api.getNodes(new ApiCallback() {
            @Override public void onSuccess(String json) {
                try {
                    JSONArray rows = new JSONObject(json).optJSONArray("nodes");
                    if (rows == null || rows.length() == 0) return;
                    List<String> names = new ArrayList<>();
                    List<String> ids = new ArrayList<>();
                    for (int i = 0; i < rows.length(); i++) {
                        JSONObject row = rows.getJSONObject(i);
                        ids.add(row.getString("node_id"));
                        names.add(row.optString("name", row.getString("node_id"))
                                + " · " + row.optString("status", "offline"));
                    }
                    spinner.setTag(ids);
                    applyNodeNames(spinner, names);
                    if (admin) renderSensorHealth(rows);
                    if (screen != spinner.getRootView()) return;
                    for (int i = 0; i < ids.size(); i++) {
                        if (ids.get(i).equals(selectedNode)) {
                            spinner.setSelection(i);
                            break;
                        }
                    }
                } catch (JSONException ignored) { }
            }
            @Override public void onFailure(ApiFailure failure) { /* spinner keeps fallback nodes */ }
        });
        spinner.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(android.widget.AdapterView<?> parent, View view, int position, long id) {
                List<String> ids = (List<String>) parent.getTag();
                selectedNode = ids == null || position >= ids.size()
                        ? FALLBACK_NODES[Math.min(position, FALLBACK_NODES.length - 1)][0]
                        : ids.get(position);
                refreshAll();
            }
            @Override public void onNothingSelected(android.widget.AdapterView<?> parent) { }
        });
    }

    private List<String> fallbackNodeNames() {
        List<String> names = new ArrayList<>();
        List<String> ids = new ArrayList<>();
        for (String[] node : FALLBACK_NODES) {
            names.add(node[1]);
            ids.add(node[0]);
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
            if ("optical_colour_index".equals(metric[0])) continue;
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
        ChipGroup rangeGroup = screen.findViewById(R.id.history_range_group);
        rangeGroup.removeAllViews();
        for (int i = 0; i < RANGE_LABELS.length; i++) {
            Chip chip = new Chip(activity);
            chip.setText(RANGE_LABELS[i]);
            chip.setCheckable(true);
            chip.setChecked(i == selectedRange);
            final int index = i;
            chip.setOnCheckedChangeListener((button, checked) -> {
                if (checked) {
                    selectedRange = index;
                    loadHistory();
                }
            });
            rangeGroup.addView(chip);
        }
    }

    private void refreshAll() {
        loadLatest();
        loadThresholds();
        loadHistory();
        loadAlerts();
    }

    private void loadLatest() {
        TextView status = screen.findViewById(R.id.reading_status);
        status.setText("Loading the latest server reading…");
        hydro.loadLatest(selectedNode, new HydroRepository.DataCallback() {
            @Override public void onSuccess(String json, boolean cached, ApiFailure warning) {
                if (!isCurrent()) return;
                try {
                    renderReading(new JSONObject(json), cached, warning);
                } catch (JSONException error) {
                    status.setText("The server returned an unexpected reading.");
                }
            }
            @Override public void onFailure(ApiFailure failure) {
                if (isCurrent()) status.setText(failure.getMessage());
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
            }
            @Override public void onFailure(ApiFailure failure) { /* metric cards fall back to index status */ }
        });
    }

    private void loadHistory() {
        TextView chartStatus = screen.findViewById(R.id.history_chart_status);
        chartStatus.setText("Loading reading history…");
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
                    chartStatus.setText(history.size() + " readings in range · newest first on the right");
                    renderHistoryChart();
                    renderForecastChart();
                    notifyStale(history.isEmpty() ? 0 : parseTimestamp(history.get(history.size() - 1).optString("timestamp")));
                } catch (JSONException error) {
                    chartStatus.setText("Reading history is unavailable.");
                }
            }
            @Override public void onFailure(ApiFailure failure) {
                if (isCurrent()) chartStatus.setText(failure.getMessage());
            }
        };
        if (RANGE_DAYS[selectedRange] == 0) {
            api.getReadingHistory(selectedNode, 1000, callback);
        } else {
            api.getReadingHistoryRange(selectedNode, start, null, 1000, callback);
        }
    }

    private long parseTimestamp(String iso) {
        try {
            return isoUtc.parse(iso).getTime();
        } catch (Exception error) {
            try {
                return java.time.Instant.parse(iso).toEpochMilli();
            } catch (Exception ignored) {
                return 0;
            }
        }
    }

    private void notifyStale(long newestMillis) {
        if (newestMillis <= 0) return;
        long age = System.currentTimeMillis() - newestMillis;
        if (age > 48 * 3_600_000L) {
            notifier.notifyStaleSensor(selectedNode, newestMillis, 48 * 3_600_000L,
                    Math.round(age / 3_600_000.0) + " hours");
        }
        TextView sensorStatus = screen.findViewById(R.id.sensor_status);
        if (sensorStatus != null && isCurrent()) {
            sensorStatus.setText(age > 48 * 3_600_000L
                    ? "Sensor connection: no reading for " + Math.round(age / 3_600_000.0) + " hours"
                    : "Sensor connection: up to date");
        }
    }

    private void renderReading(JSONObject reading, boolean cached, ApiFailure warning) {
        TextView status = screen.findViewById(R.id.reading_status);
        LinearLayout cards = screen.findViewById(R.id.metric_cards);
        cards.removeAllViews();
        if (cached) {
            status.setText("Saved reading · " + (warning == null ? "offline" : warning.getMessage()));
        } else {
            status.setText("Latest reading · " + reading.optString("timestamp", "")
                    + " · Source: " + reading.optString("source", "unknown")
                    + (warning != null ? "\n" + warning.getMessage() : ""));
        }
        for (String[] metric : METRICS) {
            double value = reading.optDouble(metric[0], Double.NaN);
            if (Double.isNaN(value)) continue;
            View row = LayoutInflater.from(activity).inflate(R.layout.item_metric, cards, false);
            ((TextView) row.findViewById(R.id.metric_label)).setText(metric[1]);
            ((TextView) row.findViewById(R.id.metric_value)).setText(format(value) + metric[2]);
            double[] bounds = thresholds.get(metric[0]);
            TextView thresholdView = row.findViewById(R.id.metric_threshold);
            TextView statusView = row.findViewById(R.id.metric_status);
            if (bounds != null) {
                thresholdView.setText("Acceptable " + describeBounds(bounds));
                String state = stateFor(value, bounds);
                statusView.setText(state);
                statusView.setTextColor(activity.getColor("Within range".equals(state)
                        ? R.color.hydroguard_green : R.color.hydroguard_orange));
            } else {
                thresholdView.setText("");
                statusView.setText(WaterQualityIndexService.getParameterStatus(metric[0], (float) value));
                statusView.setTextColor(activity.getColor(R.color.hydroguard_muted));
            }
            cards.addView(row);
        }
        TextView indexSummary = screen.findViewById(R.id.index_summary);
        indexSummary.setText("HydroGuard index " + WaterQualityIndexService.calculate(
                (float) reading.optDouble("ph", 0), (float) reading.optDouble("tds", 0),
                (float) reading.optDouble("turbidity", 0), (float) reading.optDouble("temperature", 0))
                .index + "/100 · " + WaterQualityIndexService.calculate(
                (float) reading.optDouble("ph", 0), (float) reading.optDouble("tds", 0),
                (float) reading.optDouble("turbidity", 0), (float) reading.optDouble("temperature", 0))
                .category.displayName);
    }

    private String describeBounds(double[] bounds) {
        boolean hasMin = !Double.isNaN(bounds[0]);
        boolean hasMax = !Double.isNaN(bounds[1]);
        if (hasMin && hasMax) return format(bounds[0]) + " – " + format(bounds[1]);
        if (hasMin) return "above " + format(bounds[0]);
        if (hasMax) return "up to " + format(bounds[1]);
        return "not configured";
    }

    private String stateFor(double value, double[] bounds) {
        if (!Double.isNaN(bounds[0]) && value < bounds[0]) return "Below range";
        if (!Double.isNaN(bounds[1]) && value > bounds[1]) return "Above range";
        return "Within range";
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
                    for (JSONObject row : list) notifier.notifyServerAlert(selectedNode, row);
                } catch (JSONException error) {
                    alertsStatus.setText("The server returned an invalid alert list.");
                }
            }
            @Override public void onFailure(ApiFailure failure) {
                if (isCurrent()) alertsStatus.setText(failure.getMessage());
            }
        });
    }

    private void loadForecast() {
        TextView forecastStatus = screen.findViewById(R.id.forecast_status);
        forecastStatus.setText("Checking recent history and generating a 24-hour forecast…");
        screen.findViewById(R.id.load_forecast).setEnabled(false);
        api.generateForecast(selectedNode, new ApiCallback() {
            @Override public void onSuccess(String json) {
                screen.findViewById(R.id.load_forecast).setEnabled(true);
                if (!isCurrent()) return;
                try {
                    latestForecast = new JSONObject(json);
                    JSONObject prediction = latestForecast.getJSONObject("prediction");
                    forecastStatus.setText("Forecast for " + latestForecast.optString("forecast_date", "")
                            + "\nModels: LSTM, PatchTST, TimeMixer with adaptive ensemble"
                            + "\nStrategy: " + latestForecast.optString("weight_strategy", "")
                            + " · " + latestForecast.optString("weight_status", "")
                            + "\nGenerated " + latestForecast.optString("generated_at", "just now")
                            + "\npH " + format(prediction.optDouble("pH"))
                            + " · TDS " + format(prediction.optDouble("TDS")) + " ppm"
                            + " · Turbidity " + format(prediction.optDouble("turbidity")) + " NTU"
                            + " · Temperature " + format(prediction.optDouble("temperature")) + " °C");
                    screen.findViewById(R.id.forecast_chart_card).setVisibility(View.VISIBLE);
                    renderForecastChart();
                } catch (JSONException error) {
                    forecastStatus.setText("The server returned an invalid forecast.");
                }
            }

            @Override public void onFailure(ApiFailure failure) {
                screen.findViewById(R.id.load_forecast).setEnabled(true);
                if (isCurrent()) forecastStatus.setText(failure.getMessage());
            }
        });
    }

    private void renderHistoryChart() {
        LineChart chart = screen.findViewById(R.id.history_chart);
        List<Entry> entries = new ArrayList<>();
        List<String> labels = new ArrayList<>();
        int index = 0;
        for (JSONObject row : history) {
            double value = row.optDouble(selectedMetric, Double.NaN);
            if (Double.isNaN(value)) continue;
            entries.add(new Entry(index++, (float) value));
            labels.add(shortDate(row.optString("timestamp", "")));
        }
        if (entries.isEmpty()) {
            chart.clear();
            return;
        }
        chart.setData(buildData(entries, labels, "Observed", activity.getColor(R.color.hydroguard_blue), false));
        styleChart(chart);
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
        List<Entry> entries = new ArrayList<>();
        List<String> labels = new ArrayList<>();
        int shown = 0;
        int start = Math.max(0, history.size() - 15);
        for (int i = start; i < history.size(); i++) {
            double metricValue = history.get(i).optDouble(selectedMetric, Double.NaN);
            if (Double.isNaN(metricValue)) continue;
            entries.add(new Entry(shown++, (float) metricValue));
            labels.add(shortDate(history.get(i).optString("timestamp", "")));
        }
        if (entries.isEmpty()) return;
        entries.add(new Entry(shown, (float) value));
        labels.add("Forecast");
        chart.setData(buildData(entries, labels, "Observed + forecast",
                activity.getColor(R.color.hydroguard_blue), true));
        styleChart(chart);
    }

    private LineData buildData(List<Entry> entries, List<String> labels, String name, int color, boolean showLast) {
        LineDataSet set = new LineDataSet(entries, name);
        set.setColor(color);
        set.setCircleColor(color);
        set.setCircleRadius(2.5f);
        set.setDrawValues(false);
        set.setLineWidth(2f);
        LineData data = new LineData(set);
        data.setValueFormatter(new ValueFormatter() {
            @Override public String getPointLabel(Entry entry) {
                int i = (int) entry.getX();
                return i < labels.size() ? labels.get(i) : "";
            }
        });
        return data;
    }

    private void styleChart(LineChart chart) {
        chart.getDescription().setEnabled(false);
        chart.getLegend().setEnabled(true);
        chart.getLegend().setVerticalAlignment(Legend.LegendVerticalAlignment.BOTTOM);
        chart.getXAxis().setDrawGridLines(false);
        chart.getXAxis().setDrawLabels(false);
        chart.getAxisRight().setEnabled(false);
        chart.setScaleEnabled(false);
        chart.setTouchEnabled(false);
        chart.notifyDataSetChanged();
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

    private void exportCsv() {
        TextView exportStatus = screen.findViewById(R.id.export_status);
        exportStatus.setText("Exporting the research CSV…");
        ((com.google.android.material.button.MaterialButton) screen.findViewById(R.id.export_csv)).setEnabled(false);
        RetrofitClient.api().exportResearchCsv().enqueue(new retrofit2.Callback<ResponseBody>() {
            @Override public void onResponse(Call<ResponseBody> call, Response<ResponseBody> response) {
                ((com.google.android.material.button.MaterialButton) screen.findViewById(R.id.export_csv)).setEnabled(true);
                if (!response.isSuccessful() || response.body() == null) {
                    exportStatus.setText(response.code() == 403
                            ? "Export requires an administrator account."
                            : "The export could not be downloaded.");
                    return;
                }
                try (InputStream input = response.body().byteStream()) {
                    File directory = new File(activity.getExternalFilesDir(null), "exports");
                    if (!directory.exists() && !directory.mkdirs()) throw new IOException("Could not create the export folder.");
                    File file = new File(directory, "hydroguard-export-" + System.currentTimeMillis() + ".csv");
                    try (FileOutputStream output = new FileOutputStream(file)) {
                        byte[] buffer = new byte[8192];
                        int read;
                        while ((read = input.read(buffer)) != -1) output.write(buffer, 0, read);
                    }
                    Uri uri = FileProvider.getUriForFile(activity,
                            activity.getPackageName() + ".fileprovider", file);
                    Intent share = new Intent(Intent.ACTION_SEND);
                    share.setType("text/csv");
                    share.putExtra(Intent.EXTRA_STREAM, uri);
                    share.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    activity.startActivity(Intent.createChooser(share, "Open or save the CSV export"));
                    exportStatus.setText("Export saved · " + file.getName());
                } catch (IOException error) {
                    exportStatus.setText("The export could not be saved on this device.");
                }
            }

            @Override public void onFailure(Call<ResponseBody> call, Throwable error) {
                ((com.google.android.material.button.MaterialButton) screen.findViewById(R.id.export_csv)).setEnabled(true);
                exportStatus.setText("The export server is unreachable.");
            }
        });
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
                        "Last seen " + (node.optString("last_seen", "").isEmpty() ? "never" : node.optString("last_seen")));
                TextView action = row.findViewById(R.id.metric_status);
                action.setText("Set online");
                action.setTextColor(activity.getColor(R.color.hydroguard_blue));
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

    private void toast(String message) {
        android.widget.Toast.makeText(activity, message, android.widget.Toast.LENGTH_LONG).show();
    }
}
