package com.aistudio.hydroguard.wxqpzx;

import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Typeface;
import android.os.Bundle;
import android.text.InputType;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.Spinner;
import android.widget.TextView;

import androidx.annotation.Nullable;
import androidx.activity.ComponentActivity;
import androidx.lifecycle.ViewModelProvider;

import com.aistudio.hydroguard.wxqpzx.data.api.ApiCallback;
import com.aistudio.hydroguard.wxqpzx.data.api.ApiFailure;
import com.aistudio.hydroguard.wxqpzx.data.api.ApiRepository;
import com.aistudio.hydroguard.wxqpzx.data.repository.DevelopmentAuthPolicy;
import com.aistudio.hydroguard.wxqpzx.data.repository.HydroRepository;
import com.aistudio.hydroguard.wxqpzx.data.service.WaterQualityIndexService;
import com.aistudio.hydroguard.wxqpzx.ui.viewmodel.HydroViewModel;
import com.google.android.material.bottomnavigation.BottomNavigationView;
import com.google.android.material.button.MaterialButton;
import com.google.android.material.card.MaterialCardView;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public class DashboardActivity extends ComponentActivity {
    public static final String EXTRA_ROLE = "role";
    public static final String EXTRA_EMAIL = "email";
    public static final String EXTRA_NAME = "name";
    private static final String[] NODE_IDS = {"node_overhead_a", "node_overhead_b", "node_mess"};
    private static final String[] NODE_NAMES = {"Block A overhead tank", "Block B overhead tank", "Mess ground water"};
    private static final String[] ISSUE_CATEGORIES = {"Water", "Plumbing", "Electrical", "Room/Furniture", "Cleaning", "Bathroom", "Wi-Fi", "Other"};
    private static final String[] ISSUE_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "URGENT"};
    private final ApiRepository api = new ApiRepository();
    private HydroRepository hydro;
    private HydroViewModel viewModel;
    private BottomNavigationView navigation;
    private View activeScreen;
    private String role;
    private String email;
    private String displayName;
    private String selectedNode = NODE_IDS[0];
    private boolean isAdmin;

    @Override protected void onCreate(@Nullable Bundle state) {
        super.onCreate(state);
        role = getIntent().getStringExtra(EXTRA_ROLE);
        email = getIntent().getStringExtra(EXTRA_EMAIL);
        displayName = getIntent().getStringExtra(EXTRA_NAME);
        isAdmin = "ADMIN".equalsIgnoreCase(role);
        if (email == null || email.isEmpty() || !(isAdmin || "STUDENT".equalsIgnoreCase(role))) {
            startActivity(new Intent(this, MainActivity.class));
            finish();
            return;
        }
        viewModel = new ViewModelProvider(this).get(HydroViewModel.class);
        hydro = viewModel.hydro();
        setContentView(R.layout.activity_dashboard);
        navigation = findViewById(R.id.bottom_navigation);
        navigation.inflateMenu(isAdmin ? R.menu.admin_navigation : R.menu.student_navigation);
        int startId = isAdmin ? R.id.nav_water : R.id.nav_home;
        navigation.setSelectedItemId(startId);
        navigation.setOnItemSelectedListener(item -> {
            renderScreen(item.getItemId());
            return true;
        });
        renderScreen(startId);
    }

    private void renderScreen(int screenId) {
        int layout;
        String heading;
        String subtitle;
        if (screenId == R.id.nav_water) {
            layout = R.layout.screen_water;
            heading = isAdmin ? "Water monitoring" : "Water quality";
            subtitle = "Current readings, history, alerts and forecasts";
        } else if (screenId == R.id.nav_home) {
            layout = R.layout.screen_content;
            heading = "Hello, " + safeName();
            subtitle = "Your hostel water and services at a glance";
        } else if (screenId == R.id.nav_report) {
            layout = R.layout.screen_issue_form;
            heading = "Hostel services";
            subtitle = "Report an issue or send feedback";
        } else if (screenId == R.id.nav_issues) {
            layout = R.layout.screen_content;
            heading = "My issues";
            subtitle = "Follow updates to your hostel reports";
        } else if (screenId == R.id.nav_profile) {
            layout = R.layout.screen_content;
            heading = "Profile";
            subtitle = "Your HydroGuard account";
        } else if (screenId == R.id.nav_hostel) {
            layout = R.layout.screen_content;
            heading = "Hostel operations";
            subtitle = "Issues, notices, contacts, lost and found";
        } else {
            layout = R.layout.screen_admin_accounts;
            heading = "Admin management";
            subtitle = "Invite and manage faculty accounts";
        }
        ((TextView) findViewById(R.id.dashboard_heading)).setText(heading);
        ((TextView) findViewById(R.id.dashboard_subtitle)).setText(subtitle);
        LinearLayout host = findViewById(R.id.screen_container);
        host.removeAllViews();
        activeScreen = LayoutInflater.from(this).inflate(layout, host, false);
        host.addView(activeScreen, new ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        if (screenId == R.id.nav_water) renderWater(activeScreen);
        else if (screenId == R.id.nav_home) renderHome(activeScreen);
        else if (screenId == R.id.nav_report) renderIssueForm(activeScreen);
        else if (screenId == R.id.nav_issues) renderIssues(activeScreen, false);
        else if (screenId == R.id.nav_profile) renderProfile(activeScreen);
        else if (screenId == R.id.nav_hostel) renderHostelOps(activeScreen);
        else if (screenId == R.id.nav_accounts) renderAdminAccounts(activeScreen);
    }

    private void renderWater(View screen) {
        Spinner nodes = screen.findViewById(R.id.node_selector);
        nodes.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, NODE_NAMES));
        for (int i = 0; i < NODE_IDS.length; i++) if (NODE_IDS[i].equals(selectedNode)) nodes.setSelection(i);
        nodes.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(android.widget.AdapterView<?> parent, View view, int position, long id) {
                selectedNode = NODE_IDS[position];
                loadWater(screen);
            }
            @Override public void onNothingSelected(android.widget.AdapterView<?> parent) { }
        });
        screen.findViewById(R.id.refresh_water).setOnClickListener(view -> loadWater(screen));
        screen.findViewById(R.id.load_forecast).setOnClickListener(view -> loadForecast(screen));
    }

    private void loadWater(View screen) {
        TextView status = screen.findViewById(R.id.reading_status);
        if (status != null) status.setText("Loading the latest server reading…");
        hydro.loadLatest(selectedNode, new HydroRepository.DataCallback() {
            @Override public void onSuccess(String json, boolean cached, ApiFailure warning) {
                if (activeScreen != screen) return;
                try {
                    JSONObject reading = new JSONObject(json);
                    renderReading(screen, reading, cached, warning);
                } catch (JSONException error) {
                    if (status != null) status.setText("The server returned an unexpected reading.");
                }
            }
            @Override public void onFailure(ApiFailure failure) {
                if (activeScreen == screen && status != null) status.setText(failure.getMessage());
            }
        });
        TextView forecastStatus = screen.findViewById(R.id.forecast_status);
        if (forecastStatus != null) forecastStatus.setText("Loading reading history…");
        hydro.loadHistory(selectedNode, 500, new HydroRepository.DataCallback() {
            @Override public void onSuccess(String json, boolean cached, ApiFailure warning) {
                if (activeScreen != screen) return;
                try {
                    JSONObject history = new JSONObject(json);
                    int count = history.optInt("count", history.optJSONArray("readings") == null ? 0 : history.optJSONArray("readings").length());
                    String label = count + " historical readings" + (cached ? " · saved on this device" : "");
                    if (warning != null && cached) label += "\n" + warning.getMessage();
                    forecastStatus.setText(label);
                } catch (JSONException error) {
                    forecastStatus.setText("Reading history is unavailable.");
                }
            }
            @Override public void onFailure(ApiFailure failure) {
                if (activeScreen == screen) forecastStatus.setText(failure.getMessage());
            }
        });
        api.getAlerts(selectedNode, new ApiCallback() {
            @Override public void onSuccess(String json) { if (activeScreen == screen) renderAlerts(screen, json); }
            @Override public void onFailure(ApiFailure failure) {
                if (activeScreen == screen) renderAlertFailure(screen, failure.getMessage());
            }
        });
    }

    private void renderReading(View screen, JSONObject reading, boolean cached, ApiFailure warning) {
        LinearLayout container = screen.findViewById(R.id.reading_container);
        container.removeAllViews();
        addText(container, NODE_NAMES[nodeIndex(selectedNode)], 17, getColor(R.color.hydroguard_text), true);
        if (cached) addText(container, "Saved reading · " + (warning == null ? "offline" : warning.getMessage()),
                12, getColor(R.color.hydroguard_orange), false);
        float ph = (float) reading.optDouble("ph", 0);
        float tds = (float) reading.optDouble("tds", 0);
        float turbidity = (float) reading.optDouble("turbidity", 0);
        float temperature = (float) reading.optDouble("temperature", 0);
        addMetric(container, "pH", format(ph), WaterQualityIndexService.getParameterStatus("ph", ph));
        addMetric(container, "TDS", format(tds) + " ppm", WaterQualityIndexService.getParameterStatus("tds", tds));
        addMetric(container, "Turbidity", format(turbidity) + " NTU", WaterQualityIndexService.getParameterStatus("turbidity", turbidity));
        addMetric(container, "Temperature", format(temperature) + " °C", WaterQualityIndexService.getParameterStatus("temperature", temperature));
        if (!reading.isNull("optical_colour_index")) {
            addMetric(container, "Optical colour index", format(reading.optDouble("optical_colour_index")) + " · Experimental", "Not used in the application index");
        }
        WaterQualityIndexService.Result index = WaterQualityIndexService.calculate(ph, tds, turbidity, temperature);
        addText(container, "HydroGuard index  " + index.index + "/100 · " + index.category.displayName,
                15, index.index >= 75 ? getColor(R.color.hydroguard_green) : getColor(R.color.hydroguard_orange), true);
        addText(container, "Application indicator only; it is not a drinking-water safety standard.",
                12, getColor(R.color.hydroguard_muted), false);
        addText(container, "Source: " + reading.optString("source", "unknown") + " · " + reading.optString("timestamp", ""),
                12, getColor(R.color.hydroguard_muted), false);
    }

    private void addMetric(LinearLayout parent, String label, String value, String status) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setPadding(0, dp(9), 0, dp(9));
        TextView left = new TextView(this);
        left.setText(label);
        left.setTextColor(getColor(R.color.hydroguard_muted));
        left.setTextSize(14);
        row.addView(left, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        TextView right = new TextView(this);
        right.setText(value + (status.isEmpty() ? "" : "\n" + status));
        right.setGravity(android.view.Gravity.END);
        right.setTextColor(getColor(R.color.hydroguard_text));
        right.setTextSize(14);
        row.addView(right);
        parent.addView(row);
    }

    private void renderAlerts(View screen, String json) {
        LinearLayout alerts = screen.findViewById(R.id.alerts_container);
        alerts.removeAllViews();
        try {
            JSONArray rows = new JSONObject(json).optJSONArray("alerts");
            if (rows == null || rows.length() == 0) {
                addCard(alerts, "No alerts are currently recorded for this node.");
                return;
            }
            for (int i = 0; i < rows.length(); i++) {
                JSONObject row = rows.optJSONObject(i);
                if (row == null) continue;
                String severity = row.optString("severity", "INFO");
                String text = severity + " · " + row.optString("parameter", "Water") + "\n"
                        + row.optString("message", "Water quality alert") + "\nStatus: " + row.optString("status", "ACTIVE");
                addCard(alerts, text);
            }
        } catch (JSONException error) { addCard(alerts, "The server returned an invalid alert list."); }
    }

    private void renderAlertFailure(View screen, String message) {
        LinearLayout alerts = screen.findViewById(R.id.alerts_container);
        alerts.removeAllViews();
        addCard(alerts, message);
    }

    private void loadForecast(View screen) {
        TextView status = screen.findViewById(R.id.forecast_status);
        status.setText("Checking complete reading history and generating a 24-hour forecast…");
        screen.findViewById(R.id.load_forecast).setEnabled(false);
        api.generateForecast(selectedNode, new ApiCallback() {
            @Override public void onSuccess(String json) {
                if (activeScreen != screen) return;
                screen.findViewById(R.id.load_forecast).setEnabled(true);
                try {
                    JSONObject result = new JSONObject(json);
                    JSONObject prediction = result.getJSONObject("prediction");
                    status.setText("24-hour forecast · " + result.optString("forecast_date", "")
                            + "\nData source: " + result.optString("data_source", "unknown")
                            + "\nStrategy: " + result.optString("weight_strategy", "") + " · " + result.optString("weight_status", "")
                            + "\npH " + format(prediction.optDouble("pH"))
                            + " · TDS " + format(prediction.optDouble("TDS")) + " ppm"
                            + "\nTurbidity " + format(prediction.optDouble("turbidity")) + " NTU"
                            + " · Temperature " + format(prediction.optDouble("temperature")) + " °C"
                            + "\nOptical colour index " + format(prediction.optDouble("optical_colour_index")) + " · Experimental");
                } catch (JSONException error) { status.setText("The server returned an invalid forecast."); }
            }
            @Override public void onFailure(ApiFailure failure) {
                if (activeScreen == screen) {
                    screen.findViewById(R.id.load_forecast).setEnabled(true);
                    status.setText(failure.getMessage());
                }
            }
        });
    }

    private void renderHome(View screen) {
        LinearLayout content = screen.findViewById(R.id.content_container);
        addSection(content, "Water status");
        TextView water = addCard(content, "Loading the latest water reading…");
        hydro.loadLatest(NODE_IDS[0], new HydroRepository.DataCallback() {
            @Override public void onSuccess(String json, boolean cached, ApiFailure warning) {
                if (activeScreen != screen) return;
                try {
                    JSONObject reading = new JSONObject(json);
                    water.setText("Block A · pH " + format(reading.optDouble("ph")) + " · TDS "
                            + format(reading.optDouble("tds")) + " ppm · Turbidity " + format(reading.optDouble("turbidity"))
                            + (cached ? "\nSaved on this device while the server is unavailable." : "\nSource: " + reading.optString("source", "unknown")));
                } catch (JSONException error) { water.setText("Reading data is unavailable."); }
            }
            @Override public void onFailure(ApiFailure failure) { if (activeScreen == screen) water.setText(failure.getMessage()); }
        });
        MaterialButton openWater = addButton(content, "View water details and alerts");
        openWater.setOnClickListener(view -> navigation.setSelectedItemId(R.id.nav_water));
        addSection(content, "Notices");
        loadNotices(content, screen, false);
        addSection(content, "Emergency contacts");
        api.getEmergencyContacts(new ApiCallback() {
            @Override public void onSuccess(String json) { if (activeScreen == screen) displayRows(content, json, "name", "phone", "category"); }
            @Override public void onFailure(ApiFailure failure) { if (activeScreen == screen) addCard(content, failure.getMessage()); }
        });
        addSection(content, "Lost and found");
        MaterialButton postLostFound = addButton(content, "Post a lost or found item");
        postLostFound.setOnClickListener(view -> showLostFoundDialog());
        api.getLostFoundItems(new ApiCallback() {
            @Override public void onSuccess(String json) {
                if (activeScreen == screen) displayRows(content, json, "title", "description", "moderation_status");
            }
            @Override public void onFailure(ApiFailure failure) { if (activeScreen == screen) addCard(content, failure.getMessage()); }
        });
        MaterialButton report = addButton(content, "Report a hostel issue");
        report.setOnClickListener(view -> navigation.setSelectedItemId(R.id.nav_report));
        MaterialButton issues = addButton(content, "Follow my issue reports");
        issues.setOnClickListener(view -> navigation.setSelectedItemId(R.id.nav_issues));
    }

    private void renderIssueForm(View screen) {
        Spinner category = screen.findViewById(R.id.issue_category);
        category.setAdapter(adapter(ISSUE_CATEGORIES));
        Spinner severity = screen.findViewById(R.id.issue_severity);
        severity.setAdapter(adapter(ISSUE_SEVERITIES));
        screen.findViewById(R.id.submit_issue).setOnClickListener(button -> {
            EditText location = screen.findViewById(R.id.issue_location);
            EditText description = screen.findViewById(R.id.issue_description);
            String place = location.getText().toString().trim();
            String detail = description.getText().toString().trim();
            TextView result = screen.findViewById(R.id.issue_form_status);
            if (place.length() < 2 || detail.length() < 5) {
                result.setText("Enter a location and a description of at least 5 characters.");
                return;
            }
            result.setText("Submitting your report…");
            api.createIssue(String.valueOf(category.getSelectedItem()), place,
                    String.valueOf(severity.getSelectedItem()), detail, resultCallback(result,
                            "Your report was submitted.", "The report could not be submitted."));
        });
        Spinner feedbackCategory = screen.findViewById(R.id.feedback_category);
        feedbackCategory.setAdapter(adapter(new String[]{"Water", "Cleanliness", "Maintenance", "Wi-Fi", "Common Areas", "Overall Hostel Experience"}));
        Spinner rating = screen.findViewById(R.id.feedback_rating);
        rating.setAdapter(adapter(new String[]{"5 stars", "4 stars", "3 stars", "2 stars", "1 star"}));
        screen.findViewById(R.id.submit_feedback).setOnClickListener(button -> {
            String comment = ((EditText) screen.findViewById(R.id.feedback_comment)).getText().toString();
            int stars = 5 - rating.getSelectedItemPosition();
            TextView result = screen.findViewById(R.id.feedback_status);
            result.setText("Sending feedback…");
            api.submitHostelFeedback(String.valueOf(feedbackCategory.getSelectedItem()), stars,
                    comment, resultCallback(result, "Thank you for your feedback.", "Feedback could not be sent."));
        });
    }

    private void renderIssues(View screen, boolean admin) {
        LinearLayout content = screen.findViewById(R.id.content_container);
        TextView loading = addCard(content, "Loading issue reports…");
        api.getIssues(new ApiCallback() {
            @Override public void onSuccess(String json) {
                if (activeScreen != screen) return;
                content.removeView(loading);
                try {
                    JSONArray rows = new JSONArray(json);
                    if (rows.length() == 0) addCard(content, "No issue reports are recorded yet.");
                    for (int i = 0; i < rows.length(); i++) {
                        JSONObject item = rows.getJSONObject(i);
                        displayIssue(content, item, admin);
                    }
                } catch (JSONException error) { addCard(content, "The server returned an invalid issue list."); }
            }
            @Override public void onFailure(ApiFailure failure) {
                if (activeScreen == screen) { loading.setText(failure.getMessage()); }
            }
        });
    }

    private void displayIssue(LinearLayout content, JSONObject item, boolean admin) {
        String id = item.optString("id", "");
        String status = item.optString("status", "SUBMITTED");
        LinearLayout card = cardContent(content);
        addText(card, item.optString("category", "Issue") + " · " + item.optString("severity", "MEDIUM"),
                15, getColor(R.color.hydroguard_text), true);
        addText(card, item.optString("location", "") + " · " + status, 13, getColor(R.color.hydroguard_blue), true);
        addText(card, item.optString("description", ""), 14, getColor(R.color.hydroguard_text), false);
        addText(card, item.optString("created_at", ""), 12, getColor(R.color.hydroguard_muted), false);
        if (admin) {
            String next = nextIssueStatus(status);
            if (next != null) {
                MaterialButton action = new MaterialButton(this);
                action.setText("Move to " + next.replace('_', ' '));
                action.setAllCaps(false);
                card.addView(action);
                action.setOnClickListener(view -> {
                    String resolution = null;
                    if ("RESOLVED".equals(next)) {
                        EditText input = new EditText(this);
                        input.setHint("Resolution summary");
                        new AlertDialog.Builder(this).setTitle("Resolve issue")
                                .setView(input).setNegativeButton("Cancel", null)
                                .setPositiveButton("Save", (dialog, which) -> api.updateIssueStatus(id, next,
                                        input.getText().toString(), actionResult(action, "Issue updated.")))
                                .show();
                    } else {
                        api.updateIssueStatus(id, next, resolution, actionResult(action, "Issue updated."));
                    }
                });
            } else if ("RESOLVED".equals(status)) {
                MaterialButton close = new MaterialButton(this);
                close.setText("Close issue"); close.setAllCaps(false); card.addView(close);
                close.setOnClickListener(view -> api.updateIssueStatus(id, "CLOSED", null, actionResult(close, "Issue closed.")));
            }
        } else if ("RESOLVED".equals(status) || "CLOSED".equals(status)) {
            MaterialButton timeline = new MaterialButton(this);
            timeline.setText("View update timeline"); timeline.setAllCaps(false); card.addView(timeline);
            timeline.setOnClickListener(view -> api.getIssueTimeline(id, new ApiCallback() {
                @Override public void onSuccess(String json) {
                    try {
                        JSONArray events = new JSONArray(json);
                        StringBuilder text = new StringBuilder();
                        for (int i = 0; i < events.length(); i++) {
                            JSONObject event = events.getJSONObject(i);
                            text.append(event.optString("created_at", "")).append(" · ")
                                    .append(event.optString("to_status", "")).append("\n")
                                    .append(event.optString("comment", "")).append("\n\n");
                        }
                        new AlertDialog.Builder(DashboardActivity.this).setTitle("Issue timeline")
                                .setMessage(text.length() == 0 ? "No updates are available." : text.toString())
                                .setPositiveButton("Close", null).show();
                    } catch (JSONException error) { showToast("The issue timeline is unavailable."); }
                }
                @Override public void onFailure(ApiFailure failure) { showToast(failure.getMessage()); }
            }));
            MaterialButton feedback = new MaterialButton(this);
            feedback.setText("Rate this resolution"); feedback.setAllCaps(false); card.addView(feedback);
            feedback.setOnClickListener(view -> showResolutionDialog(id));
            MaterialButton reopen = new MaterialButton(this);
            reopen.setText("Reopen issue"); reopen.setAllCaps(false); card.addView(reopen);
            reopen.setOnClickListener(view -> showReopenDialog(id, reopen));
        }
    }

    private String nextIssueStatus(String status) {
        switch (status) {
            case "SUBMITTED": return "ACKNOWLEDGED";
            case "ACKNOWLEDGED": case "ASSIGNED": case "REOPENED": return "IN_PROGRESS";
            case "IN_PROGRESS": return "RESOLVED";
            default: return null;
        }
    }

    private void showResolutionDialog(String issueId) {
        LinearLayout form = new LinearLayout(this);
        form.setPadding(dp(18), 0, dp(18), 0);
        form.setOrientation(LinearLayout.VERTICAL);
        Spinner stars = new Spinner(this);
        stars.setAdapter(adapter(new String[]{"5 stars", "4 stars", "3 stars", "2 stars", "1 star"}));
        EditText comment = new EditText(this);
        comment.setHint("Comment (optional)");
        form.addView(stars); form.addView(comment);
        new AlertDialog.Builder(this).setTitle("Rate the resolution").setView(form)
                .setNegativeButton("Cancel", null)
                .setPositiveButton("Submit", (dialog, which) -> api.submitResolutionFeedback(issueId,
                        5 - stars.getSelectedItemPosition(), comment.getText().toString(), simpleResult("Feedback submitted.")))
                .show();
    }

    private void showReopenDialog(String issueId, View button) {
        EditText reason = new EditText(this);
        reason.setHint("Why does the issue need more work?");
        new AlertDialog.Builder(this).setTitle("Reopen issue").setView(reason)
                .setNegativeButton("Cancel", null)
                .setPositiveButton("Reopen", (dialog, which) -> {
                    if (reason.getText().toString().trim().length() < 5) {
                        showToast("Please enter at least 5 characters."); return;
                    }
                    api.reopenIssue(issueId, reason.getText().toString(), actionResult(button, "Issue reopened."));
                }).show();
    }

    private void renderProfile(View screen) {
        LinearLayout content = screen.findViewById(R.id.content_container);
        addSection(content, displayName == null || displayName.isEmpty() ? "HydroGuard account" : displayName);
        addCard(content, email + "\nRole: " + (isAdmin ? "Administrator" : "Student")
                + "\nYour permissions are checked by the HydroGuard backend.");
        if (!isAdmin) {
            MaterialButton water = addButton(content, "Water monitoring");
            water.setOnClickListener(view -> navigation.setSelectedItemId(R.id.nav_water));
            MaterialButton issues = addButton(content, "My hostel issues");
            issues.setOnClickListener(view -> navigation.setSelectedItemId(R.id.nav_issues));
        }
        MaterialButton signOut = addButton(content, "Sign out");
        signOut.setOnClickListener(view -> signOut());
    }

    private void renderHostelOps(View screen) {
        LinearLayout content = screen.findViewById(R.id.content_container);
        addSection(content, "Issue overview");
        TextView summary = addCard(content, "Loading issue summary…");
        api.getIssueSummary(new ApiCallback() {
            @Override public void onSuccess(String json) {
                if (activeScreen == screen) {
                    try { summary.setText(formatSummary(new JSONObject(json))); }
                    catch (JSONException error) { summary.setText("The issue summary is unavailable."); }
                }
            }
            @Override public void onFailure(ApiFailure failure) { if (activeScreen == screen) summary.setText(failure.getMessage()); }
        });
        addSection(content, "Reports and workflow");
        TextView issueLoad = addCard(content, "Loading issues…");
        api.getIssues(new ApiCallback() {
            @Override public void onSuccess(String json) {
                if (activeScreen != screen) return;
                content.removeView(issueLoad);
                try {
                    JSONArray rows = new JSONArray(json);
                    if (rows.length() == 0) addCard(content, "No reports need attention.");
                    for (int i = 0; i < rows.length(); i++) displayIssue(content, rows.getJSONObject(i), true);
                } catch (JSONException error) { addCard(content, "The server returned an invalid issue list."); }
            }
            @Override public void onFailure(ApiFailure failure) { if (activeScreen == screen) issueLoad.setText(failure.getMessage()); }
        });
        addSection(content, "Notices");
        MaterialButton newNotice = addButton(content, "Create a notice");
        newNotice.setOnClickListener(view -> showNoticeDialog());
        loadNotices(content, screen, true);
        addSection(content, "Emergency contacts");
        MaterialButton newContact = addButton(content, "Add an emergency contact");
        newContact.setOnClickListener(view -> showContactDialog());
        api.getEmergencyContacts(new ApiCallback() {
            @Override public void onSuccess(String json) {
                if (activeScreen != screen) return;
                renderContactsAdmin(content, json);
            }
            @Override public void onFailure(ApiFailure failure) { if (activeScreen == screen) addCard(content, failure.getMessage()); }
        });
        addSection(content, "Lost and found moderation");
        api.getLostFoundItems(new ApiCallback() {
            @Override public void onSuccess(String json) { if (activeScreen == screen) renderLostFoundAdmin(content, json); }
            @Override public void onFailure(ApiFailure failure) { if (activeScreen == screen) addCard(content, failure.getMessage()); }
        });
        addSection(content, "Hostel feedback");
        api.getAdminFeedback(new ApiCallback() {
            @Override public void onSuccess(String json) { if (activeScreen == screen) displayRows(content, json, "category", "comment", "rating"); }
            @Override public void onFailure(ApiFailure failure) { if (activeScreen == screen) addCard(content, failure.getMessage()); }
        });
        api.getResolutionFeedback(new ApiCallback() {
            @Override public void onSuccess(String json) { if (activeScreen == screen) displayRows(content, json, "issue_id", "comment", "stars"); }
            @Override public void onFailure(ApiFailure failure) { if (activeScreen == screen) addCard(content, failure.getMessage()); }
        });
    }

    private String formatSummary(JSONObject json) {
        JSONObject status = json.optJSONObject("by_status");
        if (status == null) status = new JSONObject();
        return "Total reports: " + json.optInt("total") + "\nSubmitted: " + status.optInt("SUBMITTED")
                + " · Acknowledged: " + status.optInt("ACKNOWLEDGED")
                + " · In progress: " + status.optInt("IN_PROGRESS")
                + " · Resolved: " + status.optInt("RESOLVED")
                + " · Closed: " + status.optInt("CLOSED");
    }

    private void loadNotices(LinearLayout content, View screen, boolean admin) {
        api.getNotices(new ApiCallback() {
            @Override public void onSuccess(String json) {
                if (activeScreen != screen) return;
                int before = content.getChildCount();
                displayRows(content, json, "title", "body", "priority");
                if (admin) addNoticeDeleteActions(content, json, before);
            }
            @Override public void onFailure(ApiFailure failure) { if (activeScreen == screen) addCard(content, failure.getMessage()); }
        });
    }

    private void renderLostFoundAdmin(LinearLayout content, String json) {
        try {
            JSONArray rows = new JSONArray(json);
            if (rows.length() == 0) { addCard(content, "No items are waiting for moderation."); return; }
            for (int i = 0; i < rows.length(); i++) {
                JSONObject item = rows.getJSONObject(i);
                LinearLayout card = cardContent(content);
                addText(card, item.optString("kind", "Item") + " · " + item.optString("title", ""), 15, getColor(R.color.hydroguard_text), true);
                addText(card, item.optString("description", "") + "\n" + item.optString("location", ""), 13, getColor(R.color.hydroguard_muted), false);
                String id = item.optString("id", "");
                MaterialButton approve = new MaterialButton(this); approve.setText("Approve"); approve.setAllCaps(false); card.addView(approve);
                approve.setOnClickListener(view -> api.moderateLostFound(id, "APPROVED", actionResult(approve, "Item approved.")));
                MaterialButton reject = new MaterialButton(this); reject.setText("Reject"); reject.setAllCaps(false); card.addView(reject);
                reject.setOnClickListener(view -> api.moderateLostFound(id, "REJECTED", actionResult(reject, "Item rejected.")));
            }
        } catch (JSONException error) { addCard(content, "The server returned an invalid Lost & Found list."); }
    }

    private void renderContactsAdmin(LinearLayout content, String json) {
        try {
            JSONArray rows = new JSONArray(json);
            if (rows.length() == 0) { addCard(content, "No active emergency contacts are configured."); return; }
            for (int i = 0; i < rows.length(); i++) {
                JSONObject row = rows.getJSONObject(i);
                LinearLayout card = cardContent(content);
                addText(card, row.optString("name", "") + " · " + row.optString("category", ""),
                        15, getColor(R.color.hydroguard_text), true);
                addText(card, row.optString("phone", "") + "\n" + row.optString("details", "")
                                + "\n" + (row.optBoolean("verified") ? "Verified for students" : "Not yet visible to students"),
                        13, getColor(R.color.hydroguard_muted), false);
                int id = row.optInt("id");
                if (!row.optBoolean("verified")) {
                    MaterialButton verify = new MaterialButton(this);
                    verify.setText("Verify for students"); verify.setAllCaps(false); card.addView(verify);
                    verify.setOnClickListener(view -> api.updateEmergencyContact(id,
                            row.optString("category"), row.optString("name"), row.optString("phone"),
                            row.optString("details", ""), true, true, actionResult(verify, "Contact verified.")));
                }
                MaterialButton deactivate = new MaterialButton(this);
                deactivate.setText("Deactivate contact"); deactivate.setAllCaps(false); card.addView(deactivate);
                deactivate.setOnClickListener(view -> api.deleteEmergencyContact(id, actionResult(deactivate, "Contact deactivated.")));
            }
        } catch (JSONException error) { addCard(content, "The server returned an invalid contact list."); }
    }

    private void addNoticeDeleteActions(LinearLayout content, String json, int firstView) {
        try {
            JSONArray rows = new JSONArray(json);
            int rowIndex = 0;
            for (int i = firstView; i < content.getChildCount() && rowIndex < rows.length(); i++) {
                View view = content.getChildAt(i);
                JSONObject row = rows.getJSONObject(rowIndex++);
                if (view instanceof MaterialCardView) {
                    String idText = row.optString("id", "");
                    TextView delete = new TextView(this);
                    delete.setText("Delete notice"); delete.setTextColor(getColor(R.color.hydroguard_red));
                    if (((ViewGroup) view).getChildAt(0) instanceof ViewGroup) {
                        ((ViewGroup) ((ViewGroup) view).getChildAt(0)).addView(delete);
                    }
                    delete.setOnClickListener(click -> api.deleteNotice(Integer.parseInt(idText), simpleResult("Notice deleted.")));
                }
            }
        } catch (Exception ignored) { }
    }

    private void renderAdminAccounts(View screen) {
        LinearLayout container = screen.findViewById(R.id.admin_accounts_container);
        TextView status = screen.findViewById(R.id.admin_accounts_status);
        screen.findViewById(R.id.invite_admin).setOnClickListener(view -> {
            EditText field = screen.findViewById(R.id.admin_invite_email);
            String address = field.getText().toString().trim();
            if (!android.util.Patterns.EMAIL_ADDRESS.matcher(address).matches()) {
                status.setText("Enter a valid faculty email address."); return;
            }
            status.setText("Adding faculty account…");
            api.inviteAdmin(address, new ApiCallback() {
                @Override public void onSuccess(String json) {
                    if (activeScreen != screen) return;
                    field.setText(""); status.setText("Faculty account added. They can sign in with the invited verified Google account.");
                    loadAdminAccounts(screen, container, status);
                }
                @Override public void onFailure(ApiFailure failure) { if (activeScreen == screen) status.setText(failure.getMessage()); }
            });
        });
        loadAdminAccounts(screen, container, status);
    }

    private void loadAdminAccounts(View screen, LinearLayout container, TextView status) {
        container.removeAllViews();
        status.setText("Loading administrator accounts…");
        api.getAdminUsers(new ApiCallback() {
            @Override public void onSuccess(String json) {
                if (activeScreen != screen) return;
                status.setText("Faculty access is managed by HydroGuard.");
                try {
                    JSONArray rows = new JSONArray(json);
                    if (rows.length() == 0) addCard(container, "No administrator records are available.");
                    for (int i = 0; i < rows.length(); i++) {
                        JSONObject row = rows.getJSONObject(i);
                        LinearLayout card = cardContent(container);
                        String emailValue = row.optString("email", "");
                        String state = row.optString("status", "INVITED");
                        addText(card, emailValue, 15, getColor(R.color.hydroguard_text), true);
                        addText(card, state + (row.optString("firebase_uid", "").isEmpty() ? " · awaiting sign-in" : ""),
                                13, getColor(R.color.hydroguard_muted), false);
                        int id = row.optInt("id");
                        if ("ACTIVE".equals(state) && !email.equalsIgnoreCase(emailValue)) {
                            MaterialButton suspend = new MaterialButton(DashboardActivity.this); suspend.setText("Suspend access"); suspend.setAllCaps(false); card.addView(suspend);
                            suspend.setOnClickListener(view -> changeAdminStatus(id, "SUSPENDED", screen, container, status));
                            MaterialButton revoke = new MaterialButton(DashboardActivity.this); revoke.setText("Revoke access"); revoke.setAllCaps(false); card.addView(revoke);
                            revoke.setOnClickListener(view -> changeAdminStatus(id, "REVOKED", screen, container, status));
                        } else if ("SUSPENDED".equals(state) || "REVOKED".equals(state)) {
                            MaterialButton activate = new MaterialButton(DashboardActivity.this); activate.setText("Restore access"); activate.setAllCaps(false); card.addView(activate);
                            activate.setOnClickListener(view -> changeAdminStatus(id, "ACTIVE", screen, container, status));
                        }
                    }
                } catch (JSONException error) { addCard(container, "The server returned an invalid account list."); }
            }
            @Override public void onFailure(ApiFailure failure) { if (activeScreen == screen) status.setText(failure.getMessage()); }
        });
    }

    private void changeAdminStatus(int id, String state, View screen, LinearLayout container, TextView status) {
        status.setText("Updating faculty access…");
        api.updateAdminStatus(id, state, new ApiCallback() {
            @Override public void onSuccess(String json) { if (activeScreen == screen) { status.setText("Faculty access updated."); loadAdminAccounts(screen, container, status); } }
            @Override public void onFailure(ApiFailure failure) { if (activeScreen == screen) status.setText(failure.getMessage()); }
        });
    }

    private void displayRows(LinearLayout content, String json, String titleKey, String bodyKey, String detailKey) {
        try {
            JSONArray rows = new JSONArray(json);
            if (rows.length() == 0) { addCard(content, "No records are available yet."); return; }
            for (int i = 0; i < rows.length(); i++) {
                JSONObject row = rows.getJSONObject(i);
                addCard(content, value(row, titleKey) + "\n" + value(row, bodyKey)
                        + (detailKey.isEmpty() ? "" : "\n" + value(row, detailKey)));
            }
        } catch (JSONException error) { addCard(content, "The server returned an invalid response."); }
    }

    private String value(JSONObject row, String key) {
        Object value = row.opt(key);
        return value == null || value == JSONObject.NULL ? "" : String.valueOf(value);
    }

    private void showLostFoundDialog() {
        LinearLayout form = dialogForm();
        Spinner kind = new Spinner(this); kind.setAdapter(adapter(new String[]{"LOST", "FOUND"}));
        Spinner category = new Spinner(this); category.setAdapter(adapter(new String[]{"ID", "Keys", "Phone", "Wallet", "Books", "Bag", "Electronics", "Other"}));
        EditText title = input("Item name", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);
        EditText description = input("Description", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        EditText location = input("Last seen location", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);
        form.addView(kind); form.addView(category); form.addView(title); form.addView(description); form.addView(location);
        new AlertDialog.Builder(this).setTitle("Post a lost or found item").setView(form)
                .setNegativeButton("Cancel", null)
                .setPositiveButton("Submit", (dialog, which) -> {
                    if (title.length() < 2 || description.length() < 5 || location.length() < 2) {
                        showToast("Add an item name, description and location."); return;
                    }
                    api.submitLostFound(String.valueOf(kind.getSelectedItem()), title.getText().toString(),
                            description.getText().toString(), String.valueOf(category.getSelectedItem()),
                            location.getText().toString(), utcNow(), simpleResult("Your item is waiting for moderation."));
                }).show();
    }

    private void showNoticeDialog() {
        LinearLayout form = dialogForm();
        EditText title = input("Notice title", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);
        EditText body = input("Notice text", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        Spinner category = new Spinner(this); category.setAdapter(adapter(new String[]{"GENERAL", "MAINTENANCE", "WATER", "EMERGENCY", "EVENT"}));
        Spinner priority = new Spinner(this); priority.setAdapter(adapter(new String[]{"NORMAL", "LOW", "HIGH", "URGENT"}));
        form.addView(title); form.addView(body); form.addView(category); form.addView(priority);
        new AlertDialog.Builder(this).setTitle("Create notice").setView(form).setNegativeButton("Cancel", null)
                .setPositiveButton("Publish", (dialog, which) -> {
                    api.createNotice(title.getText().toString(), body.getText().toString(),
                            String.valueOf(category.getSelectedItem()), String.valueOf(priority.getSelectedItem()),
                            simpleResult("Notice published."));
                }).show();
    }

    private void showContactDialog() {
        LinearLayout form = dialogForm();
        Spinner category = new Spinner(this); category.setAdapter(adapter(new String[]{"WARDEN", "SECURITY"}));
        EditText name = input("Contact name", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_WORDS);
        EditText phone = input("Phone number", InputType.TYPE_CLASS_PHONE);
        EditText details = input("Details (optional)", InputType.TYPE_CLASS_TEXT);
        form.addView(category); form.addView(name); form.addView(phone); form.addView(details);
        new AlertDialog.Builder(this).setTitle("Add emergency contact").setView(form).setNegativeButton("Cancel", null)
                .setPositiveButton("Save", (dialog, which) -> api.createEmergencyContact(
                        String.valueOf(category.getSelectedItem()), name.getText().toString(),
                        phone.getText().toString(), details.getText().toString(),
                        simpleResult("Contact added. It will appear to students when verified."))).show();
    }

    private void signOut() {
        viewModel.logout();
        Intent intent = new Intent(this, MainActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
        startActivity(intent);
        finish();
    }

    private ApiCallback actionResult(View button, String success) {
        return new ApiCallback() {
            @Override public void onSuccess(String json) { showToast(success); button.setEnabled(false); }
            @Override public void onFailure(ApiFailure failure) { showToast(failure.getMessage()); }
        };
    }

    private ApiCallback resultCallback(TextView status, String success, String failureMessage) {
        return new ApiCallback() {
            @Override public void onSuccess(String json) { status.setText(success); }
            @Override public void onFailure(ApiFailure failure) { status.setText(failure.getMessage().isEmpty() ? failureMessage : failure.getMessage()); }
        };
    }

    private ApiCallback simpleResult(String success) {
        return new ApiCallback() {
            @Override public void onSuccess(String json) { showToast(success); }
            @Override public void onFailure(ApiFailure failure) { showToast(failure.getMessage()); }
        };
    }

    private LinearLayout dialogForm() {
        LinearLayout form = new LinearLayout(this);
        form.setPadding(dp(18), 0, dp(18), 0);
        form.setOrientation(LinearLayout.VERTICAL);
        return form;
    }

    private EditText input(String hint, int type) {
        EditText field = new EditText(this);
        field.setHint(hint); field.setInputType(type); field.setMinHeight(dp(48));
        return field;
    }

    private LinearLayout cardContent(LinearLayout parent) {
        MaterialCardView card = new MaterialCardView(this);
        card.setRadius(dp(16)); card.setCardElevation(dp(1));
        LinearLayout.LayoutParams cardParams = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        cardParams.setMargins(0, dp(5), 0, dp(7));
        parent.addView(card, cardParams);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL); content.setPadding(dp(15), dp(12), dp(15), dp(12));
        card.addView(content);
        return content;
    }

    private TextView addCard(LinearLayout parent, String text) {
        LinearLayout content = cardContent(parent);
        return addText(content, text, 14, getColor(R.color.hydroguard_text), false);
    }

    private TextView addText(LinearLayout parent, String text, int size, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(text); view.setTextSize(size); view.setTextColor(color);
        if (bold) view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        view.setPadding(0, dp(3), 0, dp(3));
        parent.addView(view, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        return view;
    }

    private void addSection(LinearLayout parent, String title) {
        addText(parent, title, 18, getColor(R.color.hydroguard_text), true);
    }

    private MaterialButton addButton(LinearLayout parent, String label) {
        MaterialButton button = new MaterialButton(this);
        button.setText(label); button.setAllCaps(false);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(48));
        params.setMargins(0, dp(4), 0, dp(4));
        parent.addView(button, params);
        return button;
    }

    private ArrayAdapter<String> adapter(String[] values) {
        ArrayAdapter<String> adapter = new ArrayAdapter<>(this, android.R.layout.simple_spinner_item, values);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        return adapter;
    }

    private int nodeIndex(String id) {
        for (int i = 0; i < NODE_IDS.length; i++) if (NODE_IDS[i].equals(id)) return i;
        return 0;
    }

    private String safeName() {
        if (displayName == null || displayName.trim().isEmpty()) return isAdmin ? "Admin" : "there";
        int separator = displayName.indexOf(' ');
        return separator > 0 ? displayName.substring(0, separator) : displayName;
    }

    private String format(double value) { return String.format(Locale.US, "%.2f", value); }
    private int dp(float value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private String utcNow() {
        SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US);
        format.setTimeZone(TimeZone.getTimeZone("UTC"));
        return format.format(new Date());
    }
    private void showToast(String message) { android.widget.Toast.makeText(this, message, android.widget.Toast.LENGTH_LONG).show(); }
}
