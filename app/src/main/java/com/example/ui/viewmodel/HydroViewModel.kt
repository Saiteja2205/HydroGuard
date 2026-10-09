package com.example.ui.viewmodel

import android.app.Application
import android.util.Log
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
import com.example.data.repository.ApiRepository
import com.example.data.api.ForecastResponse
import com.example.data.api.LatestReadingResponse
import com.example.data.api.HistoricalReadingResponse
import com.example.data.api.HistoryResponse
import com.example.data.api.AlertListResponse
import com.example.data.api.AlertResponse
import com.example.data.api.AdminUserResponse
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

class HydroViewModel(application: Application) : AndroidViewModel(application) {

    private val database = AppDatabase.getDatabase(application)
    private val repository = HydroRepository(database.hydroDao(), viewModelScope)
    private val apiRepository = ApiRepository()
    private val authRepository = FirebaseAuthRepository(database.hydroDao(), application, apiRepository = apiRepository)

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
        .flatMapLatest { nodeId ->
            repository.getLatestReading(nodeId).onEach { reading ->
                Log.d("HydroViewModel", "Room latest node=$nodeId source=${reading?.source ?: "none"} timestamp=${reading?.timestamp ?: "none"}")
            }
        }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), null)

    @OptIn(ExperimentalCoroutinesApi::class)
    val historicalReadings: StateFlow<List<SensorReading>> = _selectedNodeId
        .flatMapLatest { nodeId ->
            repository.getHistoricalReadings(nodeId).onEach { readings ->
                Log.d("HydroViewModel", "Room history node=$nodeId count=${readings.size}")
            }
        }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    @OptIn(ExperimentalCoroutinesApi::class)
    val prediction: StateFlow<Prediction?> = _selectedNodeId
        .flatMapLatest { nodeId -> repository.getPrediction(nodeId) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), null)

    // API State
    private val _apiForecast = MutableStateFlow<ForecastResponse?>(null)
    val apiForecast: StateFlow<ForecastResponse?> = _apiForecast.asStateFlow()

    private val _apiLatestReading = MutableStateFlow<LatestReadingResponse?>(null)
    val apiLatestReading: StateFlow<LatestReadingResponse?> = _apiLatestReading.asStateFlow()

    private val _apiHistoricalReadings = MutableStateFlow<List<HistoricalReadingResponse>>(emptyList())
    val apiHistoricalReadings: StateFlow<List<HistoricalReadingResponse>> = _apiHistoricalReadings.asStateFlow()

    private val _apiAlerts = MutableStateFlow<List<AlertResponse>>(emptyList())
    val apiAlerts: StateFlow<List<AlertResponse>> = _apiAlerts.asStateFlow()

    private val _adminUsers = MutableStateFlow<List<AdminUserResponse>>(emptyList())
    val adminUsers: StateFlow<List<AdminUserResponse>> = _adminUsers.asStateFlow()

    private val _adminManagementMessage = MutableStateFlow<String?>(null)
    val adminManagementMessage: StateFlow<String?> = _adminManagementMessage.asStateFlow()

    private val _isAdminManagementLoading = MutableStateFlow(false)
    val isAdminManagementLoading: StateFlow<Boolean> = _isAdminManagementLoading.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _apiError = MutableStateFlow<String?>(null)
    val apiError: StateFlow<String?> = _apiError.asStateFlow()

    fun toggleDarkMode() {
        _isDarkMode.value = !_isDarkMode.value
    }

    fun selectNode(nodeId: String) {
        Log.i("HydroViewModel", "Selected monitoring node=$nodeId")
        _selectedNodeId.value = nodeId
    }

    // The backend account record determines the role; Firebase claims are refreshed for subsequent API calls.
    fun signInWithGoogleIdToken(idToken: String): Job {
        return viewModelScope.launch {
            _loginError.value = null
            authRepository.signInWithGoogleIdToken(idToken).onFailure { exception ->
                _loginError.value = when (exception) {
                    is SecurityException -> "This Google account is not authorized for HydroGuard. Contact your administrator."
                    else -> "We couldn't sign you in right now. Check your connection and try again."
                }
            }
        }
    }

    fun showLoginError(message: String) {
        _loginError.value = message
    }

    fun clearLoginError() {
        _loginError.value = null
    }

    fun developmentLogin(role: String) {
        viewModelScope.launch {
            _loginError.value = null
            authRepository.loginAsDevelopment(role).onFailure { error ->
                _loginError.value = error.localizedMessage ?: "Development Login is disabled."
            }
        }
    }

    fun logout() {
        authRepository.signOut()
    }

    fun loadAdminUsers() {
        viewModelScope.launch {
            _isAdminManagementLoading.value = true
            apiRepository.getAdminUsers()
                .onSuccess { _adminUsers.value = it }
                .onFailure { _adminManagementMessage.value = "Unable to load faculty accounts. Please try again." }
            _isAdminManagementLoading.value = false
        }
    }

    fun inviteAdmin(email: String) {
        viewModelScope.launch {
            _isAdminManagementLoading.value = true
            _adminManagementMessage.value = null
            apiRepository.inviteAdmin(email.trim())
                .onSuccess {
                    _adminManagementMessage.value = "Faculty account added. They can continue with their verified Google account."
                    apiRepository.getAdminUsers().onSuccess { _adminUsers.value = it }
                }
                .onFailure { _adminManagementMessage.value = "Unable to add that faculty account. Check the email and try again." }
            _isAdminManagementLoading.value = false
        }
    }

    fun updateAdminStatus(userId: Int, status: String) {
        viewModelScope.launch {
            _isAdminManagementLoading.value = true
            _adminManagementMessage.value = null
            apiRepository.updateAdminUserStatus(userId, status)
                .onSuccess {
                    _adminManagementMessage.value = "Faculty account updated."
                    apiRepository.getAdminUsers().onSuccess { _adminUsers.value = it }
                }
                .onFailure { _adminManagementMessage.value = "Unable to update that faculty account. Please try again." }
            _isAdminManagementLoading.value = false
        }
    }

    fun clearAdminManagementMessage() {
        _adminManagementMessage.value = null
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

    // API Methods
    fun fetchLatestReadingFromApi(nodeId: String) {
        viewModelScope.launch {
            _isLoading.value = true
            _apiError.value = null

            val result = apiRepository.getLatestReading(nodeId)
            result.onSuccess { reading ->
                _apiLatestReading.value = reading
                // Automatically fetch alerts after successful reading fetch
                fetchAlertsFromApi(nodeId)
                // Forecast only from backend-stored, timestamped observations.
                generateForecastFromApi(nodeId)
            }.onFailure { error ->
                _apiError.value = error.localizedMessage ?: "Failed to fetch latest reading"
                _isLoading.value = false
            }
        }
    }

    fun fetchHistoricalReadingsFromApi(nodeId: String, limit: Int? = null) {
        viewModelScope.launch {
            val result = apiRepository.getHistoricalReadings(nodeId, limit)
            result.onSuccess { history ->
                _apiHistoricalReadings.value = history.readings
            }.onFailure { error ->
                Log.e("HydroViewModel", "Failed to fetch historical readings", error)
                // Don't set error state for historical readings failure, just log it
            }
        }
    }

    fun fetchAlertsFromApi(nodeId: String) {
        viewModelScope.launch {
            val result = apiRepository.getAlerts(nodeId)
            result.onSuccess { alerts ->
                _apiAlerts.value = alerts.alerts
            }.onFailure { error ->
                Log.e("HydroViewModel", "Failed to fetch alerts", error)
                // Don't set error state for alerts failure, just log it
            }
        }
    }

    fun generateForecastFromApi(nodeId: String = _selectedNodeId.value) {
        viewModelScope.launch {
            _isLoading.value = true
            _apiError.value = null
            val historyResult = apiRepository.getHistoricalReadings(nodeId, limit = 1000)
            historyResult.onSuccess { history ->
                _apiHistoricalReadings.value = history.readings
                val forecastResult = apiRepository.generateForecast(nodeId, history.readings)
                forecastResult.onSuccess { forecast ->
                    _apiForecast.value = forecast
                }.onFailure { error ->
                    _apiForecast.value = null
                    _apiError.value = error.localizedMessage ?: "Not enough historical data yet"
                }
            }.onFailure { error ->
                _apiForecast.value = null
                _apiError.value = error.localizedMessage ?: "Unable to load historical readings"
            }
            _isLoading.value = false
        }
    }

    fun refreshApiData(nodeId: String) {
        fetchLatestReadingFromApi(nodeId)
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
