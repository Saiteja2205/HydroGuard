package com.example.ui.components

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.data.database.*
import com.example.ui.theme.*

/**
 * Reusable Glassmorphism Card Container
 * Combines translucent surface, subtle border glow, and soft shadow for Smart Infrastructure UI.
 */
@Composable
fun GlassCard(
    modifier: Modifier = Modifier,
    shape: RoundedCornerShape = RoundedCornerShape(22.dp),
    isDark: Boolean = isSystemInDarkTheme(),
    borderGlow: Color? = null,
    content: @Composable ColumnScope.() -> Unit
) {
    val surfaceColor = if (isDark) GlassSurfaceDark else GlassSurfaceLight
    val borderColor = borderGlow ?: if (isDark) GlassBorderDark else GlassBorderLight

    Card(
        modifier = modifier
            .shadow(
                elevation = if (isDark) 4.dp else 6.dp,
                shape = shape,
                ambientColor = if (isDark) Color(0x66000000) else Color(0x1A0047AB),
                spotColor = if (isDark) Color(0x33007BA7) else Color(0x200284C7)
            ),
        shape = shape,
        colors = CardDefaults.cardColors(containerColor = surfaceColor),
        border = BorderStroke(1.dp, borderColor)
    ) {
        Column(
            modifier = Modifier.fillMaxWidth(),
            content = content
        )
    }
}

/**
 * Radial Water Quality & Safety Dial with Smart Infrastructure Glassmorphism
 */
@Composable
fun WaterSafetyGauge(
    score: Int,
    modifier: Modifier = Modifier
) {
    val isDark = isSystemInDarkTheme()
    val animatedScore by animateFloatAsState(
        targetValue = score.toFloat(),
        animationSpec = tween(durationMillis = 1000),
        label = "GaugeScore"
    )

    val color = when {
        score >= 85 -> SafeGreen
        score >= 70 -> CeruleanBlueBright
        score >= 50 -> WarningAmber
        else -> CriticalRed
    }

    val statusText = when {
        score >= 85 -> "OPTIMAL POTABILITY"
        score >= 70 -> "NORMAL / SAFE"
        score >= 50 -> "INSPECTION NEEDED"
        else -> "CRITICAL BREACH"
    }

    val statusBgColor = when {
        score >= 85 -> SafeGreen.copy(alpha = 0.12f)
        score >= 70 -> CeruleanBlueBright.copy(alpha = 0.12f)
        score >= 50 -> WarningAmber.copy(alpha = 0.12f)
        else -> CriticalRed.copy(alpha = 0.15f)
    }

    GlassCard(
        modifier = modifier
            .testTag("safety_gauge_card")
            .fillMaxWidth(),
        shape = RoundedCornerShape(26.dp),
        isDark = isDark
    ) {
        Column(
            modifier = Modifier
                .padding(22.dp)
                .fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(
                        text = "WATER SAFETY INDEX",
                        style = MaterialTheme.typography.labelSmall,
                        color = CeruleanBlueBright,
                        letterSpacing = 1.2.sp
                    )
                    Spacer(modifier = Modifier.height(2.dp))
                    Text(
                        text = "Real-Time Potability Score",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.ExtraBold,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                }

                // Glowing Status Tag
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(50))
                        .background(statusBgColor)
                        .border(1.dp, color.copy(alpha = 0.3f), RoundedCornerShape(50))
                        .padding(horizontal = 10.dp, vertical = 4.dp)
                ) {
                    Text(
                        text = statusText,
                        style = MaterialTheme.typography.labelSmall,
                        color = color
                    )
                }
            }

            Spacer(modifier = Modifier.height(20.dp))

            Box(
                contentAlignment = Alignment.Center,
                modifier = Modifier.size(175.dp)
            ) {
                Canvas(modifier = Modifier.size(155.dp)) {
                    val strokeWidth = 14.dp.toPx()

                    // Background Track
                    drawArc(
                        color = if (isDark) Color(0x33334155) else Color(0x1F0047AB),
                        startAngle = 135f,
                        sweepAngle = 270f,
                        useCenter = false,
                        style = Stroke(width = strokeWidth, cap = StrokeCap.Round)
                    )

                    // Colored Progress Arc with Gradient
                    val sweepAngle = (animatedScore / 100f) * 270f
                    drawArc(
                        brush = Brush.sweepGradient(
                            colors = listOf(
                                color.copy(alpha = 0.4f),
                                color
                            )
                        ),
                        startAngle = 135f,
                        sweepAngle = sweepAngle,
                        useCenter = false,
                        style = Stroke(width = strokeWidth, cap = StrokeCap.Round)
                    )
                }

                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Row(
                        verticalAlignment = Alignment.Bottom,
                        horizontalArrangement = Arrangement.Center
                    ) {
                        Text(
                            text = "${animatedScore.toInt()}",
                            fontSize = 46.sp,
                            fontWeight = FontWeight.Black,
                            lineHeight = 46.sp,
                            color = MaterialTheme.colorScheme.onSurface,
                            letterSpacing = (-1.5).sp
                        )
                        Text(
                            text = "/100",
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold,
                            color = SlateBlueSubtle,
                            modifier = Modifier.padding(bottom = 6.dp)
                        )
                    }
                    Text(
                        text = "HEALTH SCORE",
                        style = MaterialTheme.typography.labelSmall,
                        color = SlateBlueSubtle
                    )
                }
            }

            Spacer(modifier = Modifier.height(18.dp))

            // Sub-status Indicator
            Row(
                horizontalArrangement = Arrangement.Center,
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .clip(RoundedCornerShape(50))
                    .background(color.copy(alpha = 0.08f))
                    .border(1.dp, color.copy(alpha = 0.22f), RoundedCornerShape(50))
                    .padding(horizontal = 14.dp, vertical = 6.dp)
            ) {
                Box(
                    modifier = Modifier
                        .size(8.dp)
                        .clip(CircleShape)
                        .background(color)
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = if (score >= 70) "Safe for campus consumption & domestic use" else "Active telemetry alert: Filtration check advised",
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    color = color
                )
            }
        }
    }
}

/**
 * KPI Bento Grid Card with Glassmorphism and Mini Sparkline
 */
@Composable
fun KPIBentoCard(
    title: String,
    value: String,
    unit: String,
    status: String, // "Excellent", "Good", "Warning", "Critical"
    readingsHistory: List<Float>,
    modifier: Modifier = Modifier
) {
    val isDark = isSystemInDarkTheme()
    val statusColor = when (status) {
        "Excellent" -> SafeGreen
        "Good" -> CeruleanBlueBright
        "Warning" -> WarningAmber
        "Critical" -> CriticalRed
        else -> SafeGreen
    }

    GlassCard(
        modifier = modifier
            .testTag("kpi_card_${title.lowercase().replace(" ", "_")}")
            .height(145.dp),
        shape = RoundedCornerShape(20.dp),
        isDark = isDark
    ) {
        Column(
            modifier = Modifier
                .padding(14.dp)
                .fillMaxSize(),
            verticalArrangement = Arrangement.SpaceBetween
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = title.uppercase(),
                    style = MaterialTheme.typography.labelSmall,
                    color = SlateBlueSubtle
                )

                // Compact Pill
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(50))
                        .background(statusColor.copy(alpha = 0.12f))
                        .border(1.dp, statusColor.copy(alpha = 0.25f), RoundedCornerShape(50))
                        .padding(horizontal = 7.dp, vertical = 2.dp)
                ) {
                    Text(
                        text = status.uppercase(),
                        style = MaterialTheme.typography.labelSmall,
                        color = statusColor,
                        fontSize = 9.sp
                    )
                }
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.Bottom,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column {
                    Row(verticalAlignment = Alignment.Bottom) {
                        Text(
                            text = value,
                            fontSize = 26.sp,
                            fontWeight = FontWeight.Black,
                            lineHeight = 28.sp,
                            color = MaterialTheme.colorScheme.onSurface,
                            letterSpacing = (-0.5).sp
                        )
                        Spacer(modifier = Modifier.width(3.dp))
                        Text(
                            text = unit,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold,
                            color = SlateBlueSubtle,
                            modifier = Modifier.padding(bottom = 3.dp)
                        )
                    }
                }

                // Mini Sparkline
                Box(
                    modifier = Modifier
                        .width(65.dp)
                        .height(34.dp)
                        .padding(bottom = 2.dp)
                ) {
                    if (readingsHistory.size >= 2) {
                        Canvas(modifier = Modifier.fillMaxSize()) {
                            val max = readingsHistory.maxOrNull() ?: 1f
                            val min = readingsHistory.minOrNull() ?: 0f
                            val range = if (max - min == 0f) 1f else max - min
                            val widthStep = size.width / (readingsHistory.size - 1)

                            val path = Path()
                            val fillPath = Path()

                            readingsHistory.forEachIndexed { i, yVal ->
                                val x = i * widthStep
                                val ratio = (yVal - min) / range
                                val y = size.height - (ratio * size.height)
                                if (i == 0) {
                                    path.moveTo(x, y)
                                    fillPath.moveTo(x, size.height)
                                    fillPath.lineTo(x, y)
                                } else {
                                    path.lineTo(x, y)
                                    fillPath.lineTo(x, y)
                                }
                            }
                            fillPath.lineTo(size.width, size.height)
                            fillPath.close()

                            // Fill
                            drawPath(
                                path = fillPath,
                                brush = Brush.verticalGradient(
                                    colors = listOf(statusColor.copy(alpha = 0.25f), Color.Transparent)
                                )
                            )

                            // Stroke
                            drawPath(
                                path = path,
                                color = statusColor,
                                style = Stroke(width = 2.2.dp.toPx(), cap = StrokeCap.Round)
                            )
                        }
                    } else {
                        Box(
                            modifier = Modifier
                                .fillMaxSize()
                                .border(1.dp, SlateBlueBorder.copy(alpha = 0.3f), RoundedCornerShape(4.dp)),
                            contentAlignment = Alignment.Center
                        ) {
                            Text("---", style = MaterialTheme.typography.labelSmall, color = SlateBlueLight)
                        }
                    }
                }
            }
        }
    }
}

/**
 * Interactive Historical Trend Chart with Area Gradient and Translucent Glass Canvas
 */
@Composable
fun InteractiveTrendChart(
    readings: List<SensorReading>,
    paramSelector: (SensorReading) -> Float,
    label: String,
    unit: String,
    color: Color,
    modifier: Modifier = Modifier
) {
    val isDark = isSystemInDarkTheme()

    GlassCard(
        modifier = modifier
            .testTag("trend_chart_card")
            .fillMaxWidth(),
        shape = RoundedCornerShape(24.dp),
        isDark = isDark
    ) {
        Column(modifier = Modifier.padding(20.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(
                        text = "HISTORICAL METRICS",
                        style = MaterialTheme.typography.labelSmall,
                        color = CeruleanBlueBright
                    )
                    Spacer(modifier = Modifier.height(2.dp))
                    Text(
                        text = "$label 12-Hour Trend",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.ExtraBold,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                }

                val currentVal = readings.firstOrNull()?.let(paramSelector)
                if (currentVal != null) {
                    Box(
                        modifier = Modifier
                            .clip(RoundedCornerShape(8.dp))
                            .background(color.copy(alpha = 0.12f))
                            .border(1.dp, color.copy(alpha = 0.3f), RoundedCornerShape(8.dp))
                            .padding(horizontal = 10.dp, vertical = 4.dp)
                    ) {
                        Text(
                            text = "${String.format("%.2f", currentVal)} $unit",
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Black,
                            color = color
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            if (readings.isEmpty()) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(180.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Text("No historical telemetry recorded.", color = SlateBlueSubtle)
                }
            } else {
                val dataPoints = readings.take(12).reversed()
                val values = dataPoints.map(paramSelector)
                val maxVal = values.maxOrNull() ?: 1f
                val minVal = values.minOrNull() ?: 0f
                val range = if (maxVal - minVal == 0f) 1f else (maxVal - minVal) * 1.2f
                val adjustedMin = (minVal - range * 0.1f).coerceAtLeast(0f)
                val finalRange = if (maxVal - adjustedMin == 0f) 1f else (maxVal - adjustedMin)

                Canvas(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(180.dp)
                ) {
                    val widthStep = size.width / (dataPoints.size - 1).coerceAtLeast(1)

                    // Grid Lines
                    val gridLines = 4
                    for (i in 0..gridLines) {
                        val yGrid = size.height * i / gridLines
                        drawLine(
                            color = if (isDark) Color(0x1F94A3B8) else Color(0x140047AB),
                            start = Offset(0f, yGrid),
                            end = Offset(size.width, yGrid),
                            strokeWidth = 1.dp.toPx()
                        )
                    }

                    val path = Path()
                    val fillPath = Path()

                    dataPoints.forEachIndexed { index, reading ->
                        val value = paramSelector(reading)
                        val x = index * widthStep
                        val ratio = (value - adjustedMin) / finalRange
                        val y = size.height - (ratio * size.height)

                        if (index == 0) {
                            path.moveTo(x, y)
                            fillPath.moveTo(x, size.height)
                            fillPath.lineTo(x, y)
                        } else {
                            path.lineTo(x, y)
                            fillPath.lineTo(x, y)
                        }

                        if (index == dataPoints.size - 1) {
                            fillPath.lineTo(x, size.height)
                            fillPath.close()
                        }

                        // Data circles
                        drawCircle(
                            color = color,
                            radius = 4.dp.toPx(),
                            center = Offset(x, y)
                        )
                        drawCircle(
                            color = Color.White,
                            radius = 2.dp.toPx(),
                            center = Offset(x, y)
                        )
                    }

                    // Gradient fill under curve
                    drawPath(
                        path = fillPath,
                        brush = Brush.verticalGradient(
                            colors = listOf(
                                color.copy(alpha = 0.35f),
                                Color.Transparent
                            )
                        )
                    )

                    // Curve path
                    drawPath(
                        path = path,
                        color = color,
                        style = Stroke(width = 3.dp.toPx(), cap = StrokeCap.Round)
                    )
                }

                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 10.dp),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(
                        text = "T-12 HOURS",
                        style = MaterialTheme.typography.labelSmall,
                        color = SlateBlueSubtle
                    )
                    Text(
                        text = "LIVE TELEMETRY",
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Bold,
                        color = color
                    )
                }
            }
        }
    }
}

/**
 * Donut Risk Assessment Card
 */
@Composable
fun DonutContaminationChart(
    riskPercentage: Float,
    modifier: Modifier = Modifier
) {
    val isDark = isSystemInDarkTheme()
    val color = when {
        riskPercentage >= 40f -> CriticalRed
        riskPercentage >= 20f -> WarningAmber
        else -> SafeGreen
    }

    GlassCard(
        modifier = modifier
            .testTag("donut_chart_card")
            .fillMaxWidth(),
        shape = RoundedCornerShape(22.dp),
        isDark = isDark
    ) {
        Row(
            modifier = Modifier
                .padding(18.dp)
                .fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Column(modifier = Modifier.weight(1.2f)) {
                Text(
                    text = "CONTAMINATION RISK",
                    style = MaterialTheme.typography.labelSmall,
                    color = CeruleanBlueBright
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "Infrastructure Hazard Level",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "Evaluated continuously from multi-sensor telemetry and baseline purity thresholds.",
                    style = MaterialTheme.typography.bodySmall,
                    color = SlateBlueSubtle,
                    lineHeight = 15.sp
                )
            }

            Spacer(modifier = Modifier.width(16.dp))

            Box(
                contentAlignment = Alignment.Center,
                modifier = Modifier.size(92.dp)
            ) {
                Canvas(modifier = Modifier.size(80.dp)) {
                    val strokeW = 10.dp.toPx()
                    drawArc(
                        color = if (isDark) Color(0x33334155) else Color(0x1F0047AB),
                        startAngle = 0f,
                        sweepAngle = 360f,
                        useCenter = false,
                        style = Stroke(width = strokeW)
                    )

                    drawArc(
                        color = color,
                        startAngle = -90f,
                        sweepAngle = (riskPercentage / 100f) * 360f,
                        useCenter = false,
                        style = Stroke(width = strokeW, cap = StrokeCap.Round)
                    )
                }

                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = "${riskPercentage.toInt()}%",
                        fontWeight = FontWeight.Black,
                        fontSize = 18.sp,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Text(
                        text = "RISK",
                        style = MaterialTheme.typography.labelSmall,
                        color = SlateBlueSubtle,
                        fontSize = 8.sp
                    )
                }
            }
        }
    }
}

/**
 * Smart Infrastructure ESP32 Connection Glass Header Indicator
 */
@Composable
fun ConnectionIndicator(
    status: String,
    lastUpdated: String,
    modifier: Modifier = Modifier
) {
    val isDark = isSystemInDarkTheme()
    val isOnline = status.equals("ONLINE", ignoreCase = true)
    val statusColor = if (isOnline) SafeGreen else CriticalRed

    GlassCard(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        isDark = isDark
    ) {
        Row(
            modifier = Modifier
                .padding(horizontal = 16.dp, vertical = 10.dp)
                .fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier
                        .size(9.dp)
                        .clip(CircleShape)
                        .background(statusColor)
                        .border(2.dp, statusColor.copy(alpha = 0.3f), CircleShape)
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = "ESP32 IoT Hub: $status",
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onSurface
                )
            }
            Text(
                text = "Last Sync: $lastUpdated",
                style = MaterialTheme.typography.bodySmall,
                color = SlateBlueSubtle
            )
        }
    }
}

/**
 * Alert Timeline Logs
 */
@Composable
fun AlertTimeline(
    alerts: List<Alert>,
    modifier: Modifier = Modifier
) {
    val isDark = isSystemInDarkTheme()

    GlassCard(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(24.dp),
        isDark = isDark
    ) {
        Column(modifier = Modifier.padding(20.dp)) {
            Text(
                text = "TELEMETRY ALARM LOG",
                style = MaterialTheme.typography.labelSmall,
                color = CeruleanBlueBright
            )
            Spacer(modifier = Modifier.height(2.dp))
            Text(
                text = "System Alerts & Action Logs",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.ExtraBold,
                color = MaterialTheme.colorScheme.onSurface
            )
            Spacer(modifier = Modifier.height(16.dp))

            if (alerts.isEmpty()) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        imageVector = Icons.Default.CheckCircle,
                        contentDescription = "Safe",
                        tint = SafeGreen,
                        modifier = Modifier.size(24.dp)
                    )
                    Spacer(modifier = Modifier.width(12.dp))
                    Text(
                        text = "All IoT telemetry streams within safe operational limits. Zero active alerts.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = SlateBlueSubtle
                    )
                }
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    alerts.take(5).forEach { alert ->
                        val color = if (alert.riskLevel == "Critical") CriticalRed else WarningAmber
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(12.dp))
                                .background(color.copy(alpha = 0.06f))
                                .border(1.dp, color.copy(alpha = 0.2f), RoundedCornerShape(12.dp))
                                .padding(12.dp),
                            verticalAlignment = Alignment.Top
                        ) {
                            Icon(
                                imageVector = Icons.Default.Warning,
                                contentDescription = "Alert",
                                tint = color,
                                modifier = Modifier
                                    .padding(top = 2.dp)
                                    .size(20.dp)
                            )
                            Spacer(modifier = Modifier.width(10.dp))
                            Column(modifier = Modifier.weight(1f)) {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Text(
                                        text = alert.title,
                                        style = MaterialTheme.typography.bodyMedium,
                                        fontWeight = FontWeight.Bold,
                                        color = MaterialTheme.colorScheme.onSurface
                                    )
                                    Text(
                                        text = alert.riskLevel.uppercase(),
                                        style = MaterialTheme.typography.labelSmall,
                                        color = color,
                                        fontSize = 9.sp
                                    )
                                }
                                Text(
                                    text = "Measured ${alert.parameterName}: ${alert.value} (Safe Threshold: ${alert.thresholdLimit})",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = SlateBlueSubtle
                                )
                                Spacer(modifier = Modifier.height(2.dp))
                                Text(
                                    text = "Advisory: ${alert.recommendation}",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = color,
                                    fontWeight = FontWeight.Bold
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

/**
 * Admin Top Metric Pill with Large Number & Uppercase Label
 */
@Composable
fun AdminMetricPill(
    label: String,
    value: String,
    color: Color,
    modifier: Modifier = Modifier
) {
    val isDark = isSystemInDarkTheme()
    GlassCard(
        modifier = modifier,
        shape = RoundedCornerShape(16.dp),
        isDark = isDark
    ) {
        Column(
            modifier = Modifier
                .padding(12.dp)
                .fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                text = label.uppercase(),
                style = MaterialTheme.typography.labelSmall,
                color = SlateBlueSubtle,
                fontSize = 9.sp
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = value,
                fontSize = 20.sp,
                fontWeight = FontWeight.Black,
                color = color
            )
        }
    }
}
