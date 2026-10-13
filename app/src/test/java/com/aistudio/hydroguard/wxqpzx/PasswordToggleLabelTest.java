package com.aistudio.hydroguard.wxqpzx;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotEquals;

/**
 * Regression test for the password eye's accessibility label.
 *
 * <p>Material Components 1.12 installs the toggle through
 * {@code PasswordToggleEndIconDelegate}, whose {@code getIconContentDescriptionResId()}
 * returns one fixed string resource. The icon drawable and its checked state do track the
 * real visibility, but the content description never changes, so a TalkBack user was told
 * "Show password" even while the password was plainly visible on screen.</p>
 *
 * <p>On-device evidence (Moto G64, API 35): tapping the eye correctly flipped the field
 * between masked and revealed, while the icon's content description stayed "Show password"
 * on all four consecutive taps.</p>
 */
public class PasswordToggleLabelTest {

    /** While masked, the eye offers to reveal. */
    @Test public void maskedFieldOffersToShow() {
        assertEquals("Show password", MainActivity.passwordToggleLabel(true));
    }

    /** Once revealed, the same eye must offer to hide again. */
    @Test public void revealedFieldOffersToHide() {
        assertEquals("Hide password", MainActivity.passwordToggleLabel(false));
    }

    /**
     * The two states must be worded differently. A label that reads the same both ways is
     * exactly the stale-description defect this guards against.
     */
    @Test public void labelsDifferBetweenStates() {
        assertNotEquals(MainActivity.passwordToggleLabel(true),
                MainActivity.passwordToggleLabel(false));
    }

    /**
     * Material's own description is the string the defect produced; the corrected label must
     * never regress to using it for the revealed state.
     */
    @Test public void revealedStateNeverReusesMaterialStaleWording() {
        assertNotEquals("Show password", MainActivity.passwordToggleLabel(false));
    }
}
