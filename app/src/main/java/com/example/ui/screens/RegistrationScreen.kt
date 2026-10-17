package com.example.ui.screens

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.Lock
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
import com.example.R
import com.example.data.api.StudentRegisterRequest
import com.example.ui.theme.HydroGuardShapes
import com.example.ui.theme.CobaltBlue
import com.example.ui.theme.SlateBlueSubtle
import com.example.ui.theme.CriticalRed
import com.example.ui.theme.CoolWhite
import com.example.ui.theme.GlassBorderDark
import com.example.ui.theme.GlassBorderLight
import com.example.ui.viewmodel.HydroViewModel

private tailrec fun Context.findActivity(): Activity? = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.findActivity()
    else -> null
]

@Composable
fun RegistrationScreen(
    viewModel: HydroViewModel,
    onRegistrationSuccess: () -> Unit,
    onBackToLogin: () -> Unit,
    modifier: Modifier = Modifier
) {
    val isDark = isSystemInDarkTheme()
    val context = LocalContext.current
    var fullName by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var confirmPassword by remember { mutableStateOf("") }
    var showPassword by remember { mutableStateOf(false) }
    var showConfirmPassword by remember { mutableStateOf(false) }
    var signingUp by remember { mutableStateOf(false) }
    val registrationError by viewModel.registrationError.collectAsState()
        ?.takeIf { it.isNotBlank() }

    fun submitRegistration() {
        if (password != confirmPassword) {
            viewModel.showRegistrationError("Passwords do not match.")
            return
        }
        signingUp = true
        viewModelScope.launch {
            viewModel.registerStudent(fullName, email, password).onSuccess {
                signingUp = false
                onRegistrationSuccess()
            }.onFailure { error ->
                signingUp = false
                viewModel.showRegistrationError(
                    when (error.kind) {
                        ApiFailureKind.AUTHENTICATION -> "Registration failed. Please try again."
                        ApiFailureKind.API_ERROR -> "Unable to reach the server. Check your connection and try again."
                        else -> "Registration failed. Please try again."
                    }
                )
            }
        }
    }

    fun navigateToLogin() {
        onBackToLogin()
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

            // Registration card
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(20.dp),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surface
                ),
                border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline)
            ) {
                Column(
                    modifier = Modifier.padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.SpacingAndSize(8.dp)
                ) {
                    Text(
                        text = "Create Your Account",
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Spacer(Modifier.height(8.dp))
                    Text(
                        text = "Sign up with your college email address to get started.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = SlateBlueSubtle,
                        textAlign = TextAlign.Center
                    )
                    Spacer(Modifier.height(24.dp))

                    // Full name field
                    OutlinedTextField(
                        value = fullName,
                        onValueChange = { fullName = it },
                        label = { Text(fullName, style = MaterialTheme.typography.labelMedium) },
                        placeholder = { Text("Full name", style = MaterialTheme.typography.bodySmall) },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        shape = RoundedCornerShape(12.dp),
                        border = OutlineTextFieldBorder(
                            defaultColor = MaterialTheme.colorScheme.outline,
                            focusedColor = CobaltBlue,
                            errorColor = CriticalRed
                        ),
                        trailingIcon = {
                            if (showPassword) {
                                Icon(Icons.Default.LockOpen, contentDescription = "Show password", tint = CobaltBlue)
                            } else {
                                Icon(Icons.Default.Lock, contentDescription = "Hide password", tint = CobaltBlue)
                            }
                        },
                        onTrailingIconClick = { showPassword = !showPassword },
                        = { it.isNotEmpty() && !it.any { it.isWhitespace() } }
                    )
                    // Actually, let me simplify this - I'll use a simpler text field approach

                    // Email field
                    OutlinedTextField(
                        value = email,
                        onValueChange = { email = it },
                        label = { Text("College email", style = MaterialTheme.typography.labelMedium) },
                        placeholder = { Text "student@vrsec.ac.in or student@siddhartha.edu.in", style = MaterialTheme.typography.bodySmall) },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        shape = RoundedCornerShape(12.dp),
                        border = OutlineTextFieldBorder(
                            defaultColor = MaterialTheme.colorScheme.outline,
                            focusedColor = CobaltBlue,
                            errorColor = CriticalRed
                        ),
                        keyboardOptions = KeyboardOptions(
                            action = ImeAction.NEXT,
                            keyboardType = KeyboardType.EMAIL
                        )
                    )
                    Spacer(Modifier.height(12.dp))

                    // Password field
                    OutlinedTextField(
                        value = password,
                        onValueChange = { password = it },
                        label = { Text("Password", style = MaterialTheme.typography.labelMedium) },
                        placeholder = { Text "minimum 8 characters", style = MaterialTheme.typography.bodySmall) },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        shape = RoundedCornerShape(12.dp),
                        border = OutlineTextFieldBorder(
                            defaultColor = MaterialTheme.colorScheme.outline,
                            focusedColor = CobaltBlue,
                            errorColor = CriticalRed
                        ),
                        passwordVisible = showPassword,
                        trailingIcon = {
                            if (showPassword) {
                                Icon(Icons.Default.LockOpen, contentDescription = "Show password", tint = CobaltBlue)
                            } else {
                                Icon(Icons.Default.Lock, contentDescription = "Hide password", tint = CobaltBlue)
                            }
                        },
                        onPasswordVisibilityToggle = { showPassword = !showPassword },
                        keyboardOptions = KeyboardOptions(
                            action = ImeAction.NEXT,
                            keyboardType = KeyboardType.Password
                        )
                    )
                    Spacer(Modifier.height(12.dp))

                    // Confirm password field
                    OutlinedTextField(
                        value = confirmPassword,
                        onValueChange = { confirmPassword = it },
                        label = { Text("Confirm password", style = MaterialTheme.typography.labelMedium) },
                        placeholder = { Text "repeat your password", style = MaterialTheme.typography.bodySmall) },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        shape = RoundedCornerShape(12.dp),
                        border = OutlineTextFieldBorder(
                            defaultColor = MaterialTheme.colorScheme.outline,
                            focusedColor = CobaltBlue,
                            errorColor = CriticalRed
                        ),
                        passwordVisible = showConfirmPassword,
                        trailingIcon = {
                            if (showConfirmPassword) {
                                Icon(Icons.Default.LockOpen, contentDescription = "Show password", tint = CobaltBlue)
                            } else {
                                Icon(Icons.Default.Lock, contentDescription = "Hide password", tint = CobaltBlue)
                            }
                        },
                        onPasswordVisibilityToggle = { showConfirmPassword = !showConfirmPassword },
                        keyboardOptions = KeyboardOptions(
                            action = ImeAction.DONE,
                            keyboardType = KeyboardType.Password
                        )
                    )
                    Spacer(Modifier.height(12.dp))

                    // Password requirements text
                    Text(
                        text = "Password must be at least 8 characters and contain at least one lowercase letter, one uppercase letter, one digit, and one special character.",
                        style = MaterialTheme.typography.bodySmall,
                        color = SlateBlueSubtle,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.padding(8.dp)
                    )
                    Spacer(Modifier.height(24.dp))

                    // Sign up button
                    Button(
                        onClick = ::submitRegistration,
                        enabled = !signingUp,
                        modifier = Modifier.fillMaxWidth().height(50.dp),
                        shape = RoundedCornerShape(12.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (password == confirmPassword && password.isNotEmpty()) {
                                CobaltBlue
                            } else {
                                MaterialTheme.colorScheme.surface
                            }
                        )
                    ) {
                        if (signingUp) {
                            CircularProgressIndicator(Modifier.size(18.dp), color = CoolWhite, strokeWidth = 2.dp)
                            Spacer(Modifier.width(10.dp))
                        }
                        Text(
                            text = if (signingUp) "Creating Account…" else "Create Account",
                            fontWeight = FontWeight.Bold,
                            fontSize = 15.sp,
                            color = CoolWhite
                        )
                    }
                    Spacer(Modifier.height(16.dp))

                    // Error message
                    if (registrationError != null) {
                        Card(
                            colors = CardDefaults.cardColors(containerColor = CriticalRed.copy(alpha = 0.1f)),
                            shape = RoundedCornerShape(12.dp),
                            border = BorderStroke(1.dp, CriticalRed.copy(alpha = 0.3f)),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Row(
                                modifier = Modifier.padding(12.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spedBy(8.dp)
                            ) {
                                Icon(Icons.Default.Error, contentDescription = "Error", tint = CriticalRed)
                                Text(
                                    text = registrationError,
                                    color = CriticalRed,
                                    style = MaterialTheme.typography.bodySmall,
                                    fontWeight = FontWeight.Bold,
                                    modifier = Modifier.weight(1f)
                                )
                            }
                        }
                        Spacer(Modifier.height(16.dp))
                    }

                    // Login link
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.Center
                    ) {
                        Text(
                            text = "Already have an account? ",
                            style = MaterialTheme.typography.bodySmall,
                            color = SlateBlueSubtle
                        )
                        OutlinedButton(
                            onClick = ::navigateToLogin,
                            modifier = Modifier.weight(1f),
                            shape = RoundedCornerShape(8.dp),
                            border = BorderStroke(1.dp, CobaltBlue),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = MaterialTheme.colorScheme.surface
                            )
                        ) {
                            Text("Sign In", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = CobaltBlue)
                        }
                    }
                }
            }
        }
    }
}

// Helper annotations for OutlinedTextField password visibility
@Composable
fun OutlinedTextField(
    value: String,
    onValueChange: (String) -> Unit,
    label: @Composable (@param: String) -> Unit,
    placeholder: @Composable (@param: String) -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    readOnly: Boolean = false,
    keyboardOptions: KeyboardOptions? = null,
    keyboardActions: KeyboardActions? = null,
    singleLine: Boolean = true,
    multiLine: Int = 1,
    shape: RoundedCornerShape = RoundedCornerShape(8.dp),
    border: OutlineTextFieldBorder? = null,
    passwordVisible: Boolean = false,
    trailingIcon: @Composable () -> Unit? = null,
    onPasswordVisibilityToggle: (() -> Unit)? = null,
    keyboardActions: KeyboardActions? = null,
    onFieldSubmit: (() -> Unit)? = null,
    keyboardType: KeyboardType = KeyboardType.Text,
    interpolation: androidx.compose.ui.text.InputInterpolation = InputDefaults.inputInterpolation,
    filter: androidx.compose.ui.text.filters.TextFilter = InputDefaults.textFilter,
    valueAlignment: Alignment = Alignment.Start,
    deleteConfirmation = false,
    selectionContainer: SelectionContainer? = null,
   imeActions: ImeActions? = null
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = label,
        placeholder = placeholder,
        modifier = modifier,
        enabled = enabled,
        readOnly = readOnly,
        keyboardOptions = keyboardOptions,
        keyboardActions = keyboardActions,
        singleLine = singleLine,
        multiLine = multiLine,
        shape = shape,
        border = border,
        passwordVisible = passwordVisible,
        trailingIcon = trailingIcon,
        onPasswordVisibilityToggle = onPasswordVisibilityToggle,
        keyboardActions = keyboardActions,
        onFieldSubmit = onFieldSubmit,
        keyboardType = keyboardType,
        interpolation = interpolation,
        filter = filter,
        valueAlignment = valueAlignment,
        deleteConfirmation = deleteConfirmation,
        selectionContainer = selectionContainer,
        imeActions = imeActions
    )