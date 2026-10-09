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
import java.util.Map;
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

    public void restoreSession(AuthCallback callback) {
        Map<String, String> debugIdentity = DevelopmentAuthPolicy.current();
        if (!debugIdentity.isEmpty()) {
            String email = debugIdentity.get("email");
            String role = debugIdentity.get("role");
            User user = developmentUser(email, role);
            io.execute(() -> {
                dao.insertUser(user);
                callback.onSuccess(user);
            });
            return;
        }
        FirebaseUser user = firebaseAuth == null ? null : firebaseAuth.getCurrentUser();
        if (user == null) {
            callback.onFailure("Sign in with your verified college Google account to continue.");
            return;
        }
        provisionFirebaseUser(user, callback);
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
                        callback.onFailure("The HydroGuard API returned an unexpected health response.");
                        return;
                    }
                    DevelopmentAuthPolicy.set(context, email, role);
                    User user = developmentUser(email, role);
                    io.execute(() -> {
                        dao.insertUser(user);
                        callback.onSuccess(user);
                    });
                } catch (JSONException error) {
                    callback.onFailure("The HydroGuard API returned an invalid health response.");
                }
            }
            @Override public void onFailure(ApiFailure failure) { callback.onFailure(failure.getMessage()); }
        });
    }

    public void signOut() {
        DevelopmentAuthPolicy.clear(context);
        if (firebaseAuth != null) firebaseAuth.signOut();
    }

    private void provisionFirebaseUser(FirebaseUser firebaseUser, AuthCallback callback) {
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

    private String firebaseErrorMessage(Exception error) {
        if (error == null) return "Google sign-in could not finish. Please try again.";
        return "Google sign-in could not finish (" + error.getClass().getSimpleName() + "). Check your Google account and try again.";
    }
}
