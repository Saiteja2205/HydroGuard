package com.example.ui.screens

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.util.Log
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.GetCredentialException
import androidx.credentials.exceptions.NoCredentialException
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Error
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import com.example.BuildConfig
import com.example.R
import com.example.ui.components.HydroCard
import com.example.ui.components.StatusChip
import com.example.ui.components.StatusTone
import com.example.ui.theme.CriticalRed
import com.example.ui.theme.CoolWhite
import com.example.ui.theme.HydroGuardShapes
import com.example.ui.theme.SlateBlueSubtle
import com.example.ui.theme.CobaltBlue
import com.example.ui.theme.GlassBorderDark
import com.example.ui.theme.GlassBorderLight
import com.example.ui.viewmodel.HydroViewModel
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.google.android.libraries.identity.googleid.GoogleIdTokenParsingException

private tailrec fun Context.findActivity(): Activity? = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.findActivity()
    else -> null
}

@Composable
fun LoginScreen(
    viewModel: HydroViewModel,
    onLoginSuccess: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    val isDark = isSystemInDarkTheme()
    val context = LocalContext.current
    val loginError by viewModel.loginError.collectAsState()
    val currentUser by viewModel.currentUser.collectAsState()
    val isFirebaseAvailable by viewModel.isFirebaseAvailable.collectAsState()
    var signingIn by remember { mutableStateOf(false) }
    val credentialManager = remember(context) { CredentialManager.create(context) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(currentUser) { currentUser?.let { onLoginSuccess(it.role) } }

    fun startGoogleSignIn() {
        viewModel.clearLoginError()
        if (!isFirebaseAvailable) {
            viewModel.showLoginError("Google Sign-In is currently unavailable.")
            return
        }
        val activity = context.findActivity()
        if (activity == null) {
            viewModel.showLoginError("Google Sign-In couldn't be opened. Please try again.")
            return
        }
        val serverClientId = context.getString(R.string.default_web_client_id)

        signingIn = true
        scope.launch {
            try {
                val credential = credentialManager.getCredential(
                    activity,
                    GetCredentialRequest.Builder()
                        .addCredentialOption(
                            GetGoogleIdOption.Builder()
                                .setServerClientId(serverClientId)
                                .setFilterByAuthorizedAccounts(false)
                                .setAutoSelectEnabled(false)
                                .build()
                        )
                        .build()
                ).credential
                if (credential !is CustomCredential || credential.type != GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL) {
                    viewModel.showLoginError("Google sign-in couldn't finish. Please try again.")
                    return@launch
                }
                val googleCredential = GoogleIdTokenCredential.createFrom(credential.data)
                viewModel.signInWithGoogleIdToken(googleCredential.idToken).join()
            } catch (_: GetCredentialCancellationException) {
                viewModel.clearLoginError()
            } catch (_: NoCredentialException) {
                if (BuildConfig.DEBUG) Log.w("LoginScreen", "No Google credential available from Credential Manager.")
                viewModel.showLoginError("No Google account is available. Add a Google account to this device and try again.")
            } catch (_: GoogleIdTokenParsingException) {
                viewModel.showLoginError("Google sign-in couldn't finish. Please try again.")
            } catch (exception: GetCredentialException) {
                if (BuildConfig.DEBUG) Log.w("LoginScreen", "Credential Manager failed (${exception.javaClass.simpleName}).")
                viewModel.showLoginError("Google Sign-In couldn't start. Check your Google account and try again.")
            } catch (exception: Exception) {
                if (BuildConfig.DEBUG) Log.w("LoginScreen", "Google Sign-In failed (${exception.javaClass.simpleName}).")
                viewModel.showLoginError("Google sign-in couldn't finish. Please try again.")
            } finally {
                signingIn = false
            }
        }
    }

    fun startDevelopmentSignIn(role: String) {
        viewModel.clearLoginError()
        signingIn = true
        scope.launch {
            try {
                viewModel.developmentLogin(role)
            } finally {
                signingIn = false
            }
        }
    }

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState()),
        contentAlignment = Alignment.Center
    ) {
        Column(
            modifier = Modifier
                .padding(horizontal = 20.dp, vertical = 24.dp)
                .fillMaxWidth()
                .widthIn(max = 440.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Image(
                painter = painterResource(R.drawable.hydroguard_ai_logo),
                contentDescription = "HydroGuard",
                modifier = Modifier.size(64.dp)
            )
            Spacer(Modifier.height(18.dp))
            Text(
                text = "HydroGuard",
                style = MaterialTheme.typography.displaySmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onSurface,
                textAlign = TextAlign.Center,
                letterSpacing = (-1).sp
            )
            Text(
                text = "Smart Hostel Water Intelligence Platform",
                style = MaterialTheme.typography.bodyLarge,
                color = SlateBlueSubtle,
                textAlign = TextAlign.Center
            )
            Spacer(Modifier.height(14.dp))
            StatusChip(
                label = if (isFirebaseAvailable) "Continue with your Google account" else "Sign-in unavailable",
                tone = if (isFirebaseAvailable) StatusTone.NEUTRAL else StatusTone.ATTENTION
            )
            Spacer(Modifier.height(20.dp))

            HydroCard(modifier = Modifier.fillMaxWidth(), shape = HydroGuardShapes.large) {
                Column(
                    modifier = Modifier.padding(20.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        text = "Welcome to HydroGuard",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.ExtraBold,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Spacer(Modifier.height(2.dp))
                    Text(
                        text = "Sign in to view water updates and hostel services",
                        style = MaterialTheme.typography.bodySmall,
                        color = SlateBlueSubtle,
                        textAlign = TextAlign.Center
                    )
                    Spacer(Modifier.height(20.dp))

                    if (loginError != null) {
                        Card(
                            colors = CardDefaults.cardColors(containerColor = CriticalRed.copy(alpha = 0.1f)),
                            shape = RoundedCornerShape(12.dp),
                            border = BorderStroke(1.dp, CriticalRed.copy(alpha = 0.3f)),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Row(
                                modifier = Modifier.padding(12.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                Icon(Icons.Default.Error, contentDescription = "Sign-in error", tint = CriticalRed)
                                Text(
                                    text = loginError.orEmpty(),
                                    color = CriticalRed,
                                    style = MaterialTheme.typography.bodySmall,
                                    fontWeight = FontWeight.Bold,
                                    modifier = Modifier.weight(1f)
                                )
                            }
                        }
                        Spacer(Modifier.height(16.dp))
                    }

                    Button(
                        onClick = ::startGoogleSignIn,
                        enabled = !signingIn,
                        modifier = Modifier.fillMaxWidth().height(50.dp).testTag("google_sign_in_button"),
                        shape = HydroGuardShapes.button,
                        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary)
                    ) {
                        if (signingIn) {
                            CircularProgressIndicator(Modifier.size(18.dp), color = CoolWhite, strokeWidth = 2.dp)
                            Spacer(Modifier.width(10.dp))
                        }
                        Text(
                            text = if (signingIn) "Connecting…" else "Sign in with Google",
                            fontWeight = FontWeight.Bold,
                            fontSize = 15.sp,
                            color = CoolWhite
                        )
                    }

                    if (BuildConfig.DEBUG && BuildConfig.ALLOW_DEVELOPMENT_LOGIN) {
                        Spacer(Modifier.height(18.dp))
                        HorizontalDivider(color = if (isDark) GlassBorderDark else GlassBorderLight)
                        Spacer(Modifier.height(14.dp))
                        Text("DEVELOPMENT LOGIN", style = MaterialTheme.typography.labelSmall, color = SlateBlueSubtle, letterSpacing = 1.sp)
                        Spacer(Modifier.height(10.dp))
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            OutlinedButton(
                                onClick = { startDevelopmentSignIn("STUDENT") },
                                enabled = !signingIn,
                                modifier = Modifier.weight(1f).height(48.dp).testTag("demo_student_btn"),
                                shape = RoundedCornerShape(10.dp),
                                border = BorderStroke(1.dp, if (isDark) GlassBorderDark else GlassBorderLight)
                            ) { Text("Continue as Student", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = CobaltBlue) }
                            OutlinedButton(
                                onClick = { startDevelopmentSignIn("ADMIN") },
                                enabled = !signingIn,
                                modifier = Modifier.weight(1f).height(48.dp).testTag("demo_admin_btn"),
                                shape = RoundedCornerShape(10.dp),
                                border = BorderStroke(1.dp, if (isDark) GlassBorderDark else GlassBorderLight)
                            ) { Text("Continue as Admin", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = CobaltBlue) }
                        }
                    }
                }
            }
        }
    }
}
