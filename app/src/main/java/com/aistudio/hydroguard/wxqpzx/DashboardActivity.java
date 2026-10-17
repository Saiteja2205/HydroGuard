package com.aistudio.hydroguard.wxqpzx;

import android.app.AlertDialog;
import android.content.Intent;
import android.content.res.ColorStateList;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Matrix;
import android.graphics.Typeface;
import android.media.ExifInterface;
import android.net.Uri;
import android.os.Bundle;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewParent;
import android.view.ViewTreeObserver;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;

import androidx.annotation.Nullable;
import androidx.activity.ComponentActivity;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.core.content.res.ResourcesCompat;
import androidx.lifecycle.ViewModelProvider;

import com.aistudio.hydroguard.wxqpzx.data.api.ApiCallback;
import com.aistudio.hydroguard.wxqpzx.data.api.ApiFailure;
import com.aistudio.hydroguard.wxqpzx.data.api.ApiRepository;
import com.aistudio.hydroguard.wxqpzx.data.api.LostFoundPhotos;
import com.aistudio.hydroguard.wxqpzx.data.api.ServerLink;
import com.aistudio.hydroguard.wxqpzx.data.config.HostelConfig;
import com.aistudio.hydroguard.wxqpzx.data.config.IssueWorkflow;
import com.aistudio.hydroguard.wxqpzx.data.repository.DevelopmentAuthPolicy;
import com.aistudio.hydroguard.wxqpzx.data.repository.HydroRepository;
import com.aistudio.hydroguard.wxqpzx.data.service.AlertNotifier;
import com.aistudio.hydroguard.wxqpzx.ui.AlertCountListener;
import com.aistudio.hydroguard.wxqpzx.ui.Timestamps;
import com.aistudio.hydroguard.wxqpzx.ui.WaterScreen;
import com.aistudio.hydroguard.wxqpzx.ui.viewmodel.HydroViewModel;
import com.google.android.material.bottomnavigation.BottomNavigationView;
import com.google.android.material.button.MaterialButton;
import com.google.android.material.card.MaterialCardView;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.TimeZone;

public class DashboardActivity extends ComponentActivity implements AlertCountListener {
    public static final String EXTRA_ROLE = "role";
    public static final String EXTRA_EMAIL = "email";
    public static final String EXTRA_NAME = "name";
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
    private String selectedNode = HostelConfig.primaryTankNodeId();
    private boolean isAdmin;
    private AlertNotifier alertNotifier;
    private WaterScreen waterScreen;
    // Navy top application bar children, bound once in onCreate.
    private View topBarLink;
    private ImageView topBarLinkIcon;
    private TextView topBarLinkState;
    private TextView topBarAlertBadge;

    @Override protected void onCreate(@Nullable Bundle state) {
        super.onCreate(state);
        role = getIntent().getStringExtra(EXTRA_ROLE);
        email = getIntent().getStringExtra(EXTRA_EMAIL);
        displayName = getIntent().getStringExtra(EXTRA_NAME);
        viewModel = new ViewModelProvider(this).get(HydroViewModel.class);
        if (!viewModel.hasActiveSession()) {
            // No live session (process restored after sign-out or a rejected demo
            // identity): protected screens must fall back to the login screen.
            startActivity(new Intent(this, MainActivity.class));
            finish();
            return;
        }
        // Privileged controls must render from the backend-verified role, not from
        // the Intent extra, which is untrusted and can outlive the session that
        // produced it. A null verified role means this process never completed an
        // authenticated sign-in, so the user is sent back to the login screen.
        String verifiedRole = viewModel.currentRole();
        if (verifiedRole == null) {
            startActivity(new Intent(this, MainActivity.class));
            finish();
            return;
        }
        role = verifiedRole;
        isAdmin = "ADMIN".equalsIgnoreCase(role);
        if (email == null || email.trim().isEmpty()) {
            startActivity(new Intent(this, MainActivity.class));
            finish();
            return;
        }
        hydro = viewModel.hydro();
        alertNotifier = new AlertNotifier(this);
        requestNotificationPermissionIfNeeded();
        setContentView(R.layout.activity_dashboard);
        // targetSdk 36 draws edge-to-edge. The navy bar absorbs the status-bar and cutout
        // inset itself so its background runs behind the clock, which is what "direct edge
        // integration with the Android Status Bar" requires and what android:statusBarColor
        // can no longer do. Every other child is padded clear of the bars as before.
        View topBar = findViewById(R.id.top_app_bar);
        com.aistudio.hydroguard.wxqpzx.ui.SystemInsets.applyForTopBar(this, topBar);
        wireTopBar(topBar);
        navigation = findViewById(R.id.bottom_navigation);
        navigation.inflateMenu(isAdmin ? R.menu.admin_navigation : R.menu.student_navigation);
        int startId = isAdmin ? R.id.nav_water : R.id.nav_home;
        navigation.setSelectedItemId(startId);
        navigation.setOnItemSelectedListener(item -> {
            renderScreen(item.getItemId());
            return true;
        });
        // Adopt the backend's authoritative transition graph before rendering
        // screens, so every "next action" button offered to an administrator is
        // one the PATCH endpoint will actually accept.
        api.getIssueWorkflow(new ApiCallback() {
            @Override public void onSuccess(String json) { IssueWorkflow.applyServerJson(json); }
            @Override public void onFailure(ApiFailure failure) { /* built-in defaults remain */ }
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
        FrameLayout host = findViewById(R.id.screen_container);
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
        waterScreen = new WaterScreen(this, api, hydro, alertNotifier, isAdmin, selectedNode);
        waterScreen.attach(screen);
    }

    /** Binds the navy top application bar: link state, alerts action and alerts badge. */
    private void wireTopBar(View topBar) {
        topBarLink = topBar.findViewById(R.id.top_bar_link);
        topBarLinkIcon = topBar.findViewById(R.id.top_bar_link_icon);
        topBarLinkState = topBar.findViewById(R.id.top_bar_link_state);
        topBarAlertBadge = topBar.findViewById(R.id.top_bar_alert_badge);

        // UNKNOWN means no request has settled yet, so there is nothing true to display and
        // the indicator stays hidden rather than guessing a connection state.
        ServerLink.State known = ServerLink.current();
        if (known == ServerLink.State.UNKNOWN) {
            topBarLink.setVisibility(View.GONE);
        } else {
            renderServerLink(known);
        }
        ServerLink.setListener(this::renderServerLink);

        topBar.findViewById(R.id.top_bar_alerts).setOnClickListener(v -> openAlerts());
    }

    private void renderServerLink(ServerLink.State state) {
        if (topBarLink == null || topBarLinkState == null) return;
        if (state == ServerLink.State.UNKNOWN) {
            topBarLink.setVisibility(View.GONE);
            return;
        }
        topBarLink.setVisibility(View.VISIBLE);
        boolean reachable = state == ServerLink.State.REACHABLE;
        topBarLinkState.setText(reachable ? "ONLINE" : "OFFLINE");
        int colour = getColor(reachable ? R.color.hydroguard_link_on : R.color.hydroguard_link_off);
        topBarLinkState.setTextColor(colour);
        topBarLinkIcon.setColorFilter(colour);
    }

    /**
     * The bell opens the alerts that actually exist: they are listed on the Water screen, so it
     * navigates there and scrolls the alert section into view. This app has no separate alerts
     * destination, and the badge is fed by that same list, so pointing anywhere else would show
     * a count the user could not then read.
     */
    private void openAlerts() {
        if (navigation == null) return;
        // renderScreen() rebuilds the entire screen, so re-selecting a tab that is already
        // on display would throw away the current scroll position and refetch every panel
        // for nothing. Only navigate when Water is not the screen already showing.
        if (shouldSwitchToWater(navigation.getSelectedItemId(), R.id.nav_water)) {
            navigation.setSelectedItemId(R.id.nav_water);
        }
        scrollToAlerts(activeScreen);
    }

    /**
     * Whether the bell has to change tabs before it can scroll to the alerts.
     *
     * <p>Returning {@code false} when Water is already on display is what keeps a second tap
     * on the bell from rebuilding the screen: the old code called
     * {@code setSelectedItemId} unconditionally, {@link #renderScreen} removed every view and
     * re-inflated the layout, and the scroll position jumped back to the top.</p>
     *
     * @param selectedItemId the tab currently selected, or 0 if none has been chosen yet.
     * @param waterItemId    the {@code R.id} of the Water tab.
     * @return true when a tab change is needed; false when Water is already showing.
     */
    static boolean shouldSwitchToWater(int selectedItemId, int waterItemId) {
        return selectedItemId != waterItemId;
    }

    /**
     * Scroll offset for bringing the alerts section into view.
     *
     * <p>The heading sits immediately above the list, so the target is pulled back by
     * {@code headingAllowancePx} to keep it on screen. The result is floored at zero: a
     * section near the top of the page must not produce a negative offset, which would ask
     * the scroller to scroll past the start of its content.</p>
     *
     * @param offsetInScroller  distance from the top of the scroller's content to the section.
     * @param headingAllowancePx how much of the area above the section to keep visible, in px.
     * @return the clamped scroll offset, always {@code >= 0}.
     */
    static int alertScrollTarget(int offsetInScroller, int headingAllowancePx) {
        return Math.max(0, offsetInScroller - headingAllowancePx);
    }

    /**
     * Brings the alerts section of the Water screen into view.
     *
     * <p>The alerts sit below the history and forecast sections, well past the fold, so the bell
     * has to perform a real scroll rather than merely switch tabs. Two things make a single
     * scroll insufficient, and both were measured on the device rather than assumed:</p>
     *
     * <ul>
     *   <li>A screen that has just been inflated has no size yet, so every offset it reports is
     *       zero and a scroll taken on the spot is a silent no-op.</li>
     *   <li>The history, forecast and alert panels then arrive and grow the content above the
     *       alerts. On the test device the content went from 2690px to 3891px in under half a
     *       second, pushing the alerts back below the fold while the scroll position itself
     *       stayed exactly where it had been set.</li>
     * </ul>
     *
     * <p>The scroll is therefore applied now if it can be, then re-applied on each layout pass
     * for a short settle window while the panels load. See {@link AlertsScroller} for how it is
     * bounded.</p>
     */
    private void scrollToAlerts(View screen) {
        if (screen == null) return;
        // Only the Water screen carries this view; every other screen has nothing to scroll to.
        View alerts = screen.findViewById(R.id.alerts_status);
        if (alerts == null) return;
        new AlertsScroller(screen, alerts).start();
    }

    /**
     * Scrolls the Water screen to its alerts section, correcting while the page is still growing.
     *
     * <p>It is bounded three separate ways, so arming it cannot become a race:</p>
     *
     * <ul>
     *   <li>every pass re-checks that {@code screen} is still {@link #activeScreen}, so changing
     *       tabs while it is armed stops it at once;</li>
     *   <li>a settle window, backed by a posted runnable, removes the listener shortly after the
     *       tap even if no further layout pass is ever dispatched;</li>
     *   <li>a hard cap on layout passes gives a second, independent stop.</li>
     * </ul>
     *
     * <p>Each pass recomputes the offset from the live layout, so it tracks content growth
     * instead of chasing a stale target. Content height is deliberately NOT used as the stop
     * signal: layout passes arrive in bursts, and on the test device two passes 44ms apart both
     * reported 2690px while the content was still on its way to 3891px, so "height unchanged"
     * ended the correction before the history and forecast panels had landed.</p>
     */
    private final class AlertsScroller implements ViewTreeObserver.OnGlobalLayoutListener {
        /**
         * How long the correction keeps following the layout after the tap.
         *
         * <p>Measured on the test device: the content finished growing at 500ms and was still
         * 3891px at 8s, so this window covers the whole load with margin while staying short
         * enough that the bell cannot keep snapping the page back after the user has moved on.
         */
        private static final long SETTLE_WINDOW_MS = 2500L;
        /** Absolute ceiling on layout passes, independent of the settle window. */
        private static final int MAX_PASSES = 24;

        private final View screen;
        private final View alerts;
        private int passes;
        private boolean stopped;

        AlertsScroller(View screen, View alerts) {
            this.screen = screen;
            this.alerts = alerts;
        }

        void start() {
            // Already laid out (the bell was tapped while Water was on display): scroll at once
            // so the tap answers immediately, then correct if the panels are still arriving.
            if (screen.getHeight() > 0) scroll();
            if (stopped) return;
            screen.getViewTreeObserver().addOnGlobalLayoutListener(this);
            // Backstop for the case where no further layout pass is ever dispatched.
            screen.postDelayed(this::stop, SETTLE_WINDOW_MS);
        }

        @Override public void onGlobalLayout() {
            if (activeScreen != screen || screen.getHeight() <= 0) {
                stop();
                return;
            }
            scroll();
            if (++passes >= MAX_PASSES) stop();
        }

        private void scroll() {
            performAlertScroll(screen, alerts);
        }

        private void stop() {
            if (stopped) return;
            stopped = true;
            ViewTreeObserver observer = screen.getViewTreeObserver();
            if (observer.isAlive()) observer.removeOnGlobalLayoutListener(this);
        }
    }

    /**
     * Scrolls the screen so the alerts section is on display.
     *
     * <p>The offset is accumulated up the view chain rather than handed to
     * {@link View#requestRectangleOnScreen}: {@code alerts_status} is nested several layouts
     * deep, and only the outermost scroller understands how to move, so walking up to it and
     * scrolling it directly is the one approach that cannot quietly stop short at an
     * intermediate layout.</p>
     *
     * <p>The result is clamped by {@code ScrollView.scrollTo} to the content bounds, so a
     * section near the very bottom cannot overshoot into blank space.</p>
     */
    private void performAlertScroll(View screen, View alerts) {
        // screen_water is rooted by a SwipeRefreshLayout, which only handles the
        // pull-to-refresh gesture; the vertical scrolling is done by the ScrollView nested
        // inside it. Scrolling the root would move nothing, because that container never
        // scrolls on its own.
        ScrollView scroller = findScrollView(screen);
        if (scroller == null) return;

        // Distance from the top of the scroller's content down to the alerts section.
        int offset = 0;
        boolean hosted = false;
        for (View node = alerts; node != null; node = parentOf(node)) {
            if (node == scroller) {
                hosted = true;
                break;
            }
            offset += node.getTop() - node.getScrollY();
        }
        if (!hosted) return; // not hosted by this scroller

        // Leave the "Alerts" heading, which sits immediately above the list, on screen too.
        int headingAllowance = Math.round(48 * getResources().getDisplayMetrics().density);
        scroller.scrollTo(0, alertScrollTarget(offset, headingAllowance));
    }

    /** Depth-first search for the scroller nested inside a screen root such as a swipe layout. */
    private static ScrollView findScrollView(View root) {
        if (root instanceof ScrollView) return (ScrollView) root;
        if (!(root instanceof ViewGroup)) return null;
        ViewGroup group = (ViewGroup) root;
        for (int i = 0; i < group.getChildCount(); i++) {
            ScrollView found = findScrollView(group.getChildAt(i));
            if (found != null) return found;
        }
        return null;
    }

    private static View parentOf(View view) {
        ViewParent parent = view.getParent();
        return parent instanceof View ? (View) parent : null;
    }

    /**
     * Badge count. Fed only by a successful alert fetch (see {@link AlertCountListener}); a failed
     * fetch reports 0 and clears the badge, because a figure the app can no longer substantiate
     * must not stay on screen.
     */
    @Override public void onAlertCountChanged(int count) {
        if (topBarAlertBadge == null) return;
        if (count <= 0) {
            topBarAlertBadge.setVisibility(View.GONE);
            topBarAlertBadge.setText(null);
            return;
        }
        topBarAlertBadge.setText(count > 99 ? "99+" : String.valueOf(count));
        topBarAlertBadge.setVisibility(View.VISIBLE);
    }

    @Override protected void onDestroy() {
        // The link listener would otherwise outlive this activity.
        ServerLink.setListener(null);
        super.onDestroy();
    }

    private void requestNotificationPermissionIfNeeded() {
        if (android.os.Build.VERSION.SDK_INT < android.os.Build.VERSION_CODES.TIRAMISU) return;
        if (androidx.core.content.ContextCompat.checkSelfPermission(this,
                android.Manifest.permission.POST_NOTIFICATIONS) == android.content.pm.PackageManager.PERMISSION_GRANTED) return;
        notificationPermissionLauncher.launch(android.Manifest.permission.POST_NOTIFICATIONS);
    }

    private final androidx.activity.result.ActivityResultLauncher<String> notificationPermissionLauncher =
            registerForActivityResult(new androidx.activity.result.contract.ActivityResultContracts.RequestPermission(),
                    granted -> { });

    /** Longest side kept when preparing a photograph for upload or display. */
    private static final int MAX_PHOTO_SIDE = 1600;

    /** Photo decode and JPEG encode never run on the main thread. */
    private static final java.util.concurrent.ExecutorService PHOTO_EXECUTOR =
            java.util.concurrent.Executors.newFixedThreadPool(2);

    /** Views belonging to the currently open "Post a lost or found item" dialog. */
    private LostFoundPhotoSlot lostFoundPhotoSlot;

    /** Only the most recent pick is allowed to write into the dialog. */
    private int lostFoundPhotoRequest;

    private static final class LostFoundPhotoSlot {
        Uri uri;
        byte[] uploadBytes;
        ImageView preview;
        MaterialButton picker;
        MaterialButton remove;
        TextView status;
    }

    private final ActivityResultLauncher<String> pickLostFoundPhoto =
            registerForActivityResult(new ActivityResultContracts.GetContent(), uri -> {
                final LostFoundPhotoSlot slot = lostFoundPhotoSlot;
                if (slot == null || uri == null) return;
                final int request = ++lostFoundPhotoRequest;
                slot.picker.setEnabled(false);
                slot.status.setText("Preparing photo…");
                PHOTO_EXECUTOR.execute(() -> {
                    final byte[] prepared = preparePhoto(uri);
                    // The preview is decoded from the very bytes that will be
                    // uploaded rather than from the in-memory bitmap. JPEG has
                    // no alpha channel, so a transparent PNG looks one way in an
                    // ImageView and a different way once compressed and served
                    // back — showing the bitmap would let the preview disagree
                    // with what the server actually stores.
                    final Bitmap preview = prepared == null ? null : decodePhoto(prepared);
                    runOnUiThread(() -> {
                        // The dialog may have closed, or a later pick may have won.
                        if (lostFoundPhotoSlot != slot || request != lostFoundPhotoRequest) return;
                        slot.picker.setEnabled(true);
                        if (prepared == null) {
                            slot.status.setText("That photo could not be read. Pick a different one.");
                            return;
                        }
                        slot.uri = uri;
                        slot.uploadBytes = prepared;
                        slot.preview.setImageDrawable(null);
                        if (preview != null) slot.preview.setImageBitmap(preview);
                        slot.preview.setVisibility(preview == null ? View.GONE : View.VISIBLE);
                        slot.remove.setVisibility(View.VISIBLE);
                        slot.picker.setText("Change photo");
                        slot.status.setText(preview == null
                                ? "Photo ready · " + Math.max(1, prepared.length / 1024)
                                        + " KB (preview unavailable)"
                                : "Photo ready · " + Math.max(1, prepared.length / 1024) + " KB");
                    });
                });
            });

    private void renderHome(View screen) {
        LinearLayout content = screen.findViewById(R.id.content_container);
        addSection(content, "Water status");

        // Inflate the structured 2x2 water status card
        View waterCard = getLayoutInflater().inflate(R.layout.item_home_water_status, content, false);
        content.addView(waterCard);

        TextView tankNameView = waterCard.findViewById(R.id.home_water_tank_name);
        TextView channelView = waterCard.findViewById(R.id.home_water_channel);
        TextView badgeView = waterCard.findViewById(R.id.home_water_badge);
        TextView phView = waterCard.findViewById(R.id.home_metric_ph);
        TextView tdsView = waterCard.findViewById(R.id.home_metric_tds);
        TextView turbidityView = waterCard.findViewById(R.id.home_metric_turbidity);
        TextView tempView = waterCard.findViewById(R.id.home_metric_temp);
        TextView footerView = waterCard.findViewById(R.id.home_water_footer);

        tankNameView.setText(HostelConfig.tankName());
        channelView.setText("Hostel Telemetry · Channel 244357");

        api.getLatestThingSpeakReading(null, new ApiCallback() {
            @Override public void onSuccess(String json) {
                if (activeScreen != screen) return;
                try {
                    JSONObject response = new JSONObject(json);
                    JSONObject values = response.optJSONObject("values");
                    String timestamp = response.optString("timestamp", "");
                    int entryId = response.optInt("entry_id", 0);
                    if (values != null) {
                        double ph = values.optDouble("pH", values.optDouble("ph", Double.NaN));
                        double tds = values.optDouble("TDS", values.optDouble("tds", Double.NaN));
                        double turbidity = values.optDouble("turbidity", Double.NaN);
                        double temp = values.optDouble("temperature", Double.NaN);

                        phView.setText(Double.isNaN(ph) ? "--" : format(ph));
                        tdsView.setText(Double.isNaN(tds) ? "--" : format(tds));
                        turbidityView.setText(Double.isNaN(turbidity) ? "--" : format(turbidity));
                        tempView.setText(Double.isNaN(temp) ? "--" : format(temp));

                        String timeStr = Timestamps.readable(timestamp);
                        Date parsed = Timestamps.parseUtc(timestamp);

                        // Freshness assessment matching backend 15-minute threshold
                        if (parsed != null) {
                            long ageMs = System.currentTimeMillis() - parsed.getTime();
                            if (ageMs >= 0 && ageMs < 15 * 60 * 1000L) {
                                badgeView.setText("ONLINE");
                                badgeView.setBackgroundTintList(ColorStateList.valueOf(getColor(R.color.hydroguard_green_surface)));
                                badgeView.setTextColor(getColor(R.color.hydroguard_green));
                            } else {
                                badgeView.setText("DATA DELAYED");
                                badgeView.setBackgroundTintList(ColorStateList.valueOf(getColor(R.color.hydroguard_caution_surface)));
                                badgeView.setTextColor(getColor(R.color.hydroguard_orange));
                            }
                        } else {
                            badgeView.setText("ONLINE");
                            badgeView.setBackgroundTintList(ColorStateList.valueOf(getColor(R.color.hydroguard_green_surface)));
                            badgeView.setTextColor(getColor(R.color.hydroguard_green));
                        }

                        StringBuilder sb = new StringBuilder("Observed: ");
                        sb.append(timeStr.isEmpty() ? "Recent observation" : timeStr);
                        if (entryId > 0) sb.append(" · Feed #").append(entryId);
                        sb.append(" · Source: ThingSpeak");
                        footerView.setText(sb.toString());
                    } else {
                        badgeView.setText("UNAVAILABLE");
                        badgeView.setBackgroundTintList(ColorStateList.valueOf(getColor(R.color.hydroguard_subsurface)));
                        badgeView.setTextColor(getColor(R.color.hydroguard_muted));
                        footerView.setText("Water reading values currently unavailable.");
                    }
                } catch (JSONException error) {
                    badgeView.setText("ERROR");
                    badgeView.setBackgroundTintList(ColorStateList.valueOf(getColor(R.color.hydroguard_critical_surface)));
                    badgeView.setTextColor(getColor(R.color.hydroguard_critical));
                    footerView.setText("Reading data is unavailable.");
                }
            }
            @Override public void onFailure(ApiFailure failure) {
                if (activeScreen == screen) {
                    badgeView.setText("OFFLINE");
                    badgeView.setBackgroundTintList(ColorStateList.valueOf(getColor(R.color.hydroguard_critical_surface)));
                    badgeView.setTextColor(getColor(R.color.hydroguard_critical));
                    footerView.setText("Live water telemetry unavailable (" + failure.getMessage() + ").");
                }
            }
        });

        MaterialButton openWater = addButton(content, "View water details and alerts");
        openWater.setOnClickListener(view -> navigation.setSelectedItemId(R.id.nav_water));

        // Optional sections render into their own body so an empty list never leaves
        // a placeholder card sitting under the heading.
        addSection(content, "Notices");
        loadNotices(sectionBody(content), screen, false, false);
        addSection(content, "Emergency contacts");
        LinearLayout contacts = sectionBody(content);
        api.getEmergencyContacts(new ApiCallback() {
            @Override public void onSuccess(String json) { if (activeScreen == screen) renderEmergencyContacts(contacts, json, false); }
            @Override public void onFailure(ApiFailure failure) { if (activeScreen == screen) addCard(contacts, failure.getMessage()); }
        });
        addSection(content, "Lost and found");
        MaterialButton postLostFound = addSecondaryButton(content, "Post a lost or found item");
        postLostFound.setOnClickListener(view -> showLostFoundDialog());
        LinearLayout lostFound = sectionBody(content);
        api.getLostFoundItems(new ApiCallback() {
            @Override public void onSuccess(String json) {
                if (activeScreen == screen) displayLostFoundRows(lostFound, json, screen);
            }
            @Override public void onFailure(ApiFailure failure) { if (activeScreen == screen) addCard(lostFound, failure.getMessage()); }
        });
        MaterialButton report = addSecondaryButton(content, "Report a hostel issue");
        report.setOnClickListener(view -> navigation.setSelectedItemId(R.id.nav_report));
        MaterialButton issues = addSecondaryButton(content, "Follow my issue reports");
        issues.setOnClickListener(view -> navigation.setSelectedItemId(R.id.nav_issues));
    }

    private void renderIssueForm(View screen) {
        Spinner category = screen.findViewById(R.id.issue_category);
        category.setAdapter(adapter(ISSUE_CATEGORIES));
        Spinner severity = screen.findViewById(R.id.issue_severity);
        severity.setAdapter(adapter(ISSUE_SEVERITIES));
        EditText location = screen.findViewById(R.id.issue_location);
        EditText description = screen.findViewById(R.id.issue_description);
        TextView issueStatus = screen.findViewById(R.id.issue_form_status);
        MaterialButton submitIssue = screen.findViewById(R.id.submit_issue);

        Spinner feedbackCategory = screen.findViewById(R.id.feedback_category);
        feedbackCategory.setAdapter(adapter(new String[]{"Water", "Cleanliness", "Maintenance", "Wi-Fi", "Common Areas", "Overall Hostel Experience"}));
        Spinner rating = screen.findViewById(R.id.feedback_rating);
        if (rating != null) {
            rating.setAdapter(adapter(new String[]{"5 stars", "4 stars", "3 stars", "2 stars", "1 star"}));
        }
        EditText comment = screen.findViewById(R.id.feedback_comment);
        TextView feedbackStatus = screen.findViewById(R.id.feedback_status);
        MaterialButton submitFeedback = screen.findViewById(R.id.submit_feedback);

        final int[] selectedStars = {5};
        final String[] starLabels = {
            "1 Star · Poor",
            "2 Stars · Fair",
            "3 Stars · Average",
            "4 Stars · Good",
            "5 Stars · Excellent"
        };
        final ImageView[] starViews = {
            screen.findViewById(R.id.star_1),
            screen.findViewById(R.id.star_2),
            screen.findViewById(R.id.star_3),
            screen.findViewById(R.id.star_4),
            screen.findViewById(R.id.star_5)
        };
        final TextView ratingText = screen.findViewById(R.id.feedback_rating_text);

        // Disabling the button only while a request is in flight is not enough:
        // a repeat tap after the first call has already succeeded files a second,
        // identical record. Instead each form locks on success and only unlocks
        // once the student actually edits something, so "submit" can never be
        // pressed twice for the same content.
        boolean[] issueLocked = {false};
        boolean[] feedbackLocked = {false};
        unlockOnEdit(location, () -> unlock(issueLocked, submitIssue));
        unlockOnEdit(description, () -> unlock(issueLocked, submitIssue));
        unlockOnEdit(comment, () -> unlock(feedbackLocked, submitFeedback));
        unlockOnSelect(severity, () -> unlock(issueLocked, submitIssue));
        unlockOnSelect(category, () -> unlock(issueLocked, submitIssue));
        if (rating != null) {
            unlockOnSelect(rating, () -> unlock(feedbackLocked, submitFeedback));
        }
        unlockOnSelect(feedbackCategory, () -> unlock(feedbackLocked, submitFeedback));

        Runnable updateStarDisplay = () -> {
            int current = selectedStars[0];
            for (int i = 0; i < 5; i++) {
                if (starViews[i] != null) {
                    starViews[i].setImageResource(i < current ? R.drawable.ic_star_filled : R.drawable.ic_star_outline);
                }
            }
            if (ratingText != null) {
                ratingText.setText(starLabels[Math.max(0, Math.min(4, current - 1))]);
            }
            if (rating != null && rating.getCount() >= 5) {
                rating.setSelection(5 - current);
            }
        };

        for (int i = 0; i < 5; i++) {
            final int starVal = i + 1;
            if (starViews[i] != null) {
                starViews[i].setOnClickListener(v -> {
                    selectedStars[0] = starVal;
                    updateStarDisplay.run();
                    unlock(feedbackLocked, submitFeedback);
                });
            }
        }
        updateStarDisplay.run();

        submitIssue.setOnClickListener(button -> {
            String place = location.getText().toString().trim();
            String detail = description.getText().toString().trim();
            if (place.length() < 2 || detail.length() < 5) {
                issueStatus.setText("Enter a location and a description of at least 5 characters.");
                return;
            }
            issueStatus.setText("Submitting your report…");
            button.setEnabled(false);
            ApiCallback settle = resultWithReenable(button, issueStatus,
                    "Your report was submitted.", "The report could not be submitted.");
            api.createIssue(String.valueOf(category.getSelectedItem()), place,
                    String.valueOf(severity.getSelectedItem()), detail,
                    new ApiCallback() {
                        @Override public void onSuccess(String json) {
                            settle.onSuccess(json);
                            issueLocked[0] = true;
                            button.setEnabled(false);
                            issueStatus.setText("Your report was submitted. Change any field to file another.");
                        }

                        @Override public void onFailure(ApiFailure failure) { settle.onFailure(failure); }
                    });
        });

        submitFeedback.setOnClickListener(button -> {
            String note = comment.getText().toString();
            int stars = selectedStars[0];
            feedbackStatus.setText("Sending feedback…");
            button.setEnabled(false);
            ApiCallback settle = resultWithReenable(button, feedbackStatus,
                    "Thank you for your feedback.", "Feedback could not be sent.");
            api.submitHostelFeedback(String.valueOf(feedbackCategory.getSelectedItem()), stars,
                    note,
                    new ApiCallback() {
                        @Override public void onSuccess(String json) {
                            settle.onSuccess(json);
                            feedbackLocked[0] = true;
                            button.setEnabled(false);
                            feedbackStatus.setText("Thank you for your feedback. Change any field to send another.");
                        }

                        @Override public void onFailure(ApiFailure failure) { settle.onFailure(failure); }
                    });
        });
    }

    private static void unlock(boolean[] locked, View control) {
        if (locked[0]) {
            locked[0] = false;
            control.setEnabled(true);
        }
    }

    /** Re-enables a locked submit control once the student edits {@code field}. */
    private static void unlockOnEdit(TextView field, Runnable unlock) {
        field.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int a, int b, int c) { }
            @Override public void onTextChanged(CharSequence s, int a, int b, int c) { }
            @Override public void afterTextChanged(Editable s) { unlock.run(); }
        });
    }

    /** Re-enables a locked submit control once the student picks a new option. */
    private static void unlockOnSelect(Spinner spinner, Runnable unlock) {
        spinner.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            boolean firstCallback = true;

            @Override public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
                // The framework fires one callback per spinner as soon as it is
                // laid out; that is not a user choice and must not unlock anything.
                if (firstCallback) { firstCallback = false; return; }
                unlock.run();
            }

            @Override public void onNothingSelected(AdapterView<?> parent) { }
        });
    }

    private void renderIssues(View screen, boolean admin) {
        LinearLayout content = screen.findViewById(R.id.content_container);
        if (!admin) {
            MaterialButton newReport = addButton(content, "File a new hostel report");
            newReport.setOnClickListener(v -> navigation.setSelectedItemId(R.id.nav_report));
        }
        // Loading is replaced by either the records, an empty notice or an error —
        // never two of them at once.
        TextView loading = addCard(content, "Loading issue reports…");
        api.getIssues(new ApiCallback() {
            @Override public void onSuccess(String json) {
                if (activeScreen != screen) return;
                removeCard(content, loading);
                try {
                    JSONArray rows = new JSONArray(json);
                    java.util.LinkedHashMap<String, JSONObject> unique = new java.util.LinkedHashMap<>();
                    for (int i = 0; i < rows.length(); i++) {
                        JSONObject item = rows.optJSONObject(i);
                        if (item == null) continue;
                        String id = item.optString("id", "");
                        unique.put(id.isEmpty() ? "row-" + i : id, item);
                    }
                    if (unique.isEmpty()) { addCard(content, "No issue reports are recorded yet."); return; }
                    for (JSONObject item : unique.values()) displayIssue(content, item, admin);
                } catch (JSONException error) { addCard(content, "The server returned an invalid issue list."); }
            }
            @Override public void onFailure(ApiFailure failure) {
                if (activeScreen == screen) loading.setText(failure.getMessage());
            }
        });
    }

    private void displayIssue(LinearLayout content, JSONObject item, boolean admin) {
        renderIssueCard(cardContent(content), item, admin, null);
    }

    /**
     * Draws one issue report.
     *
     * <p>Called again with the record the server returned after a status change,
     * so the card only ever shows a state the backend confirmed — never an
     * optimistic one. {@code notice} is the confirmation line to display, or
     * {@code null} for the first render.</p>
     */
    private void renderIssueCard(LinearLayout card, JSONObject item, boolean admin, String notice) {
        card.removeAllViews();
        String id = item.optString("id", "");
        String status = item.optString("status", IssueWorkflow.OPEN);

        addText(card, item.optString("category", "Issue") + " · " + item.optString("severity", "MEDIUM"),
                15, getColor(R.color.hydroguard_text), true);
        addText(card, item.optString("location", "") + " · " + IssueWorkflow.statusLabel(status),
                13, getColor(R.color.hydroguard_blue), true);
        addText(card, item.optString("description", ""), 14, getColor(R.color.hydroguard_text), false);
        String created = Timestamps.readable(item.optString("created_at", ""));
        if (!created.isEmpty()) addText(card, created, 12, getColor(R.color.hydroguard_muted), false);
        String resolution = nonNullText(item, "resolution");
        if (!resolution.isEmpty()) {
            addText(card, "Resolution: " + resolution, 13, getColor(R.color.hydroguard_text), false);
        }
        String updated = Timestamps.readable(item.optString("updated_at", ""));
        if (!updated.isEmpty()) addText(card, "Last updated " + updated, 12, getColor(R.color.hydroguard_muted), false);

        TextView result = addText(card, "", 13, getColor(R.color.hydroguard_blue), true);
        if (notice == null || notice.isEmpty()) {
            result.setVisibility(View.GONE);
        } else {
            result.setText(notice);
        }

        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.VERTICAL);
        card.addView(actions, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        if (admin) renderAdminIssueActions(card, actions, result, id, status, admin);
        else renderStudentIssueActions(card, actions, result, id, status, admin);
    }

    /** Every button here is derived from {@link IssueWorkflow#nextStatuses}. */
    private void renderAdminIssueActions(LinearLayout card, LinearLayout actions, TextView result,
                                         String id, String status, boolean admin) {
        List<MaterialButton> transitions = new ArrayList<>();
        for (String target : IssueWorkflow.nextStatuses(status)) {
            // ASSIGNED needs a staff identifier the app does not collect, and
            // REOPENED must carry a written reason, so both get their own path.
            if ("ASSIGNED".equals(target) || "REOPENED".equals(target)) continue;
            final String next = target;
            MaterialButton button = actionButton(actions, IssueWorkflow.actionLabel(status, next));
            transitions.add(button);
            button.setOnClickListener(view ->
                    requestTransition(card, id, status, next, transitions, result, admin));
        }
        if (IssueWorkflow.isReopenable(status)) {
            MaterialButton reopen = actionButton(actions, "Reopen");
            transitions.add(reopen);
            reopen.setOnClickListener(view -> showReopenDialog(card, id, transitions, result, admin));
        }
        MaterialButton timeline = actionButton(actions, "View timeline");
        timeline.setOnClickListener(view -> showTimeline(id));
    }

    /** Students read their own status and may rate or reopen a finished report. */
    private void renderStudentIssueActions(LinearLayout card, LinearLayout actions, TextView result,
                                           String id, String status, boolean admin) {
        MaterialButton timeline = actionButton(actions, "View update timeline");
        timeline.setOnClickListener(view -> showTimeline(id));
        if (IssueWorkflow.isReopenable(status)) {
            MaterialButton feedback = actionButton(actions, "Rate this resolution");
            feedback.setOnClickListener(view -> showResolutionDialog(id));
            MaterialButton reopen = actionButton(actions, "Reopen issue");
            reopen.setOnClickListener(view -> showReopenDialog(card, id, null, result, admin));
        }
    }

    /** Route to a prompt when the target status needs input, otherwise send directly. */
    private void requestTransition(LinearLayout card, String id, String from, String to,
                                   List<MaterialButton> buttons, TextView result, boolean admin) {
        if (IssueWorkflow.requiresResolution(to)) {
            showResolveDialog(card, id, buttons, result, admin);
        } else if ("WAITING".equals(to)) {
            showWaitingDialog(card, id, buttons, result, admin);
        } else {
            sendTransition(card, id, to, null, null, buttons, result, admin);
        }
    }

    /**
     * Save one transition. The buttons are disabled before the request leaves
     * the device, so a double tap cannot fire twice; they are restored only if
     * the server rejects the change.
     */
    private void sendTransition(LinearLayout card, String id, String status,
                                String comment, String resolution,
                                List<MaterialButton> buttons, TextView result, boolean admin) {
        setActionsEnabled(buttons, false);
        result.setVisibility(View.VISIBLE);
        result.setTextColor(getColor(R.color.hydroguard_blue));
        result.setText("Saving…");
        api.updateIssueStatus(id, status, comment, resolution, new ApiCallback() {
            @Override public void onSuccess(String json) {
                try {
                    JSONObject updated = new JSONObject(json);
                    renderIssueCard(card, updated, admin,
                            "Saved: " + IssueWorkflow.statusLabel(updated.optString("status", status)));
                } catch (JSONException error) {
                    // The status change was accepted but the body was not the
                    // record we expect. Re-read it rather than guess.
                    result.setText("Saved. Reloading the report…");
                    reloadIssue(card, id, result, admin);
                }
            }

            @Override public void onFailure(ApiFailure failure) {
                String message = failure.getMessage();
                result.setVisibility(View.VISIBLE);
                result.setTextColor(getColor(R.color.hydroguard_red));
                result.setText(message == null || message.isEmpty()
                        ? "Could not save the status change. Nothing was updated."
                        : message);
                setActionsEnabled(buttons, true);
            }
        });
    }

    /** Re-read the record after an ambiguous success so the card stays truthful. */
    private void reloadIssue(LinearLayout card, String id, TextView result, boolean admin) {
        api.getIssue(id, new ApiCallback() {
            @Override public void onSuccess(String json) {
                try {
                    JSONObject record = new JSONObject(json);
                    renderIssueCard(card, record, admin,
                            "Saved: " + IssueWorkflow.statusLabel(record.optString("status", "")));
                } catch (JSONException error) {
                    markIssueUnavailable(result);
                }
            }

            @Override public void onFailure(ApiFailure failure) { markIssueUnavailable(result); }
        });
    }

    /** The change was saved server-side; say so plainly instead of guessing the state. */
    private void markIssueUnavailable(TextView result) {
        result.setVisibility(View.VISIBLE);
        result.setTextColor(getColor(R.color.hydroguard_red));
        result.setText("Saved, but this report could not be reloaded. Refresh the list to see the saved status.");
    }

    private void setActionsEnabled(List<MaterialButton> buttons, boolean enabled) {
        if (buttons == null) return;
        for (MaterialButton button : buttons) button.setEnabled(enabled);
    }

    private MaterialButton actionButton(LinearLayout parent, String label) {
        MaterialButton button = new MaterialButton(this);
        button.setText(label);
        button.setAllCaps(false);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(48));
        params.setMargins(0, dp(4), 0, dp(4));
        parent.addView(button, params);
        return button;
    }

    /** Resolve needs a summary; the dialog stays open until one is provided. */
    private void showResolveDialog(LinearLayout card, String id,
                                   List<MaterialButton> buttons, TextView result, boolean admin) {
        EditText input = new EditText(this);
        input.setHint("What was done to fix it? (required)");
        input.setMinLines(2);
        input.setMaxLines(4);
        AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle("Resolve issue")
                .setView(input)
                .setNegativeButton("Cancel", null)
                .setPositiveButton("Resolve", null)
                .create();
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE)
                .setOnClickListener(view -> {
                    String summary = input.getText().toString().trim();
                    if (summary.length() < 5) {
                        input.setError("Describe the fix in at least 5 characters.");
                        return;
                    }
                    dialog.dismiss();
                    sendTransition(card, id, "RESOLVED", null, summary, buttons, result, admin);
                }));
        dialog.show();
    }

    /** Waiting is optional-note territory: send it with or without a reason. */
    private void showWaitingDialog(LinearLayout card, String id,
                                   List<MaterialButton> buttons, TextView result, boolean admin) {
        EditText input = new EditText(this);
        input.setHint("Why is it waiting? (optional)");
        input.setMinLines(2);
        input.setMaxLines(4);
        new AlertDialog.Builder(this)
                .setTitle("Mark as waiting")
                .setView(input)
                .setNegativeButton("Cancel", null)
                .setPositiveButton("Save", (dialog, which) -> {
                    String reason = input.getText().toString().trim();
                    sendTransition(card, id, "WAITING",
                            reason.isEmpty() ? null : reason, null, buttons, result, admin);
                })
                .show();
    }

    private void showTimeline(String issueId) {
        api.getIssueTimeline(issueId, new ApiCallback() {
            @Override public void onSuccess(String json) {
                try {
                    JSONArray events = new JSONArray(json);
                    StringBuilder text = new StringBuilder();
                    for (int i = 0; i < events.length(); i++) {
                        JSONObject event = events.getJSONObject(i);
                        text.append(Timestamps.readable(event.optString("created_at", ""))).append(" · ")
                                .append(IssueWorkflow.statusLabel(event.optString("to_status", ""))).append("\n")
                                .append(nonNullText(event, "comment")).append("\n\n");
                    }
                    new AlertDialog.Builder(DashboardActivity.this).setTitle("Issue timeline")
                            .setMessage(text.length() == 0 ? "No updates are available." : text.toString())
                            .setPositiveButton("Close", null).show();
                } catch (JSONException error) { showToast("The issue timeline is unavailable."); }
            }

            @Override public void onFailure(ApiFailure failure) { showToast(failure.getMessage()); }
        });
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

    private void showReopenDialog(LinearLayout card, String issueId,
                                  List<MaterialButton> buttons, TextView result, boolean admin) {
        EditText reason = new EditText(this);
        reason.setHint("Why does the issue need more work? (required)");
        reason.setMinLines(2);
        reason.setMaxLines(4);
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle("Reopen issue").setView(reason)
                .setNegativeButton("Cancel", null)
                .setPositiveButton("Reopen", null)
                .create();
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE)
                .setOnClickListener(view -> {
                    String text = reason.getText().toString().trim();
                    if (text.length() < 5) {
                        reason.setError("Enter at least 5 characters.");
                        return;
                    }
                    dialog.dismiss();
                    setActionsEnabled(buttons, false);
                    result.setVisibility(View.VISIBLE);
                    result.setTextColor(getColor(R.color.hydroguard_blue));
                    result.setText("Saving…");
                    api.reopenIssue(issueId, text, new ApiCallback() {
                        @Override public void onSuccess(String json) {
                            try {
                                JSONObject updated = new JSONObject(json);
                                renderIssueCard(card, updated, admin, "Saved: "
                                        + IssueWorkflow.statusLabel(updated.optString("status", "REOPENED")));
                            } catch (JSONException error) {
                                result.setText("Saved. Reloading the report…");
                                reloadIssue(card, issueId, result, admin);
                            }
                        }

                        @Override public void onFailure(ApiFailure failure) {
                            String message = failure.getMessage();
                            result.setTextColor(getColor(R.color.hydroguard_red));
                            result.setText(message == null || message.isEmpty()
                                    ? "Could not reopen the report. Nothing was changed." : message);
                            setActionsEnabled(buttons, true);
                        }
                    });
                }));
        dialog.show();
    }

    private void renderProfile(View screen) {
        LinearLayout content = screen.findViewById(R.id.content_container);
        addSection(content, displayName == null || displayName.isEmpty() ? "HydroGuard account" : displayName);
        addCard(content, email + "\nRole: " + (isAdmin ? "Administrator" : "Student")
                + "\nYour permissions are checked by the HydroGuard backend.");
        if (!isAdmin) {
            MaterialButton water = addSecondaryButton(content, "Water monitoring");
            water.setOnClickListener(view -> navigation.setSelectedItemId(R.id.nav_water));
            MaterialButton issues = addSecondaryButton(content, "My hostel issues");
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
                removeCard(content, issueLoad);
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
        loadNotices(content, screen, true, true);
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
            @Override public void onSuccess(String json) { if (activeScreen == screen) renderLostFoundAdmin(content, json, screen); }
            @Override public void onFailure(ApiFailure failure) { if (activeScreen == screen) addCard(content, failure.getMessage()); }
        });
        addSection(content, "Hostel feedback");
        api.getAdminFeedback(new ApiCallback() {
            @Override public void onSuccess(String json) { if (activeScreen == screen) displayRows(content, json, "category", "comment", "rating", true); }
            @Override public void onFailure(ApiFailure failure) { if (activeScreen == screen) addCard(content, failure.getMessage()); }
        });
        api.getResolutionFeedback(new ApiCallback() {
            @Override public void onSuccess(String json) { if (activeScreen == screen) displayRows(content, json, "issue_id", "comment", "stars", true); }
            @Override public void onFailure(ApiFailure failure) { if (activeScreen == screen) addCard(content, failure.getMessage()); }
        });
    }

    private String formatSummary(JSONObject json) {
        JSONObject status = json.optJSONObject("by_status");
        if (status == null) status = new JSONObject();
        StringBuilder text = new StringBuilder("Total reports: ").append(json.optInt("total"));
        String[] order = {"SUBMITTED", "ACKNOWLEDGED", "ASSIGNED", "IN_PROGRESS", "WAITING", "RESOLVED", "CLOSED", "REOPENED"};
        for (String key : order) {
            int count = status.optInt(key);
            if (count <= 0) continue;
            text.append("\n").append(IssueWorkflow.statusLabel(key)).append(": ").append(count);
        }
        return text.toString();
    }

    private void loadNotices(LinearLayout content, View screen, boolean admin, boolean showEmptyState) {
        api.getNotices(new ApiCallback() {
            @Override public void onSuccess(String json) {
                if (activeScreen != screen) return;
                int before = content.getChildCount();
                displayRows(content, json, "title", "body", "priority", showEmptyState);
                if (admin) addNoticeDeleteActions(content, json, before);
            }
            @Override public void onFailure(ApiFailure failure) { if (activeScreen == screen) addCard(content, failure.getMessage()); }
        });
    }

    private void renderLostFoundAdmin(LinearLayout content, String json, View screen) {
        try {
            JSONArray rows = new JSONArray(json);
            if (rows.length() == 0) { addCard(content, "No items are waiting for moderation."); return; }
            for (int i = 0; i < rows.length(); i++) {
                JSONObject item = rows.getJSONObject(i);
                LinearLayout card = cardContent(content);
                addText(card, item.optString("kind", "Item") + " · " + item.optString("title", ""), 15, getColor(R.color.hydroguard_text), true);
                addText(card, item.optString("description", "") + "\n" + item.optString("location", ""), 13, getColor(R.color.hydroguard_muted), false);
                // A moderator cannot judge a reported item without seeing it.
                attachLostFoundPhoto(card, value(item, "image_url"), screen);
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

    private void displayRows(LinearLayout content, String json, String titleKey, String bodyKey,
                             String detailKey, boolean showEmptyState) {
        try {
            JSONArray rows = new JSONArray(json);
            java.util.LinkedHashMap<String, JSONObject> unique = new java.util.LinkedHashMap<>();
            for (int i = 0; i < rows.length(); i++) {
                JSONObject row = rows.optJSONObject(i);
                if (row == null) continue;
                // Stable ids keep a repeated submission from rendering twice.
                String id = row.optString("id", "");
                String key = id.isEmpty()
                        ? value(row, titleKey) + "|" + value(row, bodyKey) + "|" + value(row, detailKey)
                        : id;
                if (!unique.containsKey(key)) unique.put(key, row);
            }
            if (unique.isEmpty()) {
                if (showEmptyState) addCard(content, "No records are available yet.");
                return;
            }
            for (JSONObject row : unique.values()) {
                addCard(content, value(row, titleKey) + "\n" + value(row, bodyKey)
                        + (detailKey.isEmpty() ? "" : "\n" + value(row, detailKey)));
            }
        } catch (JSONException error) { addCard(content, "The server returned an invalid response."); }
    }

    private void renderEmergencyContacts(LinearLayout content, String json, boolean showEmptyState) {
        try {
            JSONArray rows = new JSONArray(json);
            if (rows.length() == 0) {
                if (showEmptyState) addCard(content, "No emergency contacts are configured.");
                return;
            }
            for (int i = 0; i < rows.length(); i++) {
                JSONObject row = rows.optJSONObject(i);
                if (row == null) continue;
                String name = row.optString("name", "Contact");
                String phone = row.optString("phone", "");
                String category = row.optString("category", "General");
                String details = row.optString("details", "");

                LinearLayout card = cardContent(content);
                addText(card, name + " · " + category, 15, getColor(R.color.hydroguard_text), true);
                String desc = (details.isEmpty() ? "" : details + "\n") + phone + "\nTap to open phone dialer";
                addText(card, desc, 13, getColor(R.color.hydroguard_blue), false);

                if (!phone.isEmpty()) {
                    View parentCard = (View) card.getParent();
                    if (parentCard != null) {
                        parentCard.setClickable(true);
                        parentCard.setFocusable(true);
                        parentCard.setOnClickListener(v -> {
                            try {
                                Intent intent = new Intent(Intent.ACTION_DIAL, Uri.parse("tel:" + phone.replaceAll("[^0-9+]", "")));
                                startActivity(intent);
                            } catch (Exception e) {
                                showToast("Could not open dialer for " + phone);
                            }
                        });
                    }
                }
            }
        } catch (JSONException error) {
            addCard(content, "The server returned an invalid contact list.");
        }
    }

    /**
     * Renders lost-and-found rows separately from {@link #displayRows} because
     * each row may carry a photograph that has to be fetched with the
     * signed-in user's credentials and decoded off the main thread.
     */
    private void displayLostFoundRows(LinearLayout content, String json, View screen) {
        try {
            JSONArray rows = new JSONArray(json);
            java.util.LinkedHashMap<String, JSONObject> unique = new java.util.LinkedHashMap<>();
            for (int i = 0; i < rows.length(); i++) {
                JSONObject row = rows.optJSONObject(i);
                if (row == null) continue;
                String id = nonNullText(row, "id");
                if (id.isEmpty()) id = value(row, "kind") + "|" + value(row, "title") + "|" + value(row, "description");
                if (!unique.containsKey(id)) unique.put(id, row);
            }
            if (unique.isEmpty()) return;
            for (JSONObject row : unique.values()) {
                LinearLayout card = cardContent(content);
                addText(card, value(row, "kind") + " · " + value(row, "title"), 15,
                        getColor(R.color.hydroguard_text), true);
                addText(card, value(row, "description")
                                + "\n" + value(row, "category") + " · " + value(row, "location")
                                + "\n" + moderationLabel(value(row, "moderation_status")),
                        13, getColor(R.color.hydroguard_muted), false);
                attachLostFoundPhoto(card, value(row, "image_url"), screen);
            }
        } catch (JSONException error) {
            addCard(content, "The server returned an invalid Lost & Found list.");
        }
    }

    private String moderationLabel(String status) {
        if ("PENDING".equalsIgnoreCase(status)) return "Waiting for a moderator";
        if ("APPROVED".equalsIgnoreCase(status)) return "Approved and visible to everyone";
        if ("REJECTED".equalsIgnoreCase(status)) return "Not approved";
        if ("REMOVED".equalsIgnoreCase(status)) return "Removed by a moderator";
        return "";
    }

    /**
     * Appends an item's photograph to a card.
     *
     * <p>References this server did not issue are skipped instead of fetched,
     * so a tampered {@code image_url} never becomes a request; failures are
     * shown as text rather than hidden.</p>
     */
    private void attachLostFoundPhoto(LinearLayout card, String imageUrl, View screen) {
        if (!LostFoundPhotos.isServerPhotoReference(imageUrl)) return;

        TextView statusView = new TextView(this);
        statusView.setText("Loading photo…");
        statusView.setTextSize(12);
        statusView.setTextColor(getColor(R.color.hydroguard_muted));
        statusView.setPadding(0, dp(6), 0, 0);
        card.addView(statusView);

        ImageView imageView = new ImageView(this);
        // Same bounded treatment as the dialog preview: an unconstrained
        // portrait photo is several thousand pixels tall and would dominate
        // the list card.
        imageView.setScaleType(ImageView.ScaleType.FIT_CENTER);
        imageView.setPadding(0, dp(6), 0, dp(6));
        imageView.setContentDescription("Photo attached to this lost and found item");
        imageView.setVisibility(View.GONE);
        card.addView(imageView, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(200)));

        api.fetchLostFoundPhoto(imageUrl, new ApiRepository.PhotoCallback() {
            @Override public void onPhoto(byte[] bytes, String contentType) {
                PHOTO_EXECUTOR.execute(() -> {
                    final Bitmap bitmap = decodePhoto(bytes);
                    runOnUiThread(() -> {
                        if (activeScreen != screen) return;
                        if (bitmap == null) {
                            statusView.setText("This photo could not be displayed.");
                            return;
                        }
                        statusView.setVisibility(View.GONE);
                        imageView.setImageBitmap(bitmap);
                        imageView.setVisibility(View.VISIBLE);
                        imageView.setClickable(true);
                        imageView.setFocusable(true);
                        imageView.setOnClickListener(v -> {
                            ImageView fullView = new ImageView(DashboardActivity.this);
                            fullView.setImageBitmap(bitmap);
                            fullView.setAdjustViewBounds(true);
                            fullView.setPadding(dp(12), dp(12), dp(12), dp(12));
                            new AlertDialog.Builder(DashboardActivity.this)
                                    .setTitle("Photo preview")
                                    .setView(fullView)
                                    .setPositiveButton("Close", null)
                                    .show();
                        });
                    });
                });
            }

            @Override public void onFailure(ApiFailure failure) {
                if (activeScreen != screen) return;
                statusView.setText("Photo unavailable · " + failure.getMessage());
            }
        });
    }

    /** A body container that optional Home sections render into. */
    private LinearLayout sectionBody(LinearLayout parent) {
        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        parent.addView(body, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        return body;
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
        EditText location = input("Last seen location within the hostel",
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);

        final LostFoundPhotoSlot slot = new LostFoundPhotoSlot();
        slot.preview = new ImageView(this);
        // Fixed height rather than adjustViewBounds: a portrait screenshot has a
        // ~0.45 aspect ratio, and a wrap-height preview alone was tall enough to
        // push "Remove photo" and the status line past the bottom of the dialog.
        slot.preview.setScaleType(ImageView.ScaleType.FIT_CENTER);
        slot.preview.setLayoutParams(new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(220)));
        slot.preview.setPadding(0, dp(6), 0, dp(6));
        slot.preview.setContentDescription("Preview of the photo that will be uploaded");
        slot.preview.setVisibility(View.GONE);

        slot.picker = new MaterialButton(this);
        slot.picker.setText("Add a photo"); slot.picker.setAllCaps(false);

        slot.remove = new MaterialButton(this);
        slot.remove.setText("Remove photo"); slot.remove.setAllCaps(false);
        slot.remove.setVisibility(View.GONE);

        slot.status = new TextView(this);
        slot.status.setTextColor(getColor(R.color.hydroguard_muted));
        slot.status.setTextSize(13);
        slot.status.setPadding(0, dp(10), 0, 0);
        slot.status.setText("A photo helps other students recognise the item.");

        form.addView(kind); form.addView(category); form.addView(title);
        form.addView(description); form.addView(location);
        form.addView(slot.picker); form.addView(slot.preview); form.addView(slot.remove);
        form.addView(slot.status);

        slot.picker.setOnClickListener(view -> pickLostFoundPhoto.launch("image/*"));
        slot.remove.setOnClickListener(view -> clearPhoto(slot));

        lostFoundPhotoSlot = slot;
        lostFoundPhotoRequest++;

        // AlertDialog's custom panel does not scroll on its own, so a tall form
        // is clipped instead of scrolled. The photo rows make this form tall
        // enough that clipping hid the remove button and the status line.
        android.widget.ScrollView scroll = new android.widget.ScrollView(this);
        scroll.setVerticalScrollBarEnabled(false);
        scroll.addView(form);

        AlertDialog dialog = new AlertDialog.Builder(this).setTitle("Post a lost or found item").setView(scroll)
                .setNegativeButton("Cancel", null)
                .setPositiveButton("Submit", null)
                .create();
        dialog.setOnDismissListener(ignored -> {
            if (lostFoundPhotoSlot == slot) lostFoundPhotoSlot = null;
        });
        dialog.show();
        // The positive button's own listener would dismiss the dialog before the
        // upload finishes, so it is replaced: the form stays open and shows the
        // server's real answer when a request fails.
        android.widget.Button submit = dialog.getButton(AlertDialog.BUTTON_POSITIVE);
        submit.setOnClickListener(view -> submitLostFound(dialog, submit, slot, kind, category,
                title, description, location));
    }

    private void clearPhoto(LostFoundPhotoSlot slot) {
        lostFoundPhotoRequest++;
        slot.uri = null;
        slot.uploadBytes = null;
        slot.preview.setImageDrawable(null);
        slot.preview.setVisibility(View.GONE);
        slot.remove.setVisibility(View.GONE);
        slot.picker.setText("Add a photo");
        slot.status.setText("A photo helps other students recognise the item.");
    }

    /**
     * Files the listing, uploading the photograph first when one is attached.
     *
     * <p>If the upload is rejected the listing is <em>not</em> submitted: the
     * form reports why and stays open, so the student never ends up with a
     * record claiming a photo exists when nothing reached the server.</p>
     */
    private void submitLostFound(android.app.AlertDialog dialog, android.widget.Button submit,
                                 LostFoundPhotoSlot slot, Spinner kind, Spinner category,
                                 EditText title, EditText description, EditText location) {
        if (title.length() < 2 || description.length() < 5 || location.length() < 2) {
            slot.status.setText("Add an item name, description and location.");
            return;
        }
        submit.setEnabled(false);
        final boolean withPhoto = slot.uploadBytes != null;
        slot.status.setText(withPhoto ? "Uploading photo…" : "Submitting…");

        ApiCallback filed = new ApiCallback() {
            @Override public void onSuccess(String json) {
                submit.setEnabled(true);
                dialog.dismiss();
                showToast("Your item is waiting for moderation.");
            }

            @Override public void onFailure(ApiFailure failure) {
                submit.setEnabled(true);
                slot.status.setText(failure.getMessage());
            }
        };

        if (!withPhoto) {
            api.submitLostFound(String.valueOf(kind.getSelectedItem()), title.getText().toString(),
                    description.getText().toString(), String.valueOf(category.getSelectedItem()),
                    location.getText().toString(), utcNow(), null, filed);
            return;
        }
        final byte[] photo = slot.uploadBytes;
        api.uploadLostFoundPhoto(photo, "image/jpeg", new ApiCallback() {
            @Override public void onSuccess(String json) {
                String reference = "";
                try {
                    reference = new JSONObject(json).optString("image_url", "");
                } catch (JSONException ignored) { }
                if (reference.isEmpty() || !LostFoundPhotos.isServerPhotoReference(reference)) {
                    submit.setEnabled(true);
                    slot.status.setText("The server did not return a usable photo reference, "
                            + "so nothing was submitted. Try again.");
                    return;
                }
                slot.status.setText("Submitting your item…");
                api.submitLostFound(String.valueOf(kind.getSelectedItem()), title.getText().toString(),
                        description.getText().toString(), String.valueOf(category.getSelectedItem()),
                        location.getText().toString(), utcNow(), reference, filed);
            }

            @Override public void onFailure(ApiFailure failure) {
                submit.setEnabled(true);
                slot.status.setText("Photo upload failed, so nothing was submitted. "
                        + failure.getMessage());
            }
        });
    }

    /**
     * Decodes the picked photo off the main thread, uprights it using the EXIF
     * orientation the camera recorded, and re-encodes it as a bounded JPEG.
     *
     * <p>Re-encoding is what keeps the upload inside the server's 5 MB limit and
     * guarantees the bytes really are JPEG, rather than hoping the picker's
     * source file happens to be small enough. Only those bytes are returned, so
     * the caller can preview exactly what will be sent.</p>
     *
     * @return the JPEG bytes to upload, or {@code null} if the source could not
     *         be read or encoded
     */
    private byte[] preparePhoto(Uri uri) {
        BitmapFactory.Options bounds = new BitmapFactory.Options();
        bounds.inJustDecodeBounds = true;
        try (java.io.InputStream probe = getContentResolver().openInputStream(uri)) {
            if (probe == null) return null;
            BitmapFactory.decodeStream(probe, null, bounds);
        } catch (Exception error) {
            return null;
        }
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null;

        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inSampleSize = sampleSize(bounds.outWidth, bounds.outHeight, MAX_PHOTO_SIDE);
        Bitmap decoded;
        try (java.io.InputStream source = getContentResolver().openInputStream(uri)) {
            if (source == null) return null;
            decoded = BitmapFactory.decodeStream(source, null, options);
        } catch (Exception error) {
            return null;
        }
        if (decoded == null) return null;

        Bitmap upright = applyExifOrientation(uri, decoded);
        Bitmap bounded = scaleDown(upright, MAX_PHOTO_SIDE);
        byte[] bytes;
        try {
            java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
            bounded.compress(Bitmap.CompressFormat.JPEG, 85, out);
            bytes = out.toByteArray();
        } catch (OutOfMemoryError error) {
            bounded.recycle();
            return null;
        }
        bounded.recycle();
        if (bytes.length == 0) return null;
        return bytes;
    }

    /** Rotates/flips the decoded bitmap to match the orientation EXIF records. */
    private Bitmap applyExifOrientation(Uri uri, Bitmap bitmap) {
        int orientation = ExifInterface.ORIENTATION_NORMAL;
        try (java.io.InputStream source = getContentResolver().openInputStream(uri)) {
            if (source != null) {
                orientation = new ExifInterface(source).getAttributeInt(
                        ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL);
            }
        } catch (Exception ignored) {
            // No EXIF block is normal for screenshots and downloaded images.
        }
        Matrix matrix = new Matrix();
        switch (orientation) {
            case ExifInterface.ORIENTATION_ROTATE_90: matrix.postRotate(90); break;
            case ExifInterface.ORIENTATION_ROTATE_180: matrix.postRotate(180); break;
            case ExifInterface.ORIENTATION_ROTATE_270: matrix.postRotate(270); break;
            case ExifInterface.ORIENTATION_FLIP_HORIZONTAL: matrix.postScale(-1, 1); break;
            case ExifInterface.ORIENTATION_FLIP_VERTICAL: matrix.postScale(1, -1); break;
            case ExifInterface.ORIENTATION_TRANSPOSE: matrix.postRotate(90); matrix.postScale(-1, 1); break;
            case ExifInterface.ORIENTATION_TRANSVERSE: matrix.postRotate(270); matrix.postScale(-1, 1); break;
            default: return bitmap;
        }
        try {
            Bitmap rotated = Bitmap.createBitmap(bitmap, 0, 0, bitmap.getWidth(), bitmap.getHeight(), matrix, true);
            if (rotated != bitmap) bitmap.recycle();
            return rotated;
        } catch (OutOfMemoryError error) {
            return bitmap;
        }
    }

    private static Bitmap scaleDown(Bitmap bitmap, int maxSide) {
        int longest = Math.max(bitmap.getWidth(), bitmap.getHeight());
        if (longest <= maxSide) return bitmap;
        Matrix matrix = new Matrix();
        matrix.postScale((float) maxSide / longest, (float) maxSide / longest);
        try {
            Bitmap scaled = Bitmap.createBitmap(bitmap, 0, 0, bitmap.getWidth(), bitmap.getHeight(), matrix, true);
            if (scaled != bitmap) bitmap.recycle();
            return scaled;
        } catch (OutOfMemoryError error) {
            return bitmap;
        }
    }

    /** Power-of-two {@code inSampleSize} that lands on or below {@code maxSide}. */
    private static int sampleSize(int width, int height, int maxSide) {
        int sample = 1;
        while (Math.max(width, height) / (sample * 2) >= maxSide) sample *= 2;
        return sample;
    }

    /** Decodes a photograph served by the backend, bounded to {@link #MAX_PHOTO_SIDE}. */
    private static Bitmap decodePhoto(byte[] bytes) {
        if (bytes == null || bytes.length == 0) return null;
        BitmapFactory.Options bounds = new BitmapFactory.Options();
        bounds.inJustDecodeBounds = true;
        BitmapFactory.decodeByteArray(bytes, 0, bytes.length, bounds);
        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inSampleSize = sampleSize(Math.max(bounds.outWidth, 1), Math.max(bounds.outHeight, 1), MAX_PHOTO_SIDE);
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
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

    /**
     * Same as {@link #resultCallback}, but always restores the submit button so a
     * failed or successful request never leaves the form permanently disabled.
     */
    private ApiCallback resultWithReenable(android.view.View button, TextView status,
                                           String success, String failureMessage) {
        return new ApiCallback() {
            private void settle(String text) {
                status.setText(text);
                button.setEnabled(true);
            }

            @Override public void onSuccess(String json) { settle(success); }
            @Override public void onFailure(ApiFailure failure) {
                String message = failure.getMessage();
                settle(message == null || message.isEmpty() ? failureMessage : message);
            }
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
        // MaterialCardView would otherwise fall back to Material3's baseline
        // surface container, which renders purple-tinted (#F2EFFA) and is
        // off-palette in this blue/teal app. Match the white surface the
        // sign-in cards already declare explicitly.
        card.setCardBackgroundColor(getColor(R.color.hydroguard_surface));
        card.setStrokeColor(getColor(R.color.hydroguard_divider));
        card.setStrokeWidth(dp(1));
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

    /**
     * Removes the whole card that {@link #addCard} created.
     *
     * <p>The returned text view is a child of the card's inner layout, not of
     * {@code parent}, so calling {@code parent.removeView(text)} silently does
     * nothing and a stale "Loading…" card stays on screen beside the real
     * content. Walk up to the {@link MaterialCardView} before removing.</p>
     */
    private void removeCard(LinearLayout parent, TextView text) {
        if (text == null) return;
        if (!(text.getParent() instanceof View)) return;
        View inner = (View) text.getParent();
        if (!(inner.getParent() instanceof View)) return;
        View card = (View) inner.getParent();
        if (card.getParent() == parent) parent.removeView(card);
    }

    /** {@code optString} reports a JSON null as the literal "null"; never show that. */
    private static String nonNullText(JSONObject item, String key) {
        if (item == null || item.isNull(key)) return "";
        String value = item.optString(key, "").trim();
        return "null".equalsIgnoreCase(value) ? "" : value;
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
        button.setBackgroundTintList(ColorStateList.valueOf(getColor(R.color.hydroguard_blue)));
        button.setTextColor(getColor(android.R.color.white));
        button.setCornerRadius(dp(12));
        try {
            button.setTypeface(ResourcesCompat.getFont(this, R.font.hydroguard_sans), Typeface.BOLD);
        } catch (Exception ignored) { }
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(48));
        params.setMargins(0, dp(4), 0, dp(4));
        parent.addView(button, params);
        return button;
    }

    private MaterialButton addSecondaryButton(LinearLayout parent, String label) {
        MaterialButton button = new MaterialButton(this, null, com.google.android.material.R.attr.materialButtonOutlinedStyle);
        button.setText(label); button.setAllCaps(false);
        button.setTextColor(getColor(R.color.hydroguard_blue));
        button.setStrokeColor(ColorStateList.valueOf(getColor(R.color.hydroguard_outline)));
        button.setStrokeWidth(dp(1));
        button.setCornerRadius(dp(12));
        try {
            button.setTypeface(ResourcesCompat.getFont(this, R.font.hydroguard_sans), Typeface.NORMAL);
        } catch (Exception ignored) { }
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
