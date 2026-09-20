package com.example.ui.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.example.data.database.AppDatabase
import com.example.data.database.User
import com.example.data.database.SensorReading
import com.example.data.database.SensorNode
import com.example.data.database.Prediction
import com.example.data.database.Alert
import com.example.data.database.NotificationLog
import com.example.data.database.WaterFeedback
import com.example.data.database.HostelFeedback
import com.example.data.database.WaterQualityReport
import com.example.data.database.AuditLog
import com.example.data.repository.HydroRepository
import com.example.data.repository.FirebaseAuthRepository
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

class HydroViewModel(application: Application) : AndroidViewModel(application) {

    private val database = AppDatabase.getDatabase(application)
    private val repository = HydroRepository(database.hydroDao(), viewModelScope)
    private val authRepository = FirebaseAuthRepository(database.hydroDao(), application)

    // User State
    val currentUser: StateFlow<User?> = authRepository.currentUserFlow
    val isFirebaseAvailable: StateFlow<Boolean> = authRepository.isFirebaseAvailable

    private val _loginError = MutableStateFlow<String?>(null)
    val loginError: StateFlow<String?> = _loginError.asStateFlow()

    // Dark Mode State
    private val _isDarkMode = MutableStateFlow(false)
    val isDarkMode: StateFlow<Boolean> = _isDarkMode.asStateFlow()

    // Active Node Selection
    private val _selectedNodeId = MutableStateFlow("node_overhead_a")
    val selectedNodeId: StateFlow<String> = _selectedNodeId.asStateFlow()

    // Interactive Data Streams
    val allNodes: StateFlow<List<SensorNode>> = repository.allNodes
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    val activeAlerts: StateFlow<List<Alert>> = repository.activeAlerts
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    val allAlerts: StateFlow<List<Alert>> = repository.allAlerts
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    val notificationLogs: StateFlow<List<NotificationLog>> = repository.notificationLogs
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    val waterFeedbackList: StateFlow<List<WaterFeedback>> = repository.waterFeedbackList
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    val hostelFeedbackList: StateFlow<List<HostelFeedback>> = repository.hostelFeedbackList
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    val reportsList: StateFlow<List<WaterQualityReport>> = repository.reportsList
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    val auditLogs: StateFlow<List<AuditLog>> = repository.auditLogs
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    // Feedback Filtering States (Admin Panel)
    val feedbackFilterStatus = MutableStateFlow("ALL")      // "ALL", "PENDING", "RESOLVED"
    val feedbackFilterBlock = MutableStateFlow("ALL")       // "ALL", "A", "B", "Mess"
    val feedbackFilterPriority = MutableStateFlow("ALL")    // "ALL", "LOW", "MEDIUM", "HIGH", "CRITICAL"
    val feedbackFilterCategory = MutableStateFlow("ALL")    // "ALL", "Water Feedback", "Hostel Feedback"

    // Dynamic stream triggers based on selected nodeId
    @OptIn(ExperimentalCoroutinesApi::class)
    val latestReading: StateFlow<SensorReading?> = _selectedNodeId
        .flatMapLatest { nodeId -> repository.getLatestReading(nodeId) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), null)

    @OptIn(ExperimentalCoroutinesApi::class)
    val historicalReadings: StateFlow<List<SensorReading>> = _selectedNodeId
        .flatMapLatest { nodeId -> repository.getHistoricalReadings(nodeId) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    @OptIn(ExperimentalCoroutinesApi::class)
    val prediction: StateFlow<Prediction?> = _selectedNodeId
        .flatMapLatest { nodeId -> repository.getPrediction(nodeId) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), null)

    fun toggleDarkMode() {
        _isDarkMode.value = !_isDarkMode.value
    }

    fun selectNode(nodeId: String) {
        _selectedNodeId.value = nodeId
    }

    // Role-Based Authentication Flow
    fun login(email: String, role: String) {
        login(email, "password123", role)
    }

    fun login(email: String, password: String, role: String) {
        viewModelScope.launch {
            _loginError.value = null
            if (email.isBlank()) {
                _loginError.value = "Email cannot be empty"
                return@launch
            }
            if (password.isBlank()) {
                _loginError.value = "Password cannot be empty"
                return@launch
            }
            if (!android.util.Patterns.EMAIL_ADDRESS.matcher(email).matches()) {
                _loginError.value = "Invalid email format"
                return@launch
            }

            val result = authRepository.loginWithEmailAndPassword(email, password, role)
            result.onFailure { exception ->
                _loginError.value = exception.localizedMessage ?: "Authentication failed"
            }
        }
    }

    fun register(
        email: String,
        password: String,
        name: String,
        role: String,
        hostelBlock: String,
        roomNumber: String
    ) {
        viewModelScope.launch {
            _loginError.value = null
            if (email.isBlank()) {
                _loginError.value = "Email cannot be empty"
                return@launch
            }
            if (password.isBlank() || password.length < 6) {
                _loginError.value = "Password must be at least 6 characters"
                return@launch
            }
            if (name.isBlank()) {
                _loginError.value = "Full Name cannot be empty"
                return@launch
            }
            if (!android.util.Patterns.EMAIL_ADDRESS.matcher(email).matches()) {
                _loginError.value = "Invalid email format"
                return@launch
            }

            val result = authRepository.registerWithEmailAndPassword(
                email, password, name, role, hostelBlock, roomNumber
            )
            result.onFailure { exception ->
                _loginError.value = exception.localizedMessage ?: "Registration failed"
            }
        }
    }

    fun logout() {
        authRepository.signOut()
    }

    // Student operations
    fun submitWaterFeedback(rating: Int, issueType: String, description: String, block: String, room: String, imagePath: String?) {
        viewModelScope.launch {
            repository.addNewWaterFeedback(rating, issueType, description, block, room, imagePath)
        }
    }

    fun submitHostelFeedback(category: String, priority: String, description: String, block: String, room: String, imagePath: String?) {
        viewModelScope.launch {
            repository.addNewHostelFeedback(category, priority, description, block, room, imagePath)
        }
    }

    // Admin operations
    fun resolveWaterComplaint(feedbackId: String, remarks: String, staff: String) {
        viewModelScope.launch {
            val adminEmail = currentUser.value?.email ?: "admin@hostel.edu"
            repository.resolveWaterFeedback(feedbackId, remarks, staff, adminEmail)
        }
    }

    fun resolveHostelComplaint(feedbackId: String, remarks: String, staff: String) {
        viewModelScope.launch {
            val adminEmail = currentUser.value?.email ?: "admin@hostel.edu"
            repository.resolveHostelFeedback(feedbackId, remarks, staff, adminEmail)
        }
    }

    fun resolveAlert(alertId: String, remarks: String) {
        viewModelScope.launch {
            val adminEmail = currentUser.value?.email ?: "admin@hostel.edu"
            repository.resolveAlert(alertId, remarks, adminEmail)
        }
    }

    fun updateThreshold(nodeId: String, param: String, newThreshold: Float) {
        viewModelScope.launch {
            val adminEmail = currentUser.value?.email ?: "admin@hostel.edu"
            repository.configureThreshold(nodeId, param, newThreshold, adminEmail)
        }
    }

    fun exportWeeklyReport(title: String, summary: String, ph: Float, turb: Float, tds: Float, alerts: Int, complaints: Int) {
        viewModelScope.launch {
            val adminEmail = currentUser.value?.email ?: "admin@hostel.edu"
            repository.exportReport(title, summary, ph, turb, tds, alerts, complaints, adminEmail)
        }
    }

    class Factory(private val application: Application) : ViewModelProvider.Factory {
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            if (modelClass.isAssignableFrom(HydroViewModel::class.java)) {
                @Suppress("UNCHECKED_CAST")
                return HydroViewModel(application) as T
            }
            throw IllegalArgumentException("Unknown ViewModel class")
        }
    }
}
