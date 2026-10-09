package com.example.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import com.example.ui.viewmodel.HydroViewModel

@Composable
fun AdminManagementScreen(
    viewModel: HydroViewModel,
    modifier: Modifier = Modifier
) {
    val admins by viewModel.adminUsers.collectAsState()
    val message by viewModel.adminManagementMessage.collectAsState()
    val loading by viewModel.isAdminManagementLoading.collectAsState()
    val currentUser by viewModel.currentUser.collectAsState()
    var facultyEmail by remember { mutableStateOf("") }

    LaunchedEffect(Unit) { viewModel.loadAdminUsers() }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("Admin Management", style = MaterialTheme.typography.headlineSmall)
        Text(
            "Add and manage faculty access for HydroGuard.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        Card(modifier = Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Text("Add Faculty", style = MaterialTheme.typography.titleMedium)
                OutlinedTextField(
                    value = facultyEmail,
                    onValueChange = { facultyEmail = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("Faculty Google email") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email)
                )
                Button(
                    onClick = {
                        viewModel.inviteAdmin(facultyEmail)
                        facultyEmail = ""
                    },
                    enabled = !loading && facultyEmail.isNotBlank()
                ) {
                    Text("Add Faculty")
                }
            }
        }

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text("Faculty/Admin accounts", style = MaterialTheme.typography.titleMedium)
            TextButton(onClick = { viewModel.loadAdminUsers() }, enabled = !loading) {
                Text("Refresh")
            }
        }

        message?.let {
            Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.primary)
        }

        if (loading && admins.isEmpty()) {
            CircularProgressIndicator()
        } else if (admins.isEmpty()) {
            Text("No faculty accounts have been added yet.", style = MaterialTheme.typography.bodyMedium)
        } else {
            admins.forEach { admin ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        Text(
                            admin.displayName?.takeIf(String::isNotBlank) ?: admin.email,
                            style = MaterialTheme.typography.titleSmall
                        )
                        Text(admin.email, style = MaterialTheme.typography.bodyMedium)
                        Text(
                            admin.status.lowercase().replaceFirstChar(Char::uppercase),
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        if (!admin.email.equals(currentUser?.email, ignoreCase = true)) {
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                when (admin.status) {
                                    "ACTIVE" -> {
                                        OutlinedButton(
                                            onClick = { viewModel.updateAdminStatus(admin.id, "SUSPENDED") },
                                            enabled = !loading
                                        ) { Text("Suspend") }
                                        TextButton(
                                            onClick = { viewModel.updateAdminStatus(admin.id, "REVOKED") },
                                            enabled = !loading
                                        ) { Text("Revoke") }
                                    }
                                    "SUSPENDED", "REVOKED" -> Button(
                                        onClick = { viewModel.updateAdminStatus(admin.id, "ACTIVE") },
                                        enabled = !loading
                                    ) { Text("Activate") }
                                    "INVITED" -> TextButton(
                                        onClick = { viewModel.updateAdminStatus(admin.id, "REVOKED") },
                                        enabled = !loading
                                    ) { Text("Revoke invite") }
                                }
                            }
                        }
                    }
                }
            }
        }
        Spacer(modifier = Modifier.height(8.dp))
    }
}
