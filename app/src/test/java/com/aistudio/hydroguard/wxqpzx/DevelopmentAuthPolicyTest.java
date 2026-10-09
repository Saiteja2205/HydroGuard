package com.aistudio.hydroguard.wxqpzx;

import com.aistudio.hydroguard.wxqpzx.data.repository.DevelopmentAuthPolicy;

import org.junit.Test;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public class DevelopmentAuthPolicyTest {
    @Test public void developmentSignInRequiresDebugAndExplicitFlag() {
        assertTrue(DevelopmentAuthPolicy.allows(true, true));
        assertFalse(DevelopmentAuthPolicy.allows(false, true));
        assertFalse(DevelopmentAuthPolicy.allows(true, false));
    }

    @Test public void apiBridgeAlsoRequiresAConfiguredToken() {
        assertTrue(DevelopmentAuthPolicy.apiBridgeConfigured(true, true, "dev-token"));
        assertFalse(DevelopmentAuthPolicy.apiBridgeConfigured(true, true, " "));
        assertFalse(DevelopmentAuthPolicy.apiBridgeConfigured(false, true, "dev-token"));
        assertFalse(DevelopmentAuthPolicy.apiBridgeConfigured(true, false, "dev-token"));
    }
}
