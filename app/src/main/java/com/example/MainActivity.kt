package com.example

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AdminPanelSettings
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.PersonOutline
import androidx.compose.material.icons.filled.ReportProblem
import androidx.compose.material.icons.filled.WaterDrop
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.example.ui.screens.AdminDashboardScreen
import com.example.ui.screens.AdminHostelOpsScreen
import com.example.ui.screens.LoginScreen
import com.example.ui.screens.student.HostelHomeScreen
import com.example.ui.screens.student.MyIssuesScreen
import com.example.ui.screens.student.ReportIssueScreen
import com.example.ui.screens.student.StudentProfileScreen
import com.example.ui.screens.student.WaterScreen
import com.example.ui.theme.HydroGuardTheme
import com.example.ui.viewmodel.HydroViewModel
import com.example.data.repository.DevelopmentAuthPolicy

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        setContent {
            // Instantiate the central ViewModel using standard Factory
            val viewModel: HydroViewModel by viewModels {
                HydroViewModel.Factory(application)
            }

            val isDark by viewModel.isDarkMode.collectAsState()

            HydroGuardTheme(darkTheme = isDark) {
                Surface(
                    modifier = Modifier.fillMaxSize()
                ) {
                    val navController = rememberNavController()

                    NavHost(
                        navController = navController,
                        startDestination = "login"
                    ) {
                        composable("login") {
                            LoginScreen(
                                viewModel = viewModel,
                                onLoginSuccess = { role ->
                                    navController.navigate(DevelopmentAuthPolicy.destinationForRole(role)) {
                                        popUpTo("login") { inclusive = true }
                                    }
                                }
                            )
                        }

                        composable("student") {
                            StudentNavigationWrapper(
                                viewModel = viewModel,
                                onLogout = {
                                    viewModel.logout()
                                    navController.navigate("login") {
                                        popUpTo("student") { inclusive = true }
                                    }
                                }
                            )
                        }

                        composable("admin") {
            AdminNavigationWrapper(viewModel, onLogout = {
                viewModel.logout()
                navController.navigate("login") { popUpTo("admin") { inclusive = true } }
            })
                        }

                    }
                }
            }
        }
    }
}

@Composable
private fun AdminNavigationWrapper(viewModel: HydroViewModel, onLogout: () -> Unit) {
    var selected by rememberSaveable { mutableIntStateOf(0) }
    Scaffold(containerColor = MaterialTheme.colorScheme.background, bottomBar = {
        NavigationBar(containerColor = MaterialTheme.colorScheme.surface, tonalElevation = 0.dp) {
            listOf("Water Monitoring", "Hostel Operations").forEachIndexed { index, label ->
                NavigationBarItem(selected == index, onClick = { selected = index },
                    icon = { Icon(if (index == 0) Icons.Default.WaterDrop else Icons.Default.AdminPanelSettings, contentDescription = label) },
                    label = { Text(label, maxLines = 1, style = MaterialTheme.typography.labelSmall) },
                    colors = NavigationBarItemDefaults.colors(
                        selectedIconColor = MaterialTheme.colorScheme.primary,
                        selectedTextColor = MaterialTheme.colorScheme.primary,
                        indicatorColor = MaterialTheme.colorScheme.primaryContainer
                    ))
            }
        }
    }) { padding ->
        when (selected) {
            0 -> AdminDashboardScreen(viewModel, onLogout, Modifier.padding(padding))
            else -> AdminHostelOpsScreen(onLogout, Modifier.padding(padding))
        }
    }
}

@Composable
private fun StudentNavigationWrapper(
    viewModel: HydroViewModel,
    onLogout: () -> Unit
) {
    var selectedTab by rememberSaveable { mutableIntStateOf(0) }
    var initialWaterTab by rememberSaveable { mutableIntStateOf(0) }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        bottomBar = {
            NavigationBar(containerColor = MaterialTheme.colorScheme.surface, tonalElevation = 0.dp) {
                val labels = listOf("Home", "Water", "Report", "My Issues", "Profile")
                val icons = listOf(Icons.Default.Home, Icons.Default.WaterDrop, Icons.Default.ReportProblem, Icons.Default.History, Icons.Default.PersonOutline)
                labels.forEachIndexed { index, label ->
                    NavigationBarItem(
                        selected = selectedTab == index,
                        onClick = {
                            selectedTab = index
                            if (index == 1) initialWaterTab = 0
                        },
                        icon = { Icon(icons[index], contentDescription = label) },
                        label = { Text(label, maxLines = 1, style = MaterialTheme.typography.labelSmall) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = MaterialTheme.colorScheme.primary,
                            selectedTextColor = MaterialTheme.colorScheme.primary,
                            indicatorColor = MaterialTheme.colorScheme.primaryContainer
                        )
                    )
                }
            }
        }
    ) { paddingValues ->
        when (selectedTab) {
            0 -> HostelHomeScreen(
                viewModel = viewModel,
                onNavigate = { selectedTab = it },
                modifier = Modifier.padding(paddingValues),
                onNavigateToAlerts = {
                    initialWaterTab = 3
                    selectedTab = 1
                },
                onSignIn = onLogout
            )
            1 -> WaterScreen(
                viewModel = viewModel,
                modifier = Modifier.padding(paddingValues),
                initialTab = initialWaterTab,
                onSignIn = onLogout
            )
            2 -> ReportIssueScreen(
                modifier = Modifier.padding(paddingValues),
                onSignIn = onLogout
            )
            3 -> MyIssuesScreen(
                modifier = Modifier.padding(paddingValues),
                onSignIn = onLogout
            )
            4 -> StudentProfileScreen(viewModel, onLogout, Modifier.padding(paddingValues))
        }
    }
}
