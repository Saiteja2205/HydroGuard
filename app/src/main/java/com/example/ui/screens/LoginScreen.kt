package com.example.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.ui.components.GlassCard
import com.example.ui.theme.*
import com.example.ui.viewmodel.HydroViewModel

@Composable
fun LoginScreen(
    viewModel: HydroViewModel,
    onLoginSuccess: (String) -> Unit, // passes role
    modifier: Modifier = Modifier
) {
    val isDark = isSystemInDarkTheme()
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }
    var hostelBlock by remember { mutableStateOf("A") }
    var roomNumber by remember { mutableStateOf("") }
    
    var selectedRole by remember { mutableStateOf("STUDENT") } // "STUDENT" or "ADMIN"
    var isRegisterMode by remember { mutableStateOf(false) }
    var passwordVisible by remember { mutableStateOf(false) }
    
    val loginError by viewModel.loginError.collectAsState()
    val currentUser by viewModel.currentUser.collectAsState()
    val isFirebaseAvailable by viewModel.isFirebaseAvailable.collectAsState()

    // Listen to login success
    LaunchedEffect(currentUser) {
        currentUser?.let {
            onLoginSuccess(it.role)
        }
    }

    val backgroundBrush = if (isDark) DarkMeshBackground else LightMeshBackground

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(backgroundBrush)
            .verticalScroll(rememberScrollState()),
        contentAlignment = Alignment.Center
    ) {
        Column(
            modifier = Modifier
                .padding(horizontal = 24.dp, vertical = 36.dp)
                .fillMaxWidth()
                .widthIn(max = 440.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            // Enterprise Smart Infrastructure Water Icon Badge
            Box(
                modifier = Modifier
                    .size(76.dp)
                    .clip(RoundedCornerShape(22.dp))
                    .background(CobaltCeruleanGradient)
                    .shadow(12.dp, RoundedCornerShape(22.dp), ambientColor = Color(0x330047AB), spotColor = Color(0x660284C7))
                    .padding(16.dp),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = Icons.Default.WaterDrop,
                    contentDescription = "HydroGuard Logo",
                    tint = CoolWhite,
                    modifier = Modifier.fillMaxSize()
                )
            }

            Spacer(modifier = Modifier.height(18.dp))

            Text(
                text = "HydroGuard AI",
                fontSize = 32.sp,
                fontWeight = FontWeight.Black,
                color = CobaltBlue,
                textAlign = TextAlign.Center,
                letterSpacing = (-1).sp
            )

            Text(
                text = "SMART INFRASTRUCTURE TELEMETRY HUB",
                style = MaterialTheme.typography.labelSmall,
                color = SlateBlueSubtle,
                textAlign = TextAlign.Center,
                letterSpacing = 1.sp
            )

            Spacer(modifier = Modifier.height(14.dp))

            // Firebase Status Chip
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                modifier = Modifier
                    .clip(RoundedCornerShape(50))
                    .background(
                        if (isFirebaseAvailable) SafeGreen.copy(alpha = 0.12f) else WarningAmber.copy(alpha = 0.12f)
                    )
                    .border(
                        1.dp,
                        if (isFirebaseAvailable) SafeGreen.copy(alpha = 0.3f) else WarningAmber.copy(alpha = 0.3f),
                        RoundedCornerShape(50)
                    )
                    .padding(horizontal = 12.dp, vertical = 5.dp)
            ) {
                Box(
                    modifier = Modifier
                        .size(7.dp)
                        .clip(CircleShape)
                        .background(if (isFirebaseAvailable) SafeGreen else WarningAmber)
                )
                Text(
                    text = if (isFirebaseAvailable) "Firebase Auth Connected" else "Local Sandbox Auth",
                    style = MaterialTheme.typography.labelSmall,
                    color = if (isFirebaseAvailable) SafeGreen else WarningAmber,
                    fontSize = 10.sp
                )
            }

            Spacer(modifier = Modifier.height(20.dp))

            // Role selection buttons with Glass Pill Design
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(16.dp))
                    .background(if (isDark) GlassSurfaceDark else GlassSurfaceLight)
                    .border(1.dp, if (isDark) GlassBorderDark else GlassBorderLight, RoundedCornerShape(16.dp))
                    .padding(4.dp),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                Button(
                    onClick = { selectedRole = "STUDENT" },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (selectedRole == "STUDENT") CobaltBlue else Color.Transparent,
                        contentColor = if (selectedRole == "STUDENT") CoolWhite else SlateBlueSubtle
                    ),
                    modifier = Modifier
                        .weight(1f)
                        .height(44.dp)
                        .testTag("role_student_toggle"),
                    shape = RoundedCornerShape(12.dp),
                    elevation = ButtonDefaults.buttonElevation(defaultElevation = 0.dp)
                ) {
                    Text(
                        text = "Student Hub",
                        fontWeight = FontWeight.Bold,
                        fontSize = 13.sp
                    )
                }

                Button(
                    onClick = { selectedRole = "ADMIN" },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (selectedRole == "ADMIN") CobaltBlue else Color.Transparent,
                        contentColor = if (selectedRole == "ADMIN") CoolWhite else SlateBlueSubtle
                    ),
                    modifier = Modifier
                        .weight(1f)
                        .height(44.dp)
                        .testTag("role_admin_toggle"),
                    shape = RoundedCornerShape(12.dp),
                    elevation = ButtonDefaults.buttonElevation(defaultElevation = 0.dp)
                ) {
                    Text(
                        text = "Admin Console",
                        fontWeight = FontWeight.Bold,
                        fontSize = 13.sp
                    )
                }
            }

            Spacer(modifier = Modifier.height(20.dp))

            // Glassmorphic Auth Card
            GlassCard(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(26.dp),
                isDark = isDark
            ) {
                Column(
                    modifier = Modifier.padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        text = if (isRegisterMode) "Create Account" else "Sign In",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.ExtraBold,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Spacer(modifier = Modifier.height(2.dp))
                    Text(
                        text = if (isRegisterMode) "Register for campus water telemetry" else "Access your node monitoring dashboard",
                        style = MaterialTheme.typography.bodySmall,
                        color = SlateBlueSubtle
                    )

                    Spacer(modifier = Modifier.height(20.dp))

                    // Registration fields (Name)
                    AnimatedVisibility(
                        visible = isRegisterMode,
                        enter = fadeIn() + expandVertically(),
                        exit = fadeOut() + shrinkVertically()
                    ) {
                        Column {
                            OutlinedTextField(
                                value = name,
                                onValueChange = { name = it },
                                label = { Text("Full Name") },
                                leadingIcon = { Icon(Icons.Default.Person, contentDescription = "Name", tint = CeruleanBlueBright) },
                                singleLine = true,
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .testTag("register_name_input"),
                                shape = RoundedCornerShape(14.dp)
                            )
                            Spacer(modifier = Modifier.height(14.dp))
                        }
                    }

                    // Email field
                    OutlinedTextField(
                        value = email,
                        onValueChange = { email = it },
                        label = { Text("Institutional Email") },
                        placeholder = { Text("e.g. resident@campus.edu") },
                        leadingIcon = { Icon(Icons.Default.Email, contentDescription = "Email", tint = CeruleanBlueBright) },
                        singleLine = true,
                        modifier = Modifier
                            .fillMaxWidth()
                            .testTag("email_input"),
                        shape = RoundedCornerShape(14.dp)
                    )

                    Spacer(modifier = Modifier.height(14.dp))

                    // Password field
                    OutlinedTextField(
                        value = password,
                        onValueChange = { password = it },
                        label = { Text("Password") },
                        placeholder = { Text("At least 6 characters") },
                        leadingIcon = { Icon(Icons.Default.Lock, contentDescription = "Password", tint = CeruleanBlueBright) },
                        singleLine = true,
                        visualTransformation = if (passwordVisible) VisualTransformation.None else PasswordVisualTransformation(),
                        trailingIcon = {
                            val image = if (passwordVisible) Icons.Filled.Visibility else Icons.Filled.VisibilityOff
                            val description = if (passwordVisible) "Hide password" else "Show password"
                            IconButton(onClick = { passwordVisible = !passwordVisible }) {
                                Icon(imageVector = image, contentDescription = description, tint = SlateBlueSubtle)
                            }
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .testTag("password_input"),
                        shape = RoundedCornerShape(14.dp)
                    )

                    // Registration fields (Block & Room)
                    AnimatedVisibility(
                        visible = isRegisterMode,
                        enter = fadeIn() + expandVertically(),
                        exit = fadeOut() + shrinkVertically()
                    ) {
                        Column {
                            Spacer(modifier = Modifier.height(14.dp))
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(12.dp)
                            ) {
                                // Hostel Block Selector
                                OutlinedTextField(
                                    value = hostelBlock,
                                    onValueChange = { hostelBlock = it.uppercase() },
                                    label = { Text("Block") },
                                    placeholder = { Text("A") },
                                    leadingIcon = { Icon(Icons.Default.Home, contentDescription = "Block", tint = CeruleanBlueBright) },
                                    singleLine = true,
                                    modifier = Modifier
                                        .weight(1f)
                                        .testTag("register_block_input"),
                                    shape = RoundedCornerShape(14.dp)
                                )

                                // Room Number
                                OutlinedTextField(
                                    value = roomNumber,
                                    onValueChange = { roomNumber = it },
                                    label = { Text("Room No.") },
                                    placeholder = { Text("304") },
                                    leadingIcon = { Icon(Icons.Default.MeetingRoom, contentDescription = "Room", tint = CeruleanBlueBright) },
                                    singleLine = true,
                                    modifier = Modifier
                                        .weight(1f)
                                        .testTag("register_room_input"),
                                    shape = RoundedCornerShape(14.dp)
                                )
                            }
                        }
                    }

                    // Error Box
                    AnimatedVisibility(visible = loginError != null) {
                        loginError?.let {
                            Card(
                                colors = CardDefaults.cardColors(
                                    containerColor = CriticalRed.copy(alpha = 0.1f)
                                ),
                                shape = RoundedCornerShape(12.dp),
                                border = BorderStroke(1.dp, CriticalRed.copy(alpha = 0.3f)),
                                modifier = Modifier
                                    .padding(top = 14.dp)
                                    .fillMaxWidth()
                            ) {
                                Row(
                                    modifier = Modifier.padding(12.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.Error,
                                        contentDescription = "Error icon",
                                        tint = CriticalRed
                                    )
                                    Text(
                                        text = it,
                                        color = CriticalRed,
                                        style = MaterialTheme.typography.bodySmall,
                                        fontWeight = FontWeight.Bold,
                                        modifier = Modifier.weight(1f)
                                    )
                                }
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(20.dp))

                    // Primary Action Button
                    Button(
                        onClick = {
                            if (isRegisterMode) {
                                viewModel.register(
                                    email = email,
                                    password = password,
                                    name = name,
                                    role = selectedRole,
                                    hostelBlock = hostelBlock,
                                    roomNumber = roomNumber
                                )
                            } else {
                                viewModel.login(
                                    email = email,
                                    password = password,
                                    role = selectedRole
                                )
                            }
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(50.dp)
                            .shadow(6.dp, RoundedCornerShape(14.dp), ambientColor = Color(0x330047AB), spotColor = Color(0x660047AB))
                            .testTag("login_button"),
                        shape = RoundedCornerShape(14.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = CobaltBlue)
                    ) {
                        Text(
                            text = if (isRegisterMode) "Create Account" else "Sign In",
                            fontWeight = FontWeight.Bold,
                            fontSize = 15.sp,
                            color = CoolWhite
                        )
                    }

                    Spacer(modifier = Modifier.height(16.dp))

                    // Switch Mode Clickable Text
                    Row(
                        horizontalArrangement = Arrangement.Center,
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(
                            text = if (isRegisterMode) "Already registered? " else "Don't have an account? ",
                            style = MaterialTheme.typography.bodySmall,
                            color = SlateBlueSubtle
                        )
                        Text(
                            text = if (isRegisterMode) "Sign In" else "Sign Up",
                            style = MaterialTheme.typography.bodySmall,
                            fontWeight = FontWeight.Black,
                            color = CobaltBlue,
                            modifier = Modifier
                                .clickable {
                                    isRegisterMode = !isRegisterMode
                                }
                                .testTag("toggle_auth_mode")
                        )
                    }

                    Spacer(modifier = Modifier.height(18.dp))

                    HorizontalDivider(color = if (isDark) GlassBorderDark else GlassBorderLight)

                    Spacer(modifier = Modifier.height(14.dp))

                    // Developer shortcuts
                    Text(
                        text = "DEV TEST BYPASS SHORTCUTS",
                        style = MaterialTheme.typography.labelSmall,
                        color = SlateBlueSubtle,
                        letterSpacing = 1.sp
                    )

                    Spacer(modifier = Modifier.height(10.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        OutlinedButton(
                            onClick = {
                                email = "student@hostel.edu"
                                password = "password123"
                                viewModel.login("student@hostel.edu", "password123", "STUDENT")
                            },
                            modifier = Modifier
                                .weight(1f)
                                .height(38.dp)
                                .testTag("demo_student_btn"),
                            shape = RoundedCornerShape(10.dp),
                            border = BorderStroke(1.dp, if (isDark) GlassBorderDark else GlassBorderLight)
                        ) {
                            Text("Student Bypass", fontSize = 11.sp, fontWeight = FontWeight.Bold, color = CobaltBlue)
                        }

                        OutlinedButton(
                            onClick = {
                                email = "admin@hostel.edu"
                                password = "password123"
                                viewModel.login("admin@hostel.edu", "password123", "ADMIN")
                            },
                            modifier = Modifier
                                .weight(1f)
                                .height(38.dp)
                                .testTag("demo_admin_btn"),
                            shape = RoundedCornerShape(10.dp),
                            border = BorderStroke(1.dp, if (isDark) GlassBorderDark else GlassBorderLight)
                        ) {
                            Text("Admin Bypass", fontSize = 11.sp, fontWeight = FontWeight.Bold, color = CeruleanBlueBright)
                        }
                    }
                }
            }
        }
    }
}
