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
    private Button demoStudentButton;
    private Button demoAdminButton;
    private boolean openingDashboard;

    @Override protected void onCreate(@Nullable Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        viewModel = new ViewModelProvider(this).get(HydroViewModel.class);
        credentialManager = CredentialManager.create(getApplicationContext());
        statusText = findViewById(R.id.login_status);
        progress = findViewById(R.id.login_progress);
        googleButton = findViewById(R.id.google_sign_in);
        demoStudentButton = findViewById(R.id.demo_student_sign_in);
        demoAdminButton = findViewById(R.id.demo_admin_sign_in);

        boolean showDevelopment = DevelopmentAuthPolicy.apiBridgeConfigured(
                BuildConfig.DEBUG, BuildConfig.ALLOW_DEVELOPMENT_LOGIN, BuildConfig.DEVELOPMENT_API_TOKEN);
        findViewById(R.id.development_login_group).setVisibility(showDevelopment ? View.VISIBLE : View.GONE);
        googleButton.setOnClickListener(view -> beginGoogleSignIn());
        demoStudentButton.setOnClickListener(view -> beginDevelopmentSignIn("STUDENT"));
        demoAdminButton.setOnClickListener(view -> beginDevelopmentSignIn("ADMIN"));

        if (FirebaseApp.getApps(this).isEmpty()) {
            showMessage("Firebase configuration is missing. Check the Android Firebase project setup.");
        }
        setLoading(true);
        viewModel.restoreSession(new AuthCallback() {
            @Override public void onSuccess(User user) { runOnUiThread(() -> openDashboard(user)); }
            @Override public void onFailure(String message) {
                runOnUiThread(() -> {
                    setLoading(false);
                    statusText.setText("");
                });
            }
        });
    }

    private void beginGoogleSignIn() {
        if (!viewModel.isFirebaseAvailable()) {
            showMessage("Firebase Authentication is not configured for this app.");
            return;
        }
        setLoading(true);
        statusText.setText("Opening Google sign-in…");
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
            statusText.setText("Verifying your HydroGuard account…");
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

    private void beginDevelopmentSignIn(String role) {
        setLoading(true);
        statusText.setText("Checking the development API and signing in…");
        viewModel.developmentLogin(role, authCallback());
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
        intent.putExtra(DashboardActivity.EXTRA_ROLE, user.role);
        intent.putExtra(DashboardActivity.EXTRA_EMAIL, user.email);
        intent.putExtra(DashboardActivity.EXTRA_NAME, user.name);
        startActivity(intent);
        finish();
    }

    private void setLoading(boolean loading) {
        progress.setVisibility(loading ? View.VISIBLE : View.GONE);
        googleButton.setEnabled(!loading);
        demoStudentButton.setEnabled(!loading);
        demoAdminButton.setEnabled(!loading);
    }

    private void showMessage(String message) {
        statusText.setText(message == null ? "Sign-in could not finish. Please try again." : message);
    }
}
