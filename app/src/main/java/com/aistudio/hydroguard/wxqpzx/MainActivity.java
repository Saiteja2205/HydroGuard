package com.aistudio.hydroguard.wxqpzx;

import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.View;
import android.widget.Button;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.Nullable;
import androidx.activity.ComponentActivity;
import androidx.credentials.Credential;
import androidx.credentials.CredentialManager;
import androidx.credentials.CustomCredential;
import androidx.credentials.GetCredentialRequest;
import androidx.credentials.GetCredentialResponse;
import androidx.credentials.exceptions.GetCredentialException;
import androidx.lifecycle.ViewModelProvider;

import com.aistudio.hydroguard.wxqpzx.data.database.User;
import com.aistudio.hydroguard.wxqpzx.data.repository.AuthCallback;
import com.aistudio.hydroguard.wxqpzx.data.repository.DevelopmentAuthPolicy;
import com.aistudio.hydroguard.wxqpzx.ui.viewmodel.HydroViewModel;
import com.google.android.libraries.identity.googleid.GetGoogleIdOption;
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential;
import com.google.firebase.FirebaseApp;

import java.util.concurrent.Executor;

public class MainActivity extends ComponentActivity {
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private HydroViewModel viewModel;
    private CredentialManager credentialManager;
    private TextView statusText;
    private ProgressBar progress;
    private Button googleButton;
    private boolean openingDashboard;

    @Override protected void onCreate(@Nullable Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        // targetSdk 36 draws edge-to-edge; pad the content clear of the system UI.
        com.aistudio.hydroguard.wxqpzx.ui.SystemInsets.apply(this);
        viewModel = new ViewModelProvider(this).get(HydroViewModel.class);
        credentialManager = CredentialManager.create(getApplicationContext());
        statusText = findViewById(R.id.login_status);
        progress = findViewById(R.id.login_progress);
        googleButton = findViewById(R.id.google_sign_in);
        googleButton.setOnClickListener(view -> beginGoogleSignIn());

        if (FirebaseApp.getApps(this).isEmpty()) {
            showMessage("Firebase configuration is missing. Check the Android Firebase project setup.");
        }



        if (BuildConfig.DEBUG && getIntent() != null && getIntent().hasExtra("demo_role")) {
            loginWithDemoRole(getIntent().getStringExtra("demo_role"));
            return;
        }

        // The launcher screen always starts unauthenticated: a development identity
        // from a previous run must never bypass this login screen.
        DevelopmentAuthPolicy.clear(this);
        if (getIntent() != null && getIntent().getBooleanExtra("sign_out", false)) {
            viewModel.logout();
            setLoading(false);
            setStatus("");
            return;
        }
        setLoading(true);
        viewModel.restoreSession(new AuthCallback() {
            @Override public void onSuccess(User user) { runOnUiThread(() -> openDashboard(user)); }
            @Override public void onFailure(String message) {
                runOnUiThread(() -> {
                    setLoading(false);
                    setStatus("");
                });
            }
        });
    }

    /**
     * Label for the password eye, describing what tapping it will do.
     *
     * <p>Kept as a pure function so the wording is locked down by a unit test. Material's own
     * description never changes with state, which is the defect this corrects.</p>
     *
     * @param masked whether the field is currently hiding the password.
     * @return "Show password" while masked, "Hide password" once revealed.
     */
    static String passwordToggleLabel(boolean masked) {
        return masked ? "Show password" : "Hide password";
    }

    private void beginGoogleSignIn() {
        if (!viewModel.isFirebaseAvailable()) {
            showMessage("Firebase Authentication is not configured for this app.");
            return;
        }
        setLoading(true);
        setStatus("Opening Google sign-in…");
        try {
            String clientId = getString(R.string.default_web_client_id);
            GetGoogleIdOption option = new GetGoogleIdOption.Builder()
                    .setServerClientId(clientId)
                    .setFilterByAuthorizedAccounts(false)
                    .setAutoSelectEnabled(false)
                    .build();
            GetCredentialRequest request = new GetCredentialRequest.Builder()
                    .addCredentialOption(option)
                    .build();
            Executor mainExecutor = command -> mainHandler.post(command);
            credentialManager.getCredentialAsync(this, request, null, mainExecutor,
                    new androidx.credentials.CredentialManagerCallback<GetCredentialResponse, GetCredentialException>() {
                        @Override public void onResult(GetCredentialResponse response) {
                            acceptGoogleCredential(response.getCredential());
                        }
                        @Override public void onError(GetCredentialException error) {
                            setLoading(false);
                            if (BuildConfig.DEBUG) Log.w("HydroGuardLogin", "Credential Manager failed: " + error.getClass().getSimpleName());
                            showMessage(credentialError(error));
                        }
                    });
        } catch (Exception error) {
            setLoading(false);
            if (BuildConfig.DEBUG) Log.w("HydroGuardLogin", "Could not open Google sign-in: " + error.getClass().getSimpleName());
            showMessage("Google sign-in could not start. Check your Google account and try again.");
        }
    }

    private void acceptGoogleCredential(Credential credential) {
        if (!(credential instanceof CustomCredential)
                || !GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL.equals(credential.getType())) {
            setLoading(false);
            showMessage("Google sign-in did not return a supported account credential.");
            return;
        }
        try {
            GoogleIdTokenCredential google = GoogleIdTokenCredential.createFrom(((CustomCredential) credential).getData());
            setStatus("Verifying your HydroGuard account…");
            viewModel.signInWithGoogleIdToken(google.getIdToken(), authCallback());
        } catch (RuntimeException error) {
            setLoading(false);
            showMessage("Google sign-in could not be read. Please try again.");
        }
    }

    private String credentialError(GetCredentialException error) {
        String type = error.getClass().getSimpleName();
        if (type.contains("Cancellation")) return "Google sign-in was cancelled.";
        if (type.contains("NoCredential")) return "No Google account is available. Add a Google account to this device and try again.";
        return "Google sign-in could not start. Check your Google account and try again.";
    }

    private AuthCallback authCallback() {
        return new AuthCallback() {
            @Override public void onSuccess(User user) { runOnUiThread(() -> openDashboard(user)); }
            @Override public void onFailure(String message) {
                runOnUiThread(() -> {
                    setLoading(false);
                    showMessage(message);
                });
            }
        };
    }

    private void openDashboard(User user) {
        if (openingDashboard || isFinishing()) return;
        openingDashboard = true;
        Intent intent = new Intent(this, DashboardActivity.class);
        if (getIntent() != null && getIntent().getExtras() != null) {
            intent.putExtras(getIntent().getExtras());
        }
        intent.putExtra(DashboardActivity.EXTRA_ROLE, user.role);
        intent.putExtra(DashboardActivity.EXTRA_EMAIL, user.email);
        intent.putExtra(DashboardActivity.EXTRA_NAME, user.name);
        startActivity(intent);
        finish();
    }

    private void setLoading(boolean loading) {
        progress.setVisibility(loading ? View.VISIBLE : View.GONE);
        googleButton.setEnabled(!loading);
    }

    /**
     * Drives the compact inline status strip. An empty message collapses it, so the
     * card never shows an oversized blank warning area above the sign-in controls.
     */
    private void setStatus(String message) {
        String text = message == null ? "" : message.trim();
        statusText.setText(text);
        statusText.setVisibility(text.isEmpty() ? View.GONE : View.VISIBLE);
    }

    private void showMessage(String message) {
        setStatus(message == null || message.trim().isEmpty()
                ? "Sign-in could not finish. Please try again." : message);
    }
    private void loginWithDemoRole(String requestedRole) {
        String roleUpper = (requestedRole == null ? "STUDENT" : requestedRole).trim().toUpperCase(java.util.Locale.ROOT);
        String customToken = getIntent() != null ? getIntent().getStringExtra("custom_token") : null;
        if (customToken != null && !customToken.trim().isEmpty()) {
            setLoading(true);
            setStatus("Authenticating Firebase session…");
            com.google.firebase.auth.FirebaseAuth.getInstance().signInWithCustomToken(customToken)
                    .addOnCompleteListener(task -> {
                        if (task.isSuccessful() && task.getResult() != null && task.getResult().getUser() != null) {
                            com.google.firebase.auth.FirebaseUser fbUser = task.getResult().getUser();
                            String email = fbUser.getEmail() != null ? fbUser.getEmail() : ("live.student." + roleUpper.toLowerCase(java.util.Locale.ROOT) + "@vrsec.ac.in");
                            DevelopmentAuthPolicy.clear(this);
                            User user = new User(email, "HydroGuard " + roleUpper, roleUpper, "", "");
                            runOnUiThread(() -> openDashboard(user));
                        } else {
                            fallbackDemoLogin(roleUpper);
                        }
                    });
            return;
        }

        com.google.firebase.auth.FirebaseUser existing = com.google.firebase.auth.FirebaseAuth.getInstance().getCurrentUser();
        if (existing != null) {
            String email = existing.getEmail() != null ? existing.getEmail() : ("live.student." + roleUpper.toLowerCase(java.util.Locale.ROOT) + "@vrsec.ac.in");
            DevelopmentAuthPolicy.clear(this);
            User user = new User(email, "HydroGuard " + roleUpper, roleUpper, "", "");
            openDashboard(user);
            return;
        }

        setLoading(true);
        setStatus("Provisioning live student session…");
        String liveEmail = "live.student." + (System.currentTimeMillis() % 1000000) + "@vrsec.ac.in";
        viewModel.registerStudent("Live Student", liveEmail, "LivePassword123!", new AuthCallback() {
            @Override
            public void onSuccess(User user) {
                User liveUser = new User(user.email, user.name, roleUpper, "", "");
                DevelopmentAuthPolicy.clear(MainActivity.this);
                runOnUiThread(() -> openDashboard(liveUser));
            }

            @Override
            public void onFailure(String message) {
                runOnUiThread(() -> fallbackDemoLogin(roleUpper));
            }
        });
    }

    private void fallbackDemoLogin(String roleUpper) {
        String demoEmail = "ADMIN".equals(roleUpper) ? "demo.admin@hydroguard.local" : "demo.student@hydroguard.local";
        String demoName = "ADMIN".equals(roleUpper) ? "Demo Administrator" : "Demo Student";
        DevelopmentAuthPolicy.set(this, demoEmail, roleUpper);
        User user = new User(demoEmail, demoName, roleUpper, "", "");
        java.util.concurrent.Executors.newSingleThreadExecutor().execute(() -> {
            try {
                com.aistudio.hydroguard.wxqpzx.data.database.AppDatabase.getDatabase(getApplicationContext())
                        .hydroDao().insertUser(user);
            } catch (Exception ignored) { }
        });
        openDashboard(user);
    }
}
