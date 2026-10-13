package com.aistudio.hydroguard.wxqpzx.ui;

import android.app.Activity;
import android.view.View;

import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;

/**
 * Keeps app content clear of the status bar, the display cutout and the gesture/ navigation bar.
 *
 * <p>HydroGuard targets SDK 36, where Android draws every window edge-to-edge and ignores the
 * old {@code android:statusBarColor} opt-out. Nothing in this project used to apply window
 * insets, so headings, the brand lockup and the bottom navigation sat underneath the system UI.
 * This helper draws behind the bars (as the platform now requires) and then pads the activity's
 * content view by the reported insets, which is what actually removes the overlap.</p>
 *
 * <p>The insets are handed back to the view hierarchy unchanged so the soft-keyboard insets still
 * reach the window and {@code android:windowSoftInputMode="adjustResize"} on the sign-in screen
 * keeps behaving exactly as it did before. Only system bars and cutouts are absorbed here.</p>
 *
 * <p>Two entry points:</p>
 * <ul>
 *   <li>{@link #apply(Activity)} — pad every edge. Used by the sign-in screen, which is a plain
 *       light surface with no chrome to run behind the bars.</li>
 *   <li>{@link #applyForTopBar(Activity, View)} — pad left, right and bottom only, and give
 *       {@code topBar} the status-bar height as its own top padding instead. The bar's navy
 *       background then covers the status-bar strip edge-to-edge (which {@code statusBarColor}
 *       cannot do on Android 15), its contents sit below the system icons, and the status icons
 *       are switched to light so they stay legible on navy.</li>
 * </ul>
 *
 * <p>Call once per activity, immediately after {@code setContentView}.</p>
 */
public final class SystemInsets {

    private SystemInsets() {
    }

    /** Pad the whole content view by the system-bar and cutout insets. */
    public static void apply(Activity activity) {
        applyInternal(activity, null);
    }

    /**
     * Draw {@code topBar} behind the status bar and cutout while keeping every other child clear
     * of the system UI. Pass the bar that should absorb the top inset; it must be a direct child of
     * the view returned by {@code setContentView}, first in reading order.
     */
    public static void applyForTopBar(Activity activity, View topBar) {
        if (activity == null || topBar == null) {
            apply(activity);
            return;
        }
        applyInternal(activity, topBar);
    }

    private static void applyInternal(Activity activity, View topBar) {
        if (activity == null) return;
        // Enforced for targetSdk 35+; setting it explicitly keeps older devices consistent.
        WindowCompat.setDecorFitsSystemWindows(activity.getWindow(), false);

        View content = activity.findViewById(android.R.id.content);
        if (content == null) return;

        // Captured before the listener runs so repeated inset passes stay idempotent — the bar's
        // own design padding is added to, never accumulated on top of an already-adjusted value.
        final int barPaddingStart = topBar == null ? 0 : topBar.getPaddingStart();
        final int barPaddingTop = topBar == null ? 0 : topBar.getPaddingTop();
        final int barPaddingEnd = topBar == null ? 0 : topBar.getPaddingEnd();
        final int barPaddingBottom = topBar == null ? 0 : topBar.getPaddingBottom();

        if (topBar != null) {
            // Navy under the status bar means the clock and battery icons must be light.
            WindowInsetsControllerCompat controller =
                    WindowCompat.getInsetsController(activity.getWindow(), topBar);
            controller.setAppearanceLightStatusBars(false);
            // The gesture bar sits under the light bottom navigation, so its icons stay dark.
            controller.setAppearanceLightNavigationBars(true);
        }

        ViewCompat.setOnApplyWindowInsetsListener(content, (view, insets) -> {
            Insets bars = insets.getInsets(
                    WindowInsetsCompat.Type.systemBars() | WindowInsetsCompat.Type.displayCutout());
            int top = topBar == null ? bars.top : 0;
            if (view.getPaddingLeft() != bars.left
                    || view.getPaddingTop() != top
                    || view.getPaddingRight() != bars.right
                    || view.getPaddingBottom() != bars.bottom) {
                view.setPadding(bars.left, top, bars.right, bars.bottom);
            }
            if (topBar != null) {
                topBar.setPadding(barPaddingStart, barPaddingTop + bars.top,
                        barPaddingEnd, barPaddingBottom);
            }
            // Deliberately not CONSUMED: children (and adjustResize) still need the IME insets.
            return insets;
        });
        ViewCompat.requestApplyInsets(content);
    }
}
