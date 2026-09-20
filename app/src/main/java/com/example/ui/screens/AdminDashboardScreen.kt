package com.example.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ExitToApp
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
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.data.database.*
import com.example.ui.components.*
import com.example.ui.theme.*
import com.example.ui.viewmodel.HydroViewModel
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AdminDashboardScreen(
    viewModel: HydroViewModel,
    onLogout: () -> Unit,
    modifier: Modifier = Modifier
) {
    val isDark = isSystemInDarkTheme()
    val currentUser by viewModel.currentUser.collectAsState()

    val nodes by viewModel.allNodes.collectAsState()
    val selectedNodeId by viewModel.selectedNodeId.collectAsState()
    val latestReading by viewModel.latestReading.collectAsState()
    val historicalReadings by viewModel.historicalReadings.collectAsState()
    val prediction by viewModel.prediction.collectAsState()
    val activeAlerts by viewModel.activeAlerts.collectAsState()

    val waterFeedback by viewModel.waterFeedbackList.collectAsState()
    val hostelFeedback by viewModel.hostelFeedbackList.collectAsState()
    val reports by viewModel.reportsList.collectAsState()
    val auditLogs by viewModel.auditLogs.collectAsState()

    // Administrative Section Tab State
    var activeAdminTab by remember { mutableStateOf("ANALYTICS") } // "ANALYTICS", "FEEDBACK", "THRESHOLDS", "REPORTS"

    // Feedback filters from ViewModel
    val filterStatus by viewModel.feedbackFilterStatus.collectAsState()
    val filterBlock by viewModel.feedbackFilterBlock.collectAsState()

    // Overlay/Dialog States
    var showResolveDialog by remember { mutableStateOf<Any?>(null) } // WaterFeedback or HostelFeedback
    var resolveRemarks by remember { mutableStateOf("") }
    var resolveStaff by remember { mutableStateOf("") }

    var showThresholdDialog by remember { mutableStateOf<String?>(null) } // Parameter name
    var newThresholdValue by remember { mutableStateOf("") }

    var showReportDialog by remember { mutableStateOf(false) }
    var reportTitle by remember { mutableStateOf("Weekly Water Audit - ${SimpleDateFormat("MMM W", Locale.getDefault()).format(Date())}") }
    var reportSummary by remember { mutableStateOf("Overall campus water infrastructure health is stable with zero critical contaminants.") }

    // Helper calculation stats
    val safetyScore = remember(latestReading) {
        val reading = latestReading ?: return@remember 95
        var base = 100
        val phDiff = Math.abs(reading.ph - 7.2f)
        if (phDiff > 1.3f) base -= 25 else if (phDiff > 0.5f) base -= 10
        if (reading.turbidity > 5.0f) base -= 40 else if (reading.turbidity > 3.0f) base -= 15
        if (reading.tds > 500f) base -= 30 else if (reading.tds > 300f) base -= 10
        base.coerceIn(5, 100)
    }

    val backgroundBrush = if (isDark) DarkMeshBackground else LightMeshBackground

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                text = "HydroGuard",
                                fontSize = 20.sp,
                                fontWeight = FontWeight.Black,
                                letterSpacing = (-0.5).sp,
                                color = CobaltBlue
                            )
                            Spacer(modifier = Modifier.width(6.dp))
                            Text(
                                text = "Central Command",
                                fontSize = 16.sp,
                                fontWeight = FontWeight.Bold,
                                color = CeruleanBlueBright
                            )
                        }
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(6.dp)
                        ) {
                            Box(
                                modifier = Modifier
                                    .size(6.dp)
                                    .clip(CircleShape)
                                    .background(SafeGreen)
                            )
                            Text(
                                text = "AUTHENTICATED: ${currentUser?.name?.uppercase() ?: "COMMAND ADMIN"} • INFRASTRUCTURE ROOT",
                                style = MaterialTheme.typography.labelSmall,
                                color = SlateBlueSubtle
                            )
                        }
                    }
                },
                actions = {
                    IconButton(
                        onClick = { viewModel.toggleDarkMode() },
                        modifier = Modifier.testTag("admin_theme_btn")
                    ) {
                        Icon(
                            imageVector = if (isDark) Icons.Default.LightMode else Icons.Default.DarkMode,
                            contentDescription = "Theme",
                            tint = if (isDark) CeruleanBlueLight else CobaltBlue
                        )
                    }
                    IconButton(
                        onClick = {
                            viewModel.logout()
                            onLogout()
                        },
                        modifier = Modifier.testTag("admin_logout_btn")
                    ) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Filled.ExitToApp,
                            contentDescription = "Logout",
                            tint = SlateBlueSubtle
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = if (isDark) GlassSurfaceDark else GlassSurfaceLight
                ),
                modifier = Modifier.border(
                    BorderStroke(1.dp, if (isDark) GlassBorderDark else GlassBorderLight)
                )
            )
        }
    ) { innerPadding ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .background(backgroundBrush)
                .padding(innerPadding)
        ) {
            // Live Status Banner Indicator
            Box(modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp)) {
                ConnectionIndicator(
                    status = "ONLINE",
                    lastUpdated = SimpleDateFormat("hh:mm:ss a", Locale.getDefault()).format(Date())
                )
            }

            // Top Quick Metrics Bento Roll
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 6.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                AdminMetricPill(
                    label = "ACTIVE ALARMS",
                    value = activeAlerts.size.toString(),
                    color = if (activeAlerts.isNotEmpty()) CriticalRed else SafeGreen,
                    modifier = Modifier.weight(1f)
                )
                AdminMetricPill(
                    label = "OPEN TICKETS",
                    value = (waterFeedback.count { it.status == "PENDING" } + hostelFeedback.count { it.status == "PENDING" }).toString(),
                    color = WarningAmber,
                    modifier = Modifier.weight(1f)
                )
                AdminMetricPill(
                    label = "PURITY INDEX",
                    value = "$safetyScore%",
                    color = if (safetyScore >= 75) SafeGreen else CriticalRed,
                    modifier = Modifier.weight(1f)
                )
            }

            // Glassmorphic Segmented Tabs
            ScrollableTabRow(
                selectedTabIndex = when (activeAdminTab) {
                    "ANALYTICS" -> 0
                    "FEEDBACK" -> 1
                    "THRESHOLDS" -> 2
                    else -> 3
                },
                containerColor = if (isDark) GlassSurfaceDark else GlassSurfaceLight,
                contentColor = CobaltBlue,
                edgePadding = 16.dp,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 4.dp)
                    .border(BorderStroke(1.dp, if (isDark) GlassBorderDark else GlassBorderLight))
            ) {
                Tab(
                    selected = activeAdminTab == "ANALYTICS",
                    onClick = { activeAdminTab = "ANALYTICS" },
                    text = {
                        Text(
                            text = "Visual Analytics",
                            fontWeight = if (activeAdminTab == "ANALYTICS") FontWeight.ExtraBold else FontWeight.Bold,
                            fontSize = 12.sp,
                            color = if (activeAdminTab == "ANALYTICS") CobaltBlue else SlateBlueSubtle
                        )
                    },
                    modifier = Modifier.testTag("admin_tab_analytics")
                )
                Tab(
                    selected = activeAdminTab == "FEEDBACK",
                    onClick = { activeAdminTab = "FEEDBACK" },
                    text = {
                        Text(
                            text = "Student Desk",
                            fontWeight = if (activeAdminTab == "FEEDBACK") FontWeight.ExtraBold else FontWeight.Bold,
                            fontSize = 12.sp,
                            color = if (activeAdminTab == "FEEDBACK") CobaltBlue else SlateBlueSubtle
                        )
                    },
                    modifier = Modifier.testTag("admin_tab_feedback")
                )
                Tab(
                    selected = activeAdminTab == "THRESHOLDS",
                    onClick = { activeAdminTab = "THRESHOLDS" },
                    text = {
                        Text(
                            text = "IoT Thresholds",
                            fontWeight = if (activeAdminTab == "THRESHOLDS") FontWeight.ExtraBold else FontWeight.Bold,
                            fontSize = 12.sp,
                            color = if (activeAdminTab == "THRESHOLDS") CobaltBlue else SlateBlueSubtle
                        )
                    },
                    modifier = Modifier.testTag("admin_tab_thresholds")
                )
                Tab(
                    selected = activeAdminTab == "REPORTS",
                    onClick = { activeAdminTab = "REPORTS" },
                    text = {
                        Text(
                            text = "Audit Reports",
                            fontWeight = if (activeAdminTab == "REPORTS") FontWeight.ExtraBold else FontWeight.Bold,
                            fontSize = 12.sp,
                            color = if (activeAdminTab == "REPORTS") CobaltBlue else SlateBlueSubtle
                        )
                    },
                    modifier = Modifier.testTag("admin_tab_reports")
                )
            }

            // Central Dashboard Content
            LazyColumn(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
                contentPadding = PaddingValues(bottom = 36.dp, top = 10.dp)
            ) {
                // Node Selector & Visual Analytics Tab
                if (activeAdminTab == "ANALYTICS") {
                    item {
                        Column {
                            Text(
                                text = "MONITORED STORAGE TANK NODE",
                                style = MaterialTheme.typography.labelSmall,
                                color = SlateBlueSubtle
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                            LazyRow(
                                horizontalArrangement = Arrangement.spacedBy(10.dp)
                            ) {
                                items(nodes) { node ->
                                    val isSelected = node.nodeId == selectedNodeId
                                    Box(
                                        modifier = Modifier
                                            .testTag("admin_node_selector_${node.nodeId}")
                                            .clip(RoundedCornerShape(14.dp))
                                            .background(
                                                if (isSelected) CobaltBlue
                                                else if (isDark) GlassSurfaceDark else GlassSurfaceLight
                                            )
                                            .border(
                                                width = 1.dp,
                                                color = if (isSelected) CobaltBlueLight
                                                else if (isDark) GlassBorderDark else GlassBorderLight,
                                                shape = RoundedCornerShape(14.dp)
                                            )
                                            .clickable { viewModel.selectNode(node.nodeId) }
                                            .padding(horizontal = 14.dp, vertical = 9.dp)
                                    ) {
                                        Text(
                                            text = node.name,
                                            fontSize = 12.sp,
                                            fontWeight = if (isSelected) FontWeight.ExtraBold else FontWeight.Bold,
                                            color = if (isSelected) CoolWhite else MaterialTheme.colorScheme.onSurface
                                        )
                                    }
                                }
                            }
                        }
                    }

                    // Water Safety Radial Gauge
                    item {
                        WaterSafetyGauge(score = safetyScore)
                    }

                    // Live Bento Metrics
                    item {
                        latestReading?.let { reading ->
                            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                    KPIBentoCard(
                                        title = "pH Level",
                                        value = String.format("%.2f", reading.ph),
                                        unit = "pH",
                                        status = when {
                                            reading.ph in 6.5f..8.5f -> "Excellent"
                                            reading.ph in 6.0f..6.5f || reading.ph in 8.5f..9.0f -> "Good"
                                            else -> "Critical"
                                        },
                                        readingsHistory = historicalReadings.map { it.ph },
                                        modifier = Modifier.weight(1f)
                                    )
                                    KPIBentoCard(
                                        title = "Turbidity",
                                        value = String.format("%.1f", reading.turbidity),
                                        unit = "NTU",
                                        status = when {
                                            reading.turbidity < 1.5f -> "Excellent"
                                            reading.turbidity < 3.0f -> "Good"
                                            reading.turbidity < 5.0f -> "Warning"
                                            else -> "Critical"
                                        },
                                        readingsHistory = historicalReadings.map { it.turbidity },
                                        modifier = Modifier.weight(1f)
                                    )
                                }

                                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                    KPIBentoCard(
                                        title = "TDS Hardness",
                                        value = String.format("%.0f", reading.tds),
                                        unit = "mg/L",
                                        status = when {
                                            reading.tds < 150f -> "Excellent"
                                            reading.tds < 300f -> "Good"
                                            reading.tds < 500f -> "Warning"
                                            else -> "Critical"
                                        },
                                        readingsHistory = historicalReadings.map { it.tds },
                                        modifier = Modifier.weight(1f)
                                    )
                                    KPIBentoCard(
                                        title = "Flow Velocity",
                                        value = String.format("%.1f", reading.flowRate),
                                        unit = "L/min",
                                        status = if (reading.flowRate > 2.0f) "Good" else "Warning",
                                        readingsHistory = historicalReadings.map { it.flowRate },
                                        modifier = Modifier.weight(1f)
                                    )
                                }
                            }
                        }
                    }

                    // Water Quality & Telemetry Health Assessment Card
                    item {
                        prediction?.let { pred ->
                            GlassCard(
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(24.dp),
                                isDark = isDark,
                                borderGlow = CobaltBlue.copy(alpha = 0.35f)
                            ) {
                                Column(
                                    modifier = Modifier
                                        .background(
                                            Brush.linearGradient(
                                                colors = listOf(
                                                    CobaltBlue.copy(alpha = if (isDark) 0.15f else 0.06f),
                                                    CeruleanBlueBright.copy(alpha = if (isDark) 0.08f else 0.02f)
                                                )
                                            )
                                        )
                                        .padding(20.dp)
                                ) {
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Row(verticalAlignment = Alignment.CenterVertically) {
                                            Icon(
                                                imageVector = Icons.Default.Analytics,
                                                contentDescription = "Analytics",
                                                tint = CobaltBlue,
                                                modifier = Modifier.size(24.dp)
                                            )
                                            Spacer(modifier = Modifier.width(8.dp))
                                            Text(
                                                text = "Water Quality & Telemetry Health Assessment",
                                                style = MaterialTheme.typography.titleMedium,
                                                fontWeight = FontWeight.ExtraBold,
                                                color = MaterialTheme.colorScheme.onSurface
                                            )
                                        }
                                        Box(
                                            modifier = Modifier
                                                .clip(RoundedCornerShape(50))
                                                .background(SafeGreen.copy(alpha = 0.15f))
                                                .border(1.dp, SafeGreen.copy(alpha = 0.3f), RoundedCornerShape(50))
                                                .padding(horizontal = 8.dp, vertical = 3.dp)
                                        ) {
                                            Text(
                                                text = "HEALTH: ${pred.confidence.toInt()}%",
                                                style = MaterialTheme.typography.labelSmall,
                                                color = SafeGreen
                                            )
                                        }
                                    }

                                    Spacer(modifier = Modifier.height(10.dp))
                                    Text(
                                        text = pred.predictionText,
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = MaterialTheme.colorScheme.onSurface,
                                        lineHeight = 20.sp
                                    )

                                    Spacer(modifier = Modifier.height(16.dp))

                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween
                                    ) {
                                        ForecastStatItem(
                                            label = "CONTAMINATION SCORE",
                                            value = "${pred.contaminationProbability.toInt()}%",
                                            color = if (pred.contaminationProbability > 25f) CriticalRed else SafeGreen
                                        )
                                        ForecastStatItem(
                                            label = "7-DAY PRED. pH",
                                            value = String.format("%.2f", pred.predictedPh),
                                            color = CobaltBlue
                                        )
                                        ForecastStatItem(
                                            label = "7-DAY PRED. TDS",
                                            value = String.format("%.0f mg/L", pred.predictedTds),
                                            color = CeruleanBlueBright
                                        )
                                    }
                                }
                            }
                        }
                    }

                    // Interactive Trends Chart
                    item {
                        InteractiveTrendChart(
                            readings = historicalReadings,
                            paramSelector = { it.turbidity },
                            label = "Turbidity Stream",
                            unit = "NTU",
                            color = SmartTeal
                        )
                    }

                    // Contamination segment Donut
                    item {
                        DonutContaminationChart(riskPercentage = prediction?.riskScore ?: 10f)
                    }

                    // Active Alarms timeline panel
                    item {
                        AlertTimeline(alerts = activeAlerts)
                    }
                }

                // Student Feedback Management Dashboard
                if (activeAdminTab == "FEEDBACK") {
                    // Filters row
                    item {
                        GlassCard(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(18.dp),
                            isDark = isDark
                        ) {
                            Column(modifier = Modifier.padding(16.dp)) {
                                Text(
                                    text = "TRIAGE FILTER CONSOLE",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = CeruleanBlueBright
                                )
                                Spacer(modifier = Modifier.height(10.dp))

                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                                ) {
                                    // Status Category filter
                                    AdminFilterPill(
                                        label = "STATUS: $filterStatus",
                                        onClick = {
                                            viewModel.feedbackFilterStatus.value = when (filterStatus) {
                                                "ALL" -> "PENDING"
                                                "PENDING" -> "RESOLVED"
                                                else -> "ALL"
                                            }
                                        },
                                        modifier = Modifier.weight(1f)
                                    )

                                    // Block Filter
                                    AdminFilterPill(
                                        label = "BLOCK: $filterBlock",
                                        onClick = {
                                            viewModel.feedbackFilterBlock.value = when (filterBlock) {
                                                "ALL" -> "A"
                                                "A" -> "B"
                                                "B" -> "Mess"
                                                else -> "ALL"
                                            }
                                        },
                                        modifier = Modifier.weight(1f)
                                    )
                                }
                            }
                        }
                    }

                    // Water Complaints items (filtered)
                    val filteredWater = waterFeedback.filter { fb ->
                        (filterStatus == "ALL" || fb.status == filterStatus) &&
                        (filterBlock == "ALL" || fb.hostelBlock == filterBlock)
                    }

                    if (filteredWater.isNotEmpty()) {
                        item {
                            Text(
                                text = "Resident Observations & Hardness Reports (${filteredWater.size})",
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.ExtraBold,
                                color = MaterialTheme.colorScheme.onBackground
                            )
                        }

                        items(filteredWater) { fb ->
                            GlassCard(
                                modifier = Modifier
                                    .testTag("water_feedback_item_${fb.id}")
                                    .fillMaxWidth(),
                                shape = RoundedCornerShape(18.dp),
                                isDark = isDark
                            ) {
                                Column(modifier = Modifier.padding(16.dp)) {
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Row(verticalAlignment = Alignment.CenterVertically) {
                                            Icon(
                                                imageVector = Icons.Default.WaterDrop,
                                                contentDescription = null,
                                                tint = CeruleanBlueBright,
                                                modifier = Modifier.size(18.dp)
                                            )
                                            Spacer(modifier = Modifier.width(6.dp))
                                            Text(
                                                text = fb.issueType,
                                                style = MaterialTheme.typography.titleSmall,
                                                fontWeight = FontWeight.Bold
                                            )
                                        }

                                        Box(
                                            modifier = Modifier
                                                .clip(RoundedCornerShape(50))
                                                .background(
                                                    if (fb.status == "RESOLVED") SafeGreen.copy(alpha = 0.12f)
                                                    else WarningAmber.copy(alpha = 0.12f)
                                                )
                                                .border(
                                                    1.dp,
                                                    if (fb.status == "RESOLVED") SafeGreen.copy(alpha = 0.3f)
                                                    else WarningAmber.copy(alpha = 0.3f),
                                                    RoundedCornerShape(50)
                                                )
                                                .padding(horizontal = 8.dp, vertical = 2.dp)
                                        ) {
                                            Text(
                                                text = fb.status,
                                                style = MaterialTheme.typography.labelSmall,
                                                color = if (fb.status == "RESOLVED") SafeGreen else WarningAmber,
                                                fontSize = 9.sp
                                            )
                                        }
                                    }

                                    Spacer(modifier = Modifier.height(8.dp))
                                    Text(
                                        text = fb.description,
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                    Spacer(modifier = Modifier.height(10.dp))

                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Text(
                                            text = "Block ${fb.hostelBlock} • Room ${fb.roomNumber} • Rating: ${fb.rating}/5",
                                            style = MaterialTheme.typography.bodySmall,
                                            color = SlateBlueSubtle
                                        )

                                        if (fb.status == "PENDING") {
                                            Button(
                                                onClick = { showResolveDialog = fb },
                                                modifier = Modifier
                                                    .height(32.dp)
                                                    .testTag("resolve_water_${fb.id}"),
                                                contentPadding = PaddingValues(horizontal = 14.dp, vertical = 0.dp),
                                                shape = RoundedCornerShape(8.dp),
                                                colors = ButtonDefaults.buttonColors(containerColor = CobaltBlue)
                                            ) {
                                                Text("Resolve Ticket", fontSize = 11.sp, fontWeight = FontWeight.Bold)
                                            }
                                        }
                                    }

                                    if (fb.status == "RESOLVED") {
                                        Spacer(modifier = Modifier.height(8.dp))
                                        Box(
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .background(SafeGreen.copy(alpha = 0.06f))
                                                .border(1.dp, SafeGreen.copy(alpha = 0.2f), RoundedCornerShape(8.dp))
                                                .padding(10.dp)
                                        ) {
                                            Column {
                                                Text("STAFF: ${fb.assignedStaff ?: "Maintenance Team"}", style = MaterialTheme.typography.labelSmall, color = SafeGreen)
                                                Text("REMARKS: ${fb.remarks ?: "Resolved in inspection"}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurface)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    } else {
                        item {
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 40.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                Text(
                                    text = "No active resident feedback matches selected filter.",
                                    color = SlateBlueSubtle,
                                    fontSize = 13.sp
                                )
                            }
                        }
                    }
                }

                // Threshold Tuning Settings
                if (activeAdminTab == "THRESHOLDS") {
                    item {
                        GlassCard(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(24.dp),
                            isDark = isDark
                        ) {
                            Column(modifier = Modifier.padding(20.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(
                                        imageVector = Icons.Default.SettingsInputAntenna,
                                        contentDescription = null,
                                        tint = CobaltBlue
                                    )
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Text(
                                        text = "IoT Sensor Threshold Calibration",
                                        style = MaterialTheme.typography.titleMedium,
                                        fontWeight = FontWeight.ExtraBold
                                    )
                                }
                                Spacer(modifier = Modifier.height(6.dp))
                                Text(
                                    text = "Configure safe margins. Exceeding these bounds triggers automated alarms across student and maintenance portals.",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = SlateBlueSubtle
                                )

                                Spacer(modifier = Modifier.height(16.dp))

                                ThresholdItemRow(
                                    label = "pH Acidic Margin",
                                    currentLimit = "6.50",
                                    unit = "pH",
                                    onClick = {
                                        showThresholdDialog = "pH Acidic Margin"
                                        newThresholdValue = "6.50"
                                    }
                                )

                                ThresholdItemRow(
                                    label = "pH Alkaline Margin",
                                    currentLimit = "8.50",
                                    unit = "pH",
                                    onClick = {
                                        showThresholdDialog = "pH Alkaline Margin"
                                        newThresholdValue = "8.50"
                                    }
                                )

                                ThresholdItemRow(
                                    label = "Maximum Turbidity",
                                    currentLimit = "5.0",
                                    unit = "NTU",
                                    onClick = {
                                        showThresholdDialog = "Maximum Turbidity"
                                        newThresholdValue = "5.0"
                                    }
                                )

                                ThresholdItemRow(
                                    label = "Maximum TDS Limit",
                                    currentLimit = "500.0",
                                    unit = "mg/L",
                                    onClick = {
                                        showThresholdDialog = "Maximum TDS Limit"
                                        newThresholdValue = "500.0"
                                    }
                                )
                            }
                        }
                    }

                    // Audit Logs List
                    item {
                        Text(
                            text = "System Infrastructure Audit Trail",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.ExtraBold,
                            color = MaterialTheme.colorScheme.onBackground
                        )
                    }

                    items(auditLogs) { log ->
                        GlassCard(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(14.dp),
                            isDark = isDark
                        ) {
                            Row(
                                modifier = Modifier
                                    .padding(12.dp)
                                    .fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(
                                        text = log.action,
                                        style = MaterialTheme.typography.bodyMedium,
                                        fontWeight = FontWeight.Bold
                                    )
                                    Text(
                                        text = "By ${log.adminEmail}",
                                        style = MaterialTheme.typography.bodySmall,
                                        color = SlateBlueSubtle
                                    )
                                }
                                Text(
                                    text = SimpleDateFormat("hh:mm a", Locale.getDefault()).format(Date(log.timestamp)),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = SlateBlueSubtle
                                )
                            }
                        }
                    }
                }

                // Water Reports list and Generation
                if (activeAdminTab == "REPORTS") {
                    item {
                        Button(
                            onClick = { showReportDialog = true },
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(52.dp)
                                .shadow(8.dp, RoundedCornerShape(14.dp), ambientColor = Color(0x330047AB), spotColor = Color(0x660047AB))
                            .testTag("generate_report_btn"),
                            shape = RoundedCornerShape(14.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = CobaltBlue)
                        ) {
                            Icon(Icons.Default.PostAdd, contentDescription = null)
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Generate System Report Audit", fontWeight = FontWeight.Bold, fontSize = 14.sp)
                        }
                    }

                    item {
                        Text(
                            text = "Published System Audits (${reports.size})",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.ExtraBold,
                            color = MaterialTheme.colorScheme.onBackground
                        )
                    }

                    items(reports) { rep ->
                        GlassCard(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(18.dp),
                            isDark = isDark
                        ) {
                            Column(modifier = Modifier.padding(16.dp)) {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text(
                                        text = rep.title,
                                        style = MaterialTheme.typography.titleSmall,
                                        fontWeight = FontWeight.ExtraBold
                                    )
                                    Text(
                                        text = SimpleDateFormat("dd MMM yyyy", Locale.getDefault()).format(Date(rep.generatedAt)),
                                        style = MaterialTheme.typography.labelSmall,
                                        color = SlateBlueSubtle
                                    )
                                }

                                Spacer(modifier = Modifier.height(6.dp))
                                Text(
                                    text = rep.summary,
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                                Spacer(modifier = Modifier.height(10.dp))

                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Text(
                                        text = "Avg pH: ${rep.avgPh}",
                                        fontSize = 11.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = CobaltBlue
                                    )
                                    Text(
                                        text = "Avg Turbidity: ${rep.avgTurbidity} NTU",
                                        fontSize = 11.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = CeruleanBlueBright
                                    )
                                    Text(
                                        text = "Alarms: ${rep.totalAlerts}",
                                        fontSize = 11.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = CriticalRed
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // Resolve dialog for feedback tickets
    showResolveDialog?.let { obj ->
        AlertDialog(
            onDismissRequest = { showResolveDialog = null },
            title = {
                Text("Resolve Complaint Ticket", fontWeight = FontWeight.ExtraBold)
            },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(
                        "Provide remarks and assign personnel to formally close this report.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = SlateBlueSubtle
                    )
                    
                    OutlinedTextField(
                        value = resolveRemarks,
                        onValueChange = { resolveRemarks = it },
                        label = { Text("Resolution Remarks") },
                        placeholder = { Text("e.g. Cleared filter valve. Backwashed tank.") },
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.fillMaxWidth()
                    )

                    OutlinedTextField(
                        value = resolveStaff,
                        onValueChange = { resolveStaff = it },
                        label = { Text("Assigned Maintenance Staff") },
                        placeholder = { Text("e.g. Facilities Operations Team") },
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.fillMaxWidth()
                    )
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        val remarks = resolveRemarks.ifBlank { "Addressed by facilities team." }
                        val staff = resolveStaff.ifBlank { "Hostel Staff" }
                        
                        when (obj) {
                            is WaterFeedback -> viewModel.resolveWaterComplaint(obj.id, remarks, staff)
                            is HostelFeedback -> viewModel.resolveHostelComplaint(obj.id, remarks, staff)
                        }

                        resolveRemarks = ""
                        resolveStaff = ""
                        showResolveDialog = null
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = CobaltBlue),
                    shape = RoundedCornerShape(10.dp),
                    modifier = Modifier.testTag("dialog_confirm_resolve")
                ) {
                    Text("Confirm Resolution", fontWeight = FontWeight.Bold)
                }
            },
            dismissButton = {
                TextButton(onClick = { showResolveDialog = null }) {
                    Text("Cancel", color = SlateBlueSubtle)
                }
            },
            shape = RoundedCornerShape(22.dp),
            containerColor = if (isDark) GlassSurfaceDark else CoolWhite
        )
    }

    // Threshold adjust dialog
    showThresholdDialog?.let { param ->
        AlertDialog(
            onDismissRequest = { showThresholdDialog = null },
            title = { Text("Calibrate $param", fontWeight = FontWeight.ExtraBold) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(
                        "Configure new IoT sensor safety threshold limit:",
                        style = MaterialTheme.typography.bodyMedium,
                        color = SlateBlueSubtle
                    )
                    OutlinedTextField(
                        value = newThresholdValue,
                        onValueChange = { newThresholdValue = it },
                        label = { Text("New Threshold Value") },
                        singleLine = true,
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.fillMaxWidth()
                    )
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        val value = newThresholdValue.toFloatOrNull()
                        if (value != null) {
                            viewModel.updateThreshold("node_overhead_a", param, value)
                        }
                        showThresholdDialog = null
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = CobaltBlue),
                    shape = RoundedCornerShape(10.dp),
                    modifier = Modifier.testTag("dialog_confirm_threshold")
                ) {
                    Text("Save Threshold", fontWeight = FontWeight.Bold)
                }
            },
            dismissButton = {
                TextButton(onClick = { showThresholdDialog = null }) {
                    Text("Cancel", color = SlateBlueSubtle)
                }
            },
            shape = RoundedCornerShape(22.dp),
            containerColor = if (isDark) GlassSurfaceDark else CoolWhite
        )
    }

    // Report Generation Dialog
    if (showReportDialog) {
        AlertDialog(
            onDismissRequest = { showReportDialog = false },
            title = { Text("Generate Audit Report", fontWeight = FontWeight.ExtraBold) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(
                        "Compile all chemical telemetry, active sensor alarms, and resident reports into a permanent compliance log.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = SlateBlueSubtle
                    )
                    
                    OutlinedTextField(
                        value = reportTitle,
                        onValueChange = { reportTitle = it },
                        label = { Text("Report Title") },
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.fillMaxWidth()
                    )

                    OutlinedTextField(
                        value = reportSummary,
                        onValueChange = { reportSummary = it },
                        label = { Text("Executive Audit Summary") },
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.fillMaxWidth()
                    )
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        viewModel.exportWeeklyReport(
                            title = reportTitle,
                            summary = reportSummary,
                            ph = latestReading?.ph ?: 7.2f,
                            turb = latestReading?.turbidity ?: 1.2f,
                            tds = latestReading?.tds ?: 180f,
                            alerts = activeAlerts.size,
                            complaints = waterFeedback.count { it.status == "PENDING" }
                        )
                        showReportDialog = false
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = CobaltBlue),
                    shape = RoundedCornerShape(10.dp),
                    modifier = Modifier.testTag("dialog_confirm_report")
                ) {
                    Text("Export Audit", fontWeight = FontWeight.Bold)
                }
            },
            dismissButton = {
                TextButton(onClick = { showReportDialog = false }) {
                    Text("Cancel", color = SlateBlueSubtle)
                }
            },
            shape = RoundedCornerShape(22.dp),
            containerColor = if (isDark) GlassSurfaceDark else CoolWhite
        )
    }
}

@Composable
fun AdminFilterPill(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val isDark = isSystemInDarkTheme()
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(10.dp))
            .background(if (isDark) GlassSurfaceDark else GlassSurfaceLight)
            .border(1.dp, if (isDark) GlassBorderDark else GlassBorderLight, RoundedCornerShape(10.dp))
            .clickable { onClick() }
            .padding(horizontal = 10.dp, vertical = 8.dp),
        contentAlignment = Alignment.Center
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurface
        )
    }
}

@Composable
fun ThresholdItemRow(
    label: String,
    currentLimit: String,
    unit: String,
    onClick: () -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onClick() }
            .padding(vertical = 12.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column {
            Text(
                text = label,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Bold
            )
            Text(
                text = "Alarms trigger outside this boundary",
                style = MaterialTheme.typography.bodySmall,
                color = SlateBlueSubtle
            )
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = "$currentLimit $unit",
                fontSize = 13.sp,
                fontWeight = FontWeight.ExtraBold,
                color = CobaltBlue
            )
            Spacer(modifier = Modifier.width(6.dp))
            Icon(
                imageVector = Icons.Default.Edit,
                contentDescription = null,
                modifier = Modifier.size(16.dp),
                tint = CeruleanBlueBright
            )
        }
    }
}
