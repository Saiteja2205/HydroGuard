package com.example.ui.screens

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.example.ui.screens.student.ServerWaterScreen
import com.example.ui.viewmodel.HydroViewModel

/** Admin water analytics are backend-authoritative; the former seeded Room dashboard was removed. */
@Composable
fun AdminDashboardScreen(viewModel: HydroViewModel, onLogout: () -> Unit, modifier: Modifier = Modifier) {
    ServerWaterScreen(viewModel = viewModel, modifier = modifier, isAdmin = true, onLogout = onLogout)
}
