package com.example

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.example.ui.screens.AdminDashboardScreen
import com.example.ui.screens.FeedbackScreen
import com.example.ui.screens.LoginScreen
import com.example.ui.screens.StudentDashboardScreen
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
                            StudentDashboardScreen(
                                viewModel = viewModel,
                                onNavigateToFeedback = { navController.navigate("feedback") },
                                onLogout = {
                                    navController.navigate("login") {
                                        popUpTo("student") { inclusive = true }
                                    }
                                }
                            )
                        }

                        composable("admin") {
                            AdminDashboardScreen(
                                viewModel = viewModel,
                                onLogout = {
                                    navController.navigate("login") {
                                        popUpTo("admin") { inclusive = true }
                                    }
                                }
                            )
                        }

                        composable("feedback") {
                            FeedbackScreen(
                                viewModel = viewModel,
                                onNavigateBack = { navController.popBackStack() }
                            )
                        }
                    }
                }
            }
        }
    }
}
