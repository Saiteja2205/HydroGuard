package com.aistudio.hydroguard.wxqpzx;

import com.aistudio.hydroguard.wxqpzx.data.repository.FirebaseAuthRepository;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;

/**
 * Regression tests for the password rule mirrored from the backend.
 *
 * <p>Two defects are covered here. The client used to accept any password of six
 * or more characters, so "abcdef" passed local validation, was sent to the
 * server, and came back as an unexplained HTTP 400. Separately, both the login
 * and registration paths called {@code trim()} on the password, so a secret with
 * a legal leading or trailing space was silently changed before it was sent.</p>
 */
public class PasswordRuleTest {

    /** The exact message the backend returns from validate_password_complexity(). */
    private static final String RULE =
            "Password must be at least 6 characters and contain at least one lowercase letter, "
                    + "one uppercase letter, one digit, and one special character.";

    @Test public void acceptsPasswordWithEveryRequiredClass() {
        assertNull(FirebaseAuthRepository.passwordProblem("Abcdef1!"));
    }

    @Test public void rejectsPasswordThatOnlyMeetsTheOldLengthCheck() {
        // The pre-fix client accepted this and let the server reject it.
        assertEquals(RULE, FirebaseAuthRepository.passwordProblem("abcdef"));
    }

    @Test public void rejectsMissingLowercase() {
        assertEquals(RULE, FirebaseAuthRepository.passwordProblem("ABCDEF1!"));
    }

    @Test public void rejectsMissingUppercase() {
        assertEquals(RULE, FirebaseAuthRepository.passwordProblem("abcdef1!"));
    }

    @Test public void rejectsMissingDigit() {
        assertEquals(RULE, FirebaseAuthRepository.passwordProblem("Abcdefg!"));
    }

    @Test public void rejectsMissingSymbol() {
        assertEquals(RULE, FirebaseAuthRepository.passwordProblem("Abcdefg1"));
    }

    @Test public void rejectsShortPassword() {
        assertEquals(RULE, FirebaseAuthRepository.passwordProblem("Ab1!"));
    }

    @Test public void rejectsOverlongPasswordMatchingTheServerLimit() {
        // The schema caps password at 128 characters; 129 must fail here rather
        // than surface as a bare HTTP 422.
        StringBuilder overlong = new StringBuilder("Ab1!");
        while (overlong.length() <= 128) overlong.append('a');
        assertEquals(RULE, FirebaseAuthRepository.passwordProblem(overlong.toString()));
    }

    @Test public void acceptsPasswordAtExactlyTheMinimumLength() {
        assertNull(FirebaseAuthRepository.passwordProblem("Ab1!xy"));
    }

    @Test public void rejectsBlankPassword() {
        assertEquals("Please enter a password.", FirebaseAuthRepository.passwordProblem("      "));
        assertEquals("Please enter a password.", FirebaseAuthRepository.passwordProblem(""));
        assertEquals("Please enter a password.", FirebaseAuthRepository.passwordProblem(null));
    }

    /**
     * Spaces inside a password are legal and must not be stripped: the value
     * validated here is the same value sent to the server.
     */
    @Test public void preservesLeadingTrailingAndInternalSpaces() {
        assertNull(FirebaseAuthRepository.passwordProblem(" Ab1!xy "));
        assertNull(FirebaseAuthRepository.passwordProblem("Ab1! xy"));
    }

    /** A space is not one of [a-zA-Z0-9], so it counts as the required symbol. */
    @Test public void spaceSatisfiesTheSymbolRequirement() {
        assertNull(FirebaseAuthRepository.passwordProblem("Abcdef1 "));
    }
}
