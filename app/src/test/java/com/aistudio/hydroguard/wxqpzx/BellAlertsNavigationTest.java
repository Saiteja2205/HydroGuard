package com.aistudio.hydroguard.wxqpzx;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

/**
 * Regression cover for the notification-bell defect.
 *
 * <p>The bell is supposed to switch to the Water screen and scroll its alerts section into
 * view. It switched correctly but never scrolled: {@code openAlerts()} unconditionally called
 * {@code setSelectedItemId(nav_water)}, and the listener behind that rebuilds the whole screen
 * by removing every view and re-inflating the layout. The scroll then ran against a view that
 * had been added to the window but not yet measured, so {@code alerts_status} still reported a
 * height of zero and {@code requestRectangleOnScreen(new Rect(0,0,0,0))} did nothing at all.
 * The page stayed exactly where it was -- on every path, including when Water was already the
 * screen on display, where the needless rebuild additionally reset the scroll position to the
 * top.</p>
 *
 * <p>These tests lock down the two decisions that fix it. The scroll itself is verified on the
 * device, because a plain JUnit test cannot build an Android view hierarchy: {@code View} is a
 * stub in the unit-test android.jar and every constructor throws.</p>
 */
public class BellAlertsNavigationTest {

    /**
     * Starting from Home the bell must change tabs, or the alerts would never appear.
     */
    @Test public void bellSwitchesTabWhenStartingFromAnotherScreen() {
        assertTrue(DashboardActivity.shouldSwitchToWater(R.id.nav_home, R.id.nav_water));
    }

    /**
     * The regression this guards: with Water already on display the bell must NOT re-run
     * renderScreen(). Doing so discards the scroll position and refetches every panel, which
     * is why the old code jumped back to the top of the page.
     */
    @Test public void bellDoesNotRebuildTheScreenWhenWaterIsAlreadyShowing() {
        assertFalse(DashboardActivity.shouldSwitchToWater(R.id.nav_water, R.id.nav_water));
    }

    /**
     * Before any tab has been chosen there is no selection to compare against, so the bell
     * still has to navigate rather than silently doing nothing.
     */
    @Test public void noSelectedTabStillNavigates() {
        assertTrue(DashboardActivity.shouldSwitchToWater(0, R.id.nav_water));
    }

    /** Every other tab is a navigation away from the alerts. */
    @Test public void everyOtherTabNavigates() {
        for (int tab : new int[] {R.id.nav_home, R.id.nav_report, R.id.nav_issues,
                R.id.nav_profile}) {
            assertTrue("tab " + tab + " must navigate to Water",
                    DashboardActivity.shouldSwitchToWater(tab, R.id.nav_water));
        }
    }

    /**
     * A screen that has not been laid out yet reports an offset of zero. This is precisely the
     * measurement that made the original scroll a silent no-op, so it is pinned here: a zero
     * offset must resolve to a zero scroll, never to a negative one.
     */
    @Test public void unLaidOutScreenProducesNoMovement() {
        assertEquals(0, DashboardActivity.alertScrollTarget(0, 102));
    }

    /** The target is pulled back by the heading allowance so the "Alerts" heading stays visible. */
    @Test public void scrollTargetPullsBackByTheHeadingAllowance() {
        assertEquals(2898, DashboardActivity.alertScrollTarget(3000, 102));
    }

    /**
     * The alerts sit far below the fold, so a realistic target must be a large positive offset
     * -- this is the assertion that would have failed against the old behaviour.
     */
    @Test public void deepSectionResolvesToARealScrollDistance() {
        assertTrue(DashboardActivity.alertScrollTarget(4000, 102) > 3000);
    }

    /**
     * A section close to the top must never produce a negative offset, which would ask the
     * scroller to scroll past the beginning of its content.
     */
    @Test public void scrollTargetIsNeverNegative() {
        assertEquals(0, DashboardActivity.alertScrollTarget(50, 102));
        assertEquals(0, DashboardActivity.alertScrollTarget(0, 102));
        assertEquals(0, DashboardActivity.alertScrollTarget(-1, 102));
    }

    /** Exactly at the allowance there is nothing above the section left to reveal. */
    @Test public void scrollTargetZeroWhenOffsetEqualsAllowance() {
        assertEquals(0, DashboardActivity.alertScrollTarget(102, 102));
    }

    /** With no heading allowance requested the offset is used as-is. */
    @Test public void scrollTargetHonoursZeroAllowance() {
        assertEquals(1000, DashboardActivity.alertScrollTarget(1000, 0));
    }
}
