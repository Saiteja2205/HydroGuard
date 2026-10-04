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
                                    if (role == "ADMIN") {
                                        navController.navigate("admin") {
                                            popUpTo("login") { inclusive = true }
                                        }
                                    } else {
                                        navController.navigate("student") {
                                            popUpTo("login") { inclusive = true }
                                        }
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
    Scaffold(bottomBar = {
        NavigationBar {
            listOf("WATER", "HOSTEL OPS").forEachIndexed { index, label ->
                NavigationBarItem(selected == index, onClick = { selected = index },
                    icon = { Icon(if (index == 0) Icons.Default.WaterDrop else Icons.Default.AdminPanelSettings, contentDescription = label) },
                    label = { Text(label) })
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

    Scaffold(
        bottomBar = {
            NavigationBar {
                val labels = listOf("HOME", "WATER", "REPORT", "MY ISSUES", "PROFILE")
                val icons = listOf(Icons.Default.Home, Icons.Default.WaterDrop, Icons.Default.Warning, Icons.Default.History, Icons.Default.AdminPanelSettings)
                labels.forEachIndexed { index, label ->
                    NavigationBarItem(
                        selected = selectedTab == index,
                        onClick = { selectedTab = index },
                        icon = { Icon(icons[index], contentDescription = label) },
                        label = { Text(label) }
                    )
                }
            }
        }
    ) { paddingValues ->
        when (selectedTab) {
            0 -> HostelHomeScreen(
                viewModel = viewModel,
                onNavigate = { selectedTab = it },
                modifier = Modifier.padding(paddingValues)
            )
            1 -> WaterScreen(
                viewModel = viewModel,
                modifier = Modifier.padding(paddingValues)
            )
            2 -> ReportIssueScreen(
                modifier = Modifier.padding(paddingValues)
            )
            3 -> MyIssuesScreen(
                modifier = Modifier.padding(paddingValues)
            )
            4 -> StudentProfileScreen(viewModel, onLogout, Modifier.padding(paddingValues))
        }
    }
}
