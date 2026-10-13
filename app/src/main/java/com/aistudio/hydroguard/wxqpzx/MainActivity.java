package com.aistudio.hydroguard.wxqpzx;

import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.TextWatcher;
import android.text.method.PasswordTransformationMethod;
import android.util.Log;
import android.view.View;
import android.widget.Button;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.Nullable;
import androidx.activity.ComponentActivity;
import androidx.appcompat.widget.AppCompatEditText;
import androidx.credentials.Credential;
import androidx.credentials.CredentialManager;
import androidx.credentials.CustomCredential;
import androidx.credentials.GetCredentialRequest;
import androidx.credentials.GetCredentialResponse;
import androidx.credentials.exceptions.GetCredentialException;
import androidx.lifecycle.ViewModelProvider;

import com.google.android.material.textfield.TextInputLayout;

import com.aistudio.hydroguard.wxqpzx.data.database.User;
import com.aistudio.hydroguard.wxqpzx.data.repository.AuthCallback;
import com.aistudio.hydroguard.wxqpzx.data.repository.DevelopmentAuthPolicy;
import com.aistudio.hydroguard.wxqpzx.data.repository.FirebaseAuthRepository;
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
    private AppCompatEditText emailField;
    private AppCompatEditText passwordField;
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
        demoStudentButton = findViewById(R.id.demo_student_sign_in);
        demoAdminButton = findViewById(R.id.demo_admin_sign_in);
        emailField = findViewById(R.id.email_address);
        passwordField = findViewById(R.id.password_field);

        boolean showDevelopment = DevelopmentAuthPolicy.apiBridgeConfigured(
                BuildConfig.DEBUG, BuildConfig.ALLOW_DEVELOPMENT_LOGIN, BuildConfig.DEVELOPMENT_API_TOKEN);
        findViewById(R.id.development_login_group).setVisibility(showDevelopment ? View.VISIBLE : View.GONE);
        findViewById(R.id.email_login_group).setVisibility(View.VISIBLE);
        googleButton.setOnClickListener(view -> beginGoogleSignIn());
        demoStudentButton.setOnClickListener(view -> beginDevelopmentSignIn("STUDENT"));
        demoAdminButton.setOnClickListener(view -> beginDevelopmentSignIn("ADMIN"));

        findViewById(R.id.email_sign_in_button).setOnClickListener(view -> performEmailLogin());
        findViewById(R.id.register_button).setOnClickListener(view -> performRegistration());
        keepPasswordToggleLabelInSync();

        if (FirebaseApp.getApps(this).isEmpty()) {
            showMessage("Firebase configuration is missing. Check the Android Firebase project setup.");
        }
        // The launcher screen always starts unauthenticated: a development identity
        // from a previous run must never bypass this login screen.
        DevelopmentAuthPolicy.clear(this);
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
     * Keeps the password eye's accessibility label describing what tapping it will do.
     *
     * <p>Material Components 1.12 wires the toggle in
     * {@code PasswordToggleEndIconDelegate}, whose {@code getIconContentDescriptionResId()}
     * returns one fixed string resource. The icon's drawable and its {@code checked} state do
     * follow the real visibility, but the content description never changes, so a TalkBack user
     * hears "Show password" even while the password is plainly on screen.</p>
     *
     * <p>This only rewrites the description; it deliberately does not install a click listener,
     * because replacing the delegate's own listener would silently break the toggle. The sync is
     * driven from a text watcher because {@code TextView.setTransformationMethod} re-sets the
     * text, so every reveal/mask fires one. The check itself asks the field whether it is still
     * using {@link PasswordTransformationMethod}, so the label can never drift from the truth.</p>
     */
    private void keepPasswordToggleLabelInSync() {
        TextInputLayout layout = null;
        // The EditText is not a direct child of the TextInputLayout: Material wraps it in an
        // internal FrameLayout ("editFrame"), so walk up until the wrapper is found.
        for (android.view.ViewParent parent = passwordField.getParent(); parent instanceof View;
                parent = ((View) parent).getParent()) {
            if (parent instanceof TextInputLayout) {
                layout = (TextInputLayout) parent;
                break;
            }
        }
        if (layout == null) return;
        final TextInputLayout host = layout;
        Runnable sync = () -> host.setEndIconContentDescription(
                passwordToggleLabel(passwordField.getTransformationMethod()
                        instanceof PasswordTransformationMethod));
        passwordField.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int a, int b, int c) { }
            @Override public void onTextChanged(CharSequence s, int a, int b, int c) { }
            @Override public void afterTextChanged(Editable s) { sync.run(); }
        });
        passwordField.post(sync);
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

    private void performEmailLogin() {
        String email = emailField.getText().toString().trim();
        // The password is deliberately NOT trimmed: leading and trailing spaces are
        // legal password characters, and trimming sent a different secret than the
        // one the user typed, which showed up as an unexplained sign-in failure.
        String password = passwordField.getText().toString();
        if (email.isEmpty() || !android.util.Patterns.EMAIL_ADDRESS.matcher(email).matches()) {
            showMessage("Please enter a valid college email address.");
            return;
        }
        if (password.trim().isEmpty()) {
            showMessage("Please enter your password.");
            return;
        }
        setLoading(true);
        viewModel.loginWithEmail(email, password, new AuthCallback() {
            @Override public void onSuccess(User user) { runOnUiThread(() -> openDashboard(user)); }
            @Override public void onFailure(String message) {
                runOnUiThread(() -> {
                    setLoading(false);
                    showMessage(message);
                });
            }
        });
    }

    private void performRegistration() {
        String email = emailField.getText().toString().trim();
        // Never trim the password: the backend hashes exactly what is sent, so a
        // trimmed value would create an account whose real password is unknown.
        String password = passwordField.getText().toString();
        if (email.isEmpty() || !android.util.Patterns.EMAIL_ADDRESS.matcher(email).matches()) {
            showMessage("Please enter a valid college email address.");
            return;
        }
        String passwordIssue = FirebaseAuthRepository.passwordProblem(password);
        if (passwordIssue != null) {
            showMessage(passwordIssue);
            return;
        }
        setLoading(true);
        viewModel.registerStudent(null, email, password, new AuthCallback() {
            @Override public void onSuccess(User user) { runOnUiThread(() -> openDashboard(user)); }
            @Override public void onFailure(String message) {
                runOnUiThread(() -> {
                    setLoading(false);
                    showMessage(message);
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

    private void beginDevelopmentSignIn(String role) {
        setLoading(true);
        setStatus("Checking the development API and signing in…");
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
        findViewById(R.id.email_sign_in_button).setEnabled(!loading);
        findViewById(R.id.register_button).setEnabled(!loading);
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
}