package com.aistudio.hydroguard.wxqpzx.data.repository;

import android.content.Context;
import android.util.Log;

import com.aistudio.hydroguard.wxqpzx.BuildConfig;
import com.aistudio.hydroguard.wxqpzx.data.api.ApiCallback;
import com.aistudio.hydroguard.wxqpzx.data.api.ApiFailure;
import com.aistudio.hydroguard.wxqpzx.data.api.ApiRepository;
import com.aistudio.hydroguard.wxqpzx.data.database.AppDatabase;
import com.aistudio.hydroguard.wxqpzx.data.database.HydroDao;
import com.aistudio.hydroguard.wxqpzx.data.database.User;
import com.google.android.gms.tasks.Tasks;
import com.google.firebase.auth.AuthCredential;
import com.google.firebase.auth.AuthResult;
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseUser;
import com.google.firebase.auth.GoogleAuthProvider;
import com.google.firebase.auth.GetTokenResult;

import org.json.JSONException;
import org.json.JSONObject;

import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class FirebaseAuthRepository {
    private static final String DEMO_STUDENT = "demo.student@hydroguard.local";
    private static final String DEMO_ADMIN = "demo.admin@hydroguard.local";
    private final Context context;
    private final HydroDao dao;
    private final ApiRepository api;
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private FirebaseAuth firebaseAuth;

    /**
     * Backend-verified role for the current session, or {@code null} when this process
     * has not verified one.
     *
     * <p>Deliberately {@code static}: each screen builds its own {@code HydroViewModel}
     * and therefore its own repository instance, but a signed-in session is one per app
     * process. Storing it per-instance would make the dashboard read {@code null} for a
     * role the login screen had just verified, bouncing every sign-in back to login.
     * It is memory-only and cleared by {@link #signOut()}, so it is never persisted and
     * never survives sign-out or process death.</p>
     */
    private static volatile String sessionRole;

    public FirebaseAuthRepository(Context context, AppDatabase database, ApiRepository apiRepository) {
        this.context = context.getApplicationContext();
        this.dao = database.hydroDao();
        this.api = apiRepository;
        try {
            firebaseAuth = FirebaseAuth.getInstance();
        } catch (Exception error) {
            Log.w("HydroGuardAuth", "Firebase initialization unavailable: " + error.getClass().getSimpleName());
        }
        DevelopmentAuthPolicy.restore(this.context, BuildConfig.DEBUG,
                BuildConfig.ALLOW_DEVELOPMENT_LOGIN, BuildConfig.DEVELOPMENT_API_TOKEN);
    }

    public boolean isFirebaseAvailable() { return firebaseAuth != null; }

    /**
     * Role verified during the current in-process session, or {@code null} when no
     * session has been verified on this process. This is the authoritative value the
     * UI must render from: the role passed through an Intent extra is untrusted
     * because it is not re-validated against the account that is actually signed in.
     */
    public String currentRole() {
        String role = sessionRole;
        return role == null || role.trim().isEmpty() ? null : role.trim();
    }

    /** Records the backend-verified role so protected screens can render from it. */
    private void rememberVerifiedRole(String role) {
        sessionRole = role == null ? null : role.trim().toUpperCase(Locale.ROOT);
    }

    private void forgetVerifiedRole() {
        sessionRole = null;
    }

    public void restoreSession(AuthCallback callback) {
        // A development identity is deliberately not restored here: demo sign-in is
        // only ever established by an explicit user action in loginAsDevelopment().
        // Restoring it automatically would bypass the login screen with "Demo Student".
        FirebaseUser user = firebaseAuth == null ? null : firebaseAuth.getCurrentUser();
        if (user == null) {
            callback.onFailure("Sign in with your verified college Google account to continue.");
            return;
        }
        provisionFirebaseUser(user, callback);
    }

    /** True when a real Firebase session or an explicitly started development session exists. */
    public boolean hasActiveSession() {
        if (!DevelopmentAuthPolicy.current().isEmpty()) return true;
        return firebaseAuth != null && firebaseAuth.getCurrentUser() != null;
    }

    public void signInWithGoogleIdToken(String idToken, AuthCallback callback) {
        if (firebaseAuth == null) {
            callback.onFailure("Firebase Authentication is not configured for this app.");
            return;
        }
        if (idToken == null || idToken.trim().isEmpty()) {
            callback.onFailure("Google did not return a sign-in token. Please try again.");
            return;
        }
        AuthCredential credential = GoogleAuthProvider.getCredential(idToken, null);
        firebaseAuth.signInWithCredential(credential).addOnCompleteListener(task -> {
            if (!task.isSuccessful() || task.getResult() == null || task.getResult().getUser() == null) {
                callback.onFailure(firebaseErrorMessage(task.getException()));
                return;
            }
            DevelopmentAuthPolicy.clear(context);
            provisionFirebaseUser(task.getResult().getUser(), callback);
        });
    }

    public void loginAsDevelopment(String requestedRole, AuthCallback callback) {
        if (!DevelopmentAuthPolicy.apiBridgeConfigured(BuildConfig.DEBUG,
                BuildConfig.ALLOW_DEVELOPMENT_LOGIN, BuildConfig.DEVELOPMENT_API_TOKEN)) {
            callback.onFailure("Development sign-in is unavailable in this build. Configure the local development token and rebuild the debug app.");
            return;
        }
        String role = requestedRole == null ? "" : requestedRole.trim().toUpperCase(Locale.ROOT);
        String email = "STUDENT".equals(role) ? DEMO_STUDENT : "ADMIN".equals(role) ? DEMO_ADMIN : null;
        if (email == null) {
            callback.onFailure("This development role is not supported.");
            return;
        }
        api.checkHealth(new ApiCallback() {
            @Override public void onSuccess(String json) {
                try {
                    if (!"ok".equalsIgnoreCase(new JSONObject(json).optString("status"))) {
                        callback.onFailure("Health check failed. The HydroGuard API responded but did not report status \"ok\".");
                        return;
                    }
                    DevelopmentAuthPolicy.set(context, email, role);
                    rememberVerifiedRole(role);
                    User user = developmentUser(email, role);
                    io.execute(() -> {
                        dao.insertUser(user);
                        callback.onSuccess(user);
                    });
                } catch (JSONException error) {
                    callback.onFailure("The HydroGuard API returned an invalid health response.");
                }
            }
            // Development sign-in never starts without a passing health check, so the
            // caller must be able to tell a health-check failure apart from a rejected
            // credential. failureMessage() already separates refusal, timeout, DNS and
            // HTTP errors; this prefix names the check that produced it.
            @Override public void onFailure(ApiFailure failure) {
                callback.onFailure("Health check failed. " + failure.getMessage());
            }
        });
    }

    public void signOut() {
        DevelopmentAuthPolicy.clear(context);
        forgetVerifiedRole();
        if (firebaseAuth != null) firebaseAuth.signOut();
    }

    public void loginWithEmail(String email, String password, AuthCallback callback) {
        if (firebaseAuth == null) {
            callback.onFailure("Firebase Authentication is not configured for this app.");
            return;
        }
        if (email == null || !android.util.Patterns.EMAIL_ADDRESS.matcher(email).matches()) {
            callback.onFailure("Please enter a valid email address.");
            return;
        }
        if (password == null || password.trim().isEmpty()) {
            callback.onFailure("Please enter a password.");
            return;
        }
        api.studentLogin(email, password, new ApiCallback() {
            @Override public void onSuccess(String json) {
                try {
                    JSONObject response = new JSONObject(json);
                    String token = response.optString("token", "");
                    if (token.isEmpty()) {
                        callback.onFailure("Authentication failed. No token received.");
                        return;
                    }
                    firebaseAuth.signInWithCustomToken(token).addOnCompleteListener(task -> {
                        if (!task.isSuccessful() || task.getResult() == null
                                || task.getResult().getUser() == null) {
                            callback.onFailure("Could not complete sign-in. Please try again.");
                            return;
                        }
                        DevelopmentAuthPolicy.clear(context);
                        provisionFirebaseUser(task.getResult().getUser(), callback);
                    });
                } catch (JSONException error) {
                    callback.onFailure("Invalid authentication response.");
                }
            }
            @Override public void onFailure(ApiFailure failure) {
                callback.onFailure(failure.getMessage());
            }
        });
    }

    public void registerStudent(String fullName, String email, String password, AuthCallback callback) {
        if (email == null || !android.util.Patterns.EMAIL_ADDRESS.matcher(email).matches()) {
            callback.onFailure("Please enter a valid college email address.");
            return;
        }
        String passwordIssue = passwordProblem(password);
        if (passwordIssue != null) {
            callback.onFailure(passwordIssue);
            return;
        }
        api.studentRegister(fullName, email, password, new ApiCallback() {
            @Override public void onSuccess(String json) {
                try {
                    JSONObject response = new JSONObject(json);
                    String token = response.optString("token", "");
                    if (token.isEmpty()) {
                        callback.onFailure("Registration failed. No token received.");
                        return;
                    }
                    firebaseAuth.signInWithCustomToken(token).addOnCompleteListener(task -> {
                        if (!task.isSuccessful() || task.getResult() == null
                                || task.getResult().getUser() == null) {
                            callback.onFailure("Could not complete sign-in. Please try again.");
                            return;
                        }
                        DevelopmentAuthPolicy.clear(context);
                        provisionFirebaseUser(task.getResult().getUser(), callback);
                    });
                } catch (JSONException error) {
                    callback.onFailure("Invalid registration response.");
                }
            }
            @Override public void onFailure(ApiFailure failure) {
                callback.onFailure(failure.getMessage());
            }
        });
    }

    private void provisionFirebaseUser(FirebaseUser firebaseUser, AuthCallback callback) {
        provisionFirebaseUserWithRetry(firebaseUser, 0, callback);
    }

    private void provisionFirebaseUserWithRetry(FirebaseUser firebaseUser, int attempt, AuthCallback callback) {
        if (firebaseUser == null) {
            callback.onFailure("Firebase did not return an authenticated account.");
            return;
        }
        firebaseUser.getIdToken(true).addOnCompleteListener(tokenTask -> {
            if (!tokenTask.isSuccessful()) {
                callback.onFailure("The sign-in session could not be refreshed. Please try again.");
                return;
            }
            api.bootstrapAccount(new ApiCallback() {
                @Override public void onSuccess(String json) {
                    try {
                        JSONObject account = new JSONObject(json);
                        String uid = account.optString("uid", "");
                        String email = account.optString("email", "").trim();
                        String role = account.optString("role", "").trim().toUpperCase(Locale.ROOT);
                        String status = account.optString("status", "");
                        if (!firebaseUser.getUid().equals(uid) || firebaseUser.getEmail() == null
                                || !firebaseUser.getEmail().equalsIgnoreCase(email)
                                || !("STUDENT".equals(role) || "ADMIN".equals(role))
                                || !"ACTIVE".equals(status)) {
                            firebaseAuth.signOut();
                            callback.onFailure("This Google account is not authorized for HydroGuard. Contact your administrator.");
                            return;
                        }
                        verifyRoleClaim(firebaseUser, role, account.optString("display_name", ""), email, callback);
                    } catch (JSONException error) {
                        callback.onFailure("HydroGuard returned an invalid account response.");
                    }
                }
                @Override public void onFailure(ApiFailure failure) {
                    if (attempt < 1 && failure.kind == ApiFailure.Kind.AUTHENTICATION) {
                        io.execute(() -> {
                            try {
                                Thread.sleep(1500);
                            } catch (InterruptedException ignored) {}
                            provisionFirebaseUserWithRetry(firebaseUser, attempt + 1, callback);
                        });
                        return;
                    }
                    if (failure.kind == ApiFailure.Kind.AUTHENTICATION) firebaseAuth.signOut();
                    callback.onFailure(failure.getMessage());
                }
            });
        });
    }

    private void verifyRoleClaim(FirebaseUser firebaseUser, String expectedRole, String displayName,
                                 String email, AuthCallback callback) {
        firebaseUser.getIdToken(true).addOnCompleteListener(task -> {
            if (!task.isSuccessful() || task.getResult() == null) {
                callback.onFailure("Account permissions are still updating. Please try again.");
                return;
            }
            Object claim = task.getResult().getClaims().get("role");
            if (!(claim instanceof String) || !expectedRole.equalsIgnoreCase((String) claim)) {
                callback.onFailure("Account permissions are still updating. Please try again.");
                return;
            }
            String name = displayName == null || displayName.trim().isEmpty()
                    ? firebaseUser.getDisplayName() : displayName;
            if (name == null || name.trim().isEmpty()) name = email.substring(0, email.indexOf('@'));
            // Cross-verified above: the backend account role must equal the Firebase
            // custom claim, so this role is safe to render privileged controls from.
            rememberVerifiedRole(expectedRole);
            User user = new User(email.toLowerCase(Locale.ROOT), name, expectedRole, "", "");
            io.execute(() -> {
                User existing = dao.getUserByEmail(email.toLowerCase(Locale.ROOT));
                if (existing != null) {
                    if (user.name == null || user.name.trim().isEmpty()) user.name = existing.name;
                    user.hostelBlock = existing.hostelBlock;
                    user.roomNumber = existing.roomNumber;
                }
                dao.insertUser(user);
                callback.onSuccess(user);
            });
        });
    }

    private User developmentUser(String email, String role) {
        String name = "ADMIN".equals(role) ? "Demo Administrator" : "Demo Student";
        return new User(email, name, role, "", "");
    }

    /** Mirrors the backend's single password message so the user sees one consistent rule. */
    private static final String PASSWORD_RULE =
            "Password must be at least 6 characters and contain at least one lowercase letter, "
                    + "one uppercase letter, one digit, and one special character.";

    /**
     * Validates a password against the rule the backend enforces in
     * {@code app.services.auth_service.validate_password_complexity}.
     *
     * <p>Character classes are matched with explicit ASCII ranges rather than
     * {@link Character#isLowerCase} so this accepts exactly what the server's
     * {@code [a-z] / [A-Z] / [0-9] / [^a-zA-Z0-9]} regular expressions accept.
     * A password is never trimmed: leading and trailing spaces are legal
     * characters, and trimming them here would make the client send a different
     * secret than the one the user typed.</p>
     *
     * @return {@code null} when the password is acceptable, otherwise the reason to show.
     */
    public static String passwordProblem(String password) {
        if (password == null || password.trim().isEmpty()) return "Please enter a password.";
        if (password.length() < 6 || password.length() > 128) return PASSWORD_RULE;
        boolean lower = false, upper = false, digit = false, symbol = false;
        for (int index = 0; index < password.length(); index++) {
            char character = password.charAt(index);
            if (character >= 'a' && character <= 'z') lower = true;
            else if (character >= 'A' && character <= 'Z') upper = true;
            else if (character >= '0' && character <= '9') digit = true;
            else symbol = true;
        }
        return lower && upper && digit && symbol ? null : PASSWORD_RULE;
    }

    private String firebaseErrorMessage(Exception error) {
        if (error == null) return "Google sign-in could not finish. Please try again.";
        return "Google sign-in could not finish (" + error.getClass().getSimpleName() + "). Check your Google account and try again.";
    }
}
