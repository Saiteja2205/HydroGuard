package com.example.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.ui.components.*
import com.example.ui.theme.*
import com.example.ui.viewmodel.HydroViewModel
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StudentDashboardScreen(
    viewModel: HydroViewModel,
    onNavigateToFeedback: () -> Unit,
    onLogout: () -> Unit,
    modifier: Modifier = Modifier
) {
    val currentUser by viewModel.currentUser.collectAsState()
    val isDark by viewModel.isDarkMode.collectAsState()

    val nodes by viewModel.allNodes.collectAsState()
    val selectedNodeId by viewModel.selectedNodeId.collectAsState()
    val latestReading by viewModel.latestReading.collectAsState()
    val historicalReadings by viewModel.historicalReadings.collectAsState()
    val prediction by viewModel.prediction.collectAsState()
    val activeAlerts by viewModel.activeAlerts.collectAsState()

    // Keep track of active chart parameter
    var selectedChartParam by remember { mutableStateOf("Turbidity") } // "pH", "Turbidity", "TDS"

    // Helper: calculate safety score
    val safetyScore = remember(latestReading) {
        val reading = latestReading ?: return@remember 95
        var base = 100
        
        // pH drift deduction
        val phDiff = Math.abs(reading.ph - 7.2f)
        if (phDiff > 1.3f) base -= 25 else if (phDiff > 0.5f) base -= 10

        // Turbidity deduction
        if (reading.turbidity > 5.0f) base -= 40 else if (reading.turbidity > 3.0f) base -= 15

        // TDS deduction
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
                            Spacer(modifier = Modifier.width(4.dp))
                            Text(
                                text = "Resident Portal",
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
                                text = "HOSTEL BLOCK ${currentUser?.hostelBlock ?: "A"} • ROOM ${currentUser?.roomNumber ?: ""}",
                                style = MaterialTheme.typography.labelSmall,
                                color = SlateBlueSubtle
                            )
                        }
                    }
                },
                actions = {
                    IconButton(
                        onClick = { viewModel.toggleDarkMode() },
                        modifier = Modifier.testTag("student_theme_btn")
                    ) {
                        Icon(
                            imageVector = if (isDark) Icons.Default.LightMode else Icons.Default.DarkMode,
                            contentDescription = "Toggle Theme",
                            tint = if (isDark) CeruleanBlueLight else CobaltBlue
                        )
                    }
                    IconButton(
                        onClick = {
                            viewModel.logout()
                            onLogout()
                        },
                        modifier = Modifier.testTag("student_logout_btn")
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
        },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = onNavigateToFeedback,
                icon = { Icon(Icons.Default.RateReview, contentDescription = "Feedback") },
                text = {
                    Text(
                        text = "Report Issue",
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 0.3.sp
                    )
                },
                containerColor = CeruleanBlueBright,
                contentColor = CoolWhite,
                shape = RoundedCornerShape(16.dp),
                modifier = Modifier
                    .testTag("submit_feedback_fab")
                    .shadow(8.dp, RoundedCornerShape(16.dp), ambientColor = Color(0x33007BA7), spotColor = Color(0x660047AB))
            )
        }
    ) { innerPadding ->
        LazyColumn(
            modifier = modifier
                .fillMaxSize()
                .background(backgroundBrush)
                .padding(innerPadding)
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
            contentPadding = PaddingValues(bottom = 88.dp, top = 12.dp)
        ) {
            // Live Status Header Indicator
            item {
                ConnectionIndicator(
                    status = "ONLINE",
                    lastUpdated = SimpleDateFormat("hh:mm:ss a", Locale.getDefault()).format(Date())
                )
            }

            // Segmented Storage Nodes Filter
            item {
                Column {
                    Text(
                        text = "MONITORING TANK NODES",
                        style = MaterialTheme.typography.labelSmall,
                        color = SlateBlueSubtle
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    LazyRow(
                        horizontalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        items(nodes) { node ->
                            val isSelected = node.nodeId == selectedNodeId
                            val nodeStatusColor = if (node.status == "ONLINE") SafeGreen else WarningAmber
                            
                            Box(
                                modifier = Modifier
                                    .testTag("node_selector_${node.nodeId}")
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
                                    .padding(horizontal = 14.dp, vertical = 10.dp)
                            ) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Box(
                                        modifier = Modifier
                                            .size(7.dp)
                                            .clip(CircleShape)
                                            .background(nodeStatusColor)
                                    )
                                    Spacer(modifier = Modifier.width(8.dp))
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
            }

            // Radial Water Gauge
            item {
                WaterSafetyGauge(score = safetyScore)
            }

            // Live Alert Box published by Admin
            item {
                AnimatedVisibility(visible = activeAlerts.isNotEmpty()) {
                    GlassCard(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(20.dp),
                        isDark = isDark,
                        borderGlow = CriticalRed.copy(alpha = 0.4f)
                    ) {
                        Row(
                            modifier = Modifier
                                .background(CriticalRed.copy(alpha = 0.08f))
                                .padding(16.dp),
                            verticalAlignment = Alignment.Top
                        ) {
                            Icon(
                                imageVector = Icons.Default.CrisisAlert,
                                contentDescription = "Alert",
                                tint = CriticalRed,
                                modifier = Modifier.size(28.dp)
                            )
                            Spacer(modifier = Modifier.width(14.dp))
                            Column {
                                Text(
                                    text = "Hostel Water Quality Warning",
                                    fontWeight = FontWeight.Black,
                                    color = CriticalRed,
                                    fontSize = 14.sp
                                )
                                Spacer(modifier = Modifier.height(4.dp))
                                Text(
                                    text = activeAlerts.firstOrNull()?.let {
                                        "${it.title}. Under current analysis at ${it.parameterName} = ${it.value}. Administrative advisory: ${it.recommendation}."
                                    } ?: "Elevated impurity levels detected. Maintenance crews are performing flushing. Use alternate supply blocks.",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurface
                                )
                            }
                        }
                    }
                }
            }

            // Live Readings Bento Grid Section
            item {
                Column {
                    Text(
                        text = "LIVE SENSOR TELEMETRY",
                        style = MaterialTheme.typography.labelSmall,
                        color = CeruleanBlueBright
                    )
                    Spacer(modifier = Modifier.height(2.dp))
                    Text(
                        text = "Real-Time Quality Parameters",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.ExtraBold,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                }
            }

            // 2-column Bento Cards of core readings
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

                        // Full-width card focused entirely on Hardwater & TDS Analysis
                        val hardnessStatus = when {
                            reading.tds < 150f -> "Soft Water"
                            reading.tds < 300f -> "Moderately Hard"
                            reading.tds < 500f -> "Hard (Scaling Risk)"
                            else -> "Very Hard (High Scaling)"
                        }
                        val hardnessColor = when {
                            reading.tds < 150f -> SafeGreen
                            reading.tds < 300f -> CeruleanBlueBright
                            reading.tds < 500f -> WarningAmber
                            else -> CriticalRed
                        }

                        GlassCard(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(20.dp),
                            isDark = isDark
                        ) {
                            Column(modifier = Modifier.padding(18.dp)) {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Column {
                                        Text(
                                            text = "TOTAL DISSOLVED SOLIDS (TDS)",
                                            style = MaterialTheme.typography.labelSmall,
                                            color = CeruleanBlueBright
                                        )
                                        Spacer(modifier = Modifier.height(4.dp))
                                        Row(
                                            verticalAlignment = Alignment.Bottom,
                                            horizontalArrangement = Arrangement.spacedBy(4.dp)
                                        ) {
                                            Text(
                                                text = String.format("%.0f", reading.tds),
                                                fontSize = 32.sp,
                                                fontWeight = FontWeight.Black,
                                                lineHeight = 32.sp,
                                                color = MaterialTheme.colorScheme.onSurface,
                                                letterSpacing = (-1).sp
                                            )
                                            Text(
                                                text = "mg/L (ppm)",
                                                fontSize = 12.sp,
                                                fontWeight = FontWeight.Bold,
                                                color = SlateBlueSubtle,
                                                modifier = Modifier.padding(bottom = 4.dp)
                                            )
                                        }
                                    }

                                    Box(
                                        modifier = Modifier
                                            .clip(RoundedCornerShape(50))
                                            .background(hardnessColor.copy(alpha = 0.12f))
                                            .border(1.dp, hardnessColor.copy(alpha = 0.3f), RoundedCornerShape(50))
                                            .padding(horizontal = 12.dp, vertical = 5.dp)
                                    ) {
                                        Text(
                                            text = hardnessStatus.uppercase(),
                                            style = MaterialTheme.typography.labelSmall,
                                            color = hardnessColor,
                                            fontSize = 10.sp
                                        )
                                    }
                                }

                                Spacer(modifier = Modifier.height(12.dp))
                                Text(
                                    text = if (reading.tds >= 300f) {
                                        "⚠️ Elevated hardness identified. High calcium and magnesium content may result in plumbing scaling and reduced soap lathering."
                                    } else {
                                        "✓ Healthy mineral balance. Minimal scale deposition risk on heating coils, fixtures, and hostel plumbing."
                                    },
                                    style = MaterialTheme.typography.bodySmall,
                                    color = SlateBlueSubtle,
                                    lineHeight = 16.sp
                                )
                            }
                        }

                        // Secondary row: Temperature & Flow Rate
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            KPIBentoCard(
                                title = "Temperature",
                                value = String.format("%.1f", reading.temperature),
                                unit = "°C",
                                status = if (reading.temperature in 15.0f..30.0f) "Good" else "Warning",
                                readingsHistory = historicalReadings.map { it.temperature },
                                modifier = Modifier.weight(1f)
                            )
                            KPIBentoCard(
                                title = "Flow Rate",
                                value = String.format("%.1f", reading.flowRate),
                                unit = "L/min",
                                status = if (reading.flowRate > 2.0f) "Good" else "Warning",
                                readingsHistory = historicalReadings.map { it.flowRate },
                                modifier = Modifier.weight(1f)
                            )
                        }
                    }
                } ?: Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(100.dp),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator(color = CobaltBlue)
                }
            }

            // Water Quality Advisory Card
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
                                horizontalArrangement = Arrangement.spacedBy(12.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Box(
                                    modifier = Modifier
                                        .size(44.dp)
                                        .clip(RoundedCornerShape(12.dp))
                                        .background(CobaltBlue.copy(alpha = 0.15f))
                                        .border(1.dp, CobaltBlue.copy(alpha = 0.3f), RoundedCornerShape(12.dp)),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.Water,
                                        contentDescription = "Advisory",
                                        tint = CobaltBlue,
                                        modifier = Modifier.size(24.dp)
                                    )
                                }
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(
                                        text = "WATER QUALITY ADVISORY",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = CobaltBlue
                                    )
                                    Text(
                                        text = "System Health: ${pred.confidence.toInt()}% Optimal",
                                        style = MaterialTheme.typography.titleSmall,
                                        fontWeight = FontWeight.ExtraBold,
                                        color = MaterialTheme.colorScheme.onSurface
                                    )
                                }
                            }

                            Spacer(modifier = Modifier.height(14.dp))

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
                                    label = "CONTAMINATION RISK",
                                    value = "${pred.contaminationProbability.toInt()}%",
                                    color = if (pred.contaminationProbability > 30f) WarningAmber else SafeGreen
                                )
                                ForecastStatItem(
                                    label = "PRED. pH TARGET",
                                    value = String.format("%.2f", pred.predictedPh),
                                    color = CobaltBlue
                                )
                                ForecastStatItem(
                                    label = "PRED. HARDNESS",
                                    value = String.format("%.0f mg/L", pred.predictedTds),
                                    color = CeruleanBlueBright
                                )
                            }
                        }
                    }
                }
            }

            // Interactive Trend Chart Section
            item {
                Column {
                    Text(
                        text = "HISTORICAL ANALYSIS",
                        style = MaterialTheme.typography.labelSmall,
                        color = CeruleanBlueBright
                    )
                    Spacer(modifier = Modifier.height(2.dp))
                    Text(
                        text = "12-Hour Telemetry Graphs",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.ExtraBold,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Spacer(modifier = Modifier.height(10.dp))
                    
                    // Chart parameter segmented selector with Glass Styling
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(14.dp))
                            .background(if (isDark) GlassSurfaceDark else GlassSurfaceLight)
                            .border(1.dp, if (isDark) GlassBorderDark else GlassBorderLight, RoundedCornerShape(14.dp))
                            .padding(4.dp),
                        horizontalArrangement = Arrangement.SpaceEvenly
                    ) {
                        listOf("Turbidity", "pH", "TDS").forEach { param ->
                            val isSelected = param == selectedChartParam
                            Box(
                                modifier = Modifier
                                    .weight(1f)
                                    .clip(RoundedCornerShape(10.dp))
                                    .background(
                                        if (isSelected) CobaltBlue
                                        else Color.Transparent
                                    )
                                    .clickable { selectedChartParam = param }
                                    .padding(vertical = 8.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                Text(
                                    text = param.uppercase(),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = if (isSelected) CoolWhite else SlateBlueSubtle
                                )
                            }
                        }
                    }
                    
                    Spacer(modifier = Modifier.height(12.dp))

                    InteractiveTrendChart(
                        readings = historicalReadings,
                        paramSelector = { r ->
                            when (selectedChartParam) {
                                "pH" -> r.ph
                                "TDS" -> r.tds
                                else -> r.turbidity
                            }
                        },
                        label = selectedChartParam,
                        unit = when (selectedChartParam) {
                            "pH" -> "pH"
                            "TDS" -> "mg/L"
                            else -> "NTU"
                        },
                        color = when (selectedChartParam) {
                            "pH" -> CeruleanBlueBright
                            "TDS" -> WarningAmber
                            else -> SmartTeal
                        }
                    )
                }
            }
        }
    }
}

@Composable
fun ForecastStatItem(
    label: String,
    value: String,
    color: Color
) {
    Column(horizontalAlignment = Alignment.Start) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = SlateBlueSubtle,
            fontSize = 9.sp
        )
        Spacer(modifier = Modifier.height(2.dp))
        Text(
            text = value,
            fontSize = 16.sp,
            fontWeight = FontWeight.Black,
            color = color
        )
    }
}
