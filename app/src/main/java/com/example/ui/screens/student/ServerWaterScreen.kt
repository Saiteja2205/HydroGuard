package com.example.ui.screens.student

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.WaterDrop
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.ScrollableTabRow
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.BorderStroke
import androidx.compose.material3.Button
import androidx.compose.material3.CardDefaults
import android.util.Log
import com.example.BuildConfig
import com.example.data.api.AlertResponse
import com.example.data.api.ForecastResponse
import com.example.data.api.HistoricalReadingResponse
import com.example.data.api.LatestReadingResponse
import com.example.data.api.NodeHealthResponse
import com.example.data.repository.ApiFailureKind
import com.example.data.repository.ApiRepository
import com.example.data.repository.ApiRequestFailure
import com.example.data.service.WaterQualityIndexService
import com.example.ui.components.ConnectionChip
import com.example.ui.components.ApplicationIndexSummary
import com.example.ui.components.EmptyState
import com.example.ui.components.ErrorState
import com.example.ui.components.HydroCard
import com.example.ui.components.LoadingState
import com.example.ui.components.MetricCard
import com.example.ui.components.SectionHeader
import com.example.ui.components.StatusChip
import com.example.ui.components.StatusTone
import com.example.ui.theme.HydroGuardColors
import com.example.ui.viewmodel.HydroViewModel
import kotlinx.coroutines.launch
import java.text.ParsePosition
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone
import kotlin.math.roundToInt

private data class TrendField(
    val label: String,
    val unit: String,
    val value: (HistoricalReadingResponse) -> Float?
)

private val trendFields = listOf(
    TrendField("pH", "", HistoricalReadingResponse::ph),
    TrendField("TDS", "ppm", HistoricalReadingResponse::tds),
    TrendField("Turbidity", "NTU", HistoricalReadingResponse::turbidity),
    TrendField("Temperature", "°C", HistoricalReadingResponse::temperature),
    TrendField("Optical Colour", "index", HistoricalReadingResponse::opticalColourIndex)
)

private val trendPeriods = listOf("Today", "7 Days", "30 Days")

@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
fun ServerWaterScreen(
    viewModel: HydroViewModel,
    modifier: Modifier = Modifier,
    isAdmin: Boolean = false,
    onLogout: (() -> Unit)? = null,
    initialTab: Int = 0,
    onSignIn: (() -> Unit)? = onLogout
) {
    val nodeId by viewModel.selectedNodeId.collectAsState()
    val api = remember { ApiRepository() }
    var reading by remember { mutableStateOf<LatestReadingResponse?>(null) }
    var history by remember { mutableStateOf<List<HistoricalReadingResponse>>(emptyList()) }
    var alerts by remember { mutableStateOf<List<AlertResponse>>(emptyList()) }
    var forecast by remember { mutableStateOf<ForecastResponse?>(null) }
    var nodeHealth by remember { mutableStateOf<NodeHealthResponse?>(null) }
    var loading by remember { mutableStateOf(false) }
    var connected by remember { mutableStateOf<Boolean?>(null) }
    var failure by remember { mutableStateOf<ApiRequestFailure?>(null) }
    var historyFailure by remember { mutableStateOf<ApiRequestFailure?>(null) }
    var alertsFailure by remember { mutableStateOf<ApiRequestFailure?>(null) }
    var forecastFailure by remember { mutableStateOf<ApiRequestFailure?>(null) }
    var noReading by remember { mutableStateOf(false) }
    var selectedTab by remember { mutableIntStateOf(initialTab.coerceIn(0, 3)) }
    var selectedTrendField by remember { mutableIntStateOf(0) }
    var selectedPeriod by remember { mutableIntStateOf(0) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(initialTab) { selectedTab = initialTab.coerceIn(0, 3) }

    suspend fun load() {
        loading = true
        failure = null
        noReading = false
        reading = null
        history = emptyList()
        alerts = emptyList()
        forecast = null
        nodeHealth = null
        historyFailure = null
        alertsFailure = null
        forecastFailure = null

        if (isAdmin) api.getNodeHealth(nodeId).onSuccess { nodeHealth = it }
        api.getLatestReading(nodeId).onSuccess {
            reading = it
            connected = true
        }.onFailure { exception ->
            val apiFailure = exception as? ApiRequestFailure
            if (apiFailure?.kind == ApiFailureKind.NO_READING) {
                noReading = true
                connected = true
            } else {
                failure = apiFailure ?: ApiRequestFailure(ApiFailureKind.API_ERROR, "/api/v1/nodes/$nodeId/readings/latest", cause = exception)
                connected = apiFailure?.kind != ApiFailureKind.SERVER_UNREACHABLE
            }
        }
        val historyResult = api.getHistoricalReadings(nodeId, 100)
        val returnedHistory = historyResult.getOrNull()?.readings.orEmpty()
        history = returnedHistory
        historyResult.onSuccess { historyFailure = null }
            .onFailure { historyFailure = it as? ApiRequestFailure }
        api.getAlerts(nodeId).onSuccess { alerts = it.alerts }
            .onFailure { alertsFailure = it as? ApiRequestFailure }
        if (historyResult.isFailure) {
            forecastFailure = historyResult.exceptionOrNull() as? ApiRequestFailure
                ?: ApiRequestFailure(ApiFailureKind.API_ERROR, "/api/v1/nodes/$nodeId/readings/history", cause = historyResult.exceptionOrNull())
        } else {
            val readiness = assessForecastHistory(returnedHistory)
            if (BuildConfig.DEBUG) {
                Log.w(
                    "HydroGuardForecast",
                    "node=$nodeId total=${readiness.totalReadings} recent30=${readiness.recent30Readings} " +
                        "complete=${readiness.forecastRows.size} source=${readiness.forecastSource} " +
                        "missingRecent30=${readiness.missingRecent30} invalidTimestamp=${readiness.invalidTimestamps} " +
                        "future=${readiness.futureTimestamps} duplicate=${readiness.duplicateTimestamps} " +
                        "required=${ApiRepository.FORECAST_MIN_HISTORY}"
                )
            }
            if (readiness.forecastRows.size >= ApiRepository.FORECAST_MIN_HISTORY) {
                api.generateForecast(nodeId, readiness.forecastRows).onSuccess { forecast = it }
                    .onFailure { forecastFailure = it as? ApiRequestFailure }
            } else {
                forecastFailure = ApiRequestFailure(
                    ApiFailureKind.INSUFFICIENT_DATA,
                    "/api/v1/forecast",
                    userDetail = readiness.detail
                )
            }
        }
        loading = false
    }
    LaunchedEffect(nodeId) { load() }

    val index = reading?.temperature?.let { temperature ->
        reading?.let { current -> WaterQualityIndexService.calculate(current.ph, current.tds, current.turbidity, temperature) }
    }
    val activeCount = alerts.count { it.status.equals("ACTIVE", true) }
    val acknowledgedCount = alerts.count { it.status.equals("ACKNOWLEDGED", true) }
    val resolvedCount = alerts.count { it.status.equals("RESOLVED", true) }

    Scaffold(
        modifier = modifier,
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            Column {
                TopAppBar(
                    title = {
                        Column(verticalArrangement = Arrangement.spacedBy(1.dp)) {
                            Text(if (isAdmin) "Admin Dashboard" else "HydroGuard", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, maxLines = 1)
                            Text(if (isAdmin) "Water Monitoring" else "Water Intelligence", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    },
                    actions = {
                        IconButton(onClick = { scope.launch { load() } }, enabled = !loading) {
                            Icon(Icons.Default.Refresh, contentDescription = "Refresh water data")
                        }
                        if (onLogout != null) {
                            OutlinedButton(onClick = onLogout, modifier = Modifier.padding(end = 8.dp).height(40.dp), shape = RoundedCornerShape(12.dp)) {
                                Text("Sign out", maxLines = 1, softWrap = false, style = MaterialTheme.typography.labelSmall)
                            }
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background)
                )
                if (isAdmin) {
                    Row(
                        Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(16.dp)
                    ) {
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text("SERVER", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            ConnectionChip(connected)
                        }
                        Column(Modifier.weight(1.35f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text("MONITORING NODE", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                StatusChip(
                                    nodeHealth?.status?.replace('_', ' ')?.let { "Node $it" } ?: "Node status unknown",
                                    tone = nodeHealth?.let { if (it.status.equals("online", true)) StatusTone.HEALTHY else StatusTone.DISCONNECTED } ?: StatusTone.NEUTRAL
                                )
                                Text("${nodeHealth?.location ?: "Selected node"} · $nodeId", maxLines = 1, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                }
                ScrollableTabRow(
                    selectedTabIndex = selectedTab,
                    containerColor = MaterialTheme.colorScheme.background,
                    edgePadding = 16.dp
                ) {
                    listOf("Current", "Trends", "Forecast", "Alerts").forEachIndexed { index, label ->
                        Tab(
                            selected = selectedTab == index,
                            onClick = { selectedTab = index },
                            text = { Text(label, style = MaterialTheme.typography.labelLarge) }
                        )
                    }
                }
            }
        }
    ) { padding ->
        LazyColumn(
            Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            if (loading) item { LoadingState(if (isAdmin) "Refreshing server data" else "Refreshing water data") }
            failure?.let { requestFailure ->
                item {
                    ErrorState(
                        title = failureTitle(requestFailure, isAdmin),
                        detail = failureDetail(requestFailure, isAdmin),
                        actionLabel = if (requestFailure.kind == ApiFailureKind.AUTHENTICATION && requestFailure.statusCode != 403 && onSignIn != null) "Sign in" else "Retry",
                        onAction = {
                            if (requestFailure.kind == ApiFailureKind.AUTHENTICATION && requestFailure.statusCode != 403 && onSignIn != null) onSignIn()
                            else scope.launch { load() }
                        }
                    )
                }
            }

            when (selectedTab) {
                0 -> {
                    if (isAdmin) {
                        item { SectionHeader("Server status", subtitle = "Backend and selected monitoring node") }
                        item {
                            HydroCard {
                                Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                            Text("SERVER", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                            ConnectionChip(connected)
                                        }
                                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                            Text("MONITORING NODE", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                            StatusChip(nodeHealth?.status?.replace('_', ' ')?.let { "Node $it" } ?: "Node status unknown", tone = nodeHealth?.let { if (it.status.equals("online", true)) StatusTone.HEALTHY else StatusTone.DISCONNECTED } ?: StatusTone.NEUTRAL)
                                        }
                                    }
                                    Text(nodeHealth?.name ?: nodeId, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                                    Text("${nodeHealth?.location ?: "Location not reported"} · Last heartbeat ${nodeHealth?.last_seen ?: "not reported"}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    Text("Last reading ${reading?.timestamp ?: "not reported"} · ${reading?.let { provenanceLabel(it.source) } ?: "No current reading"}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                            }
                        }
                    } else {
                        item { SectionHeader("Current Water Quality", subtitle = "Latest monitored readings") }
                    }
                    if (noReading && failure == null) item {
                        EmptyState(
                            if (isAdmin) "No sensor data" else "Water data temporarily unavailable",
                            if (isAdmin) "Waiting for the monitoring node to send readings." else "We couldn't load this information right now.",
                            icon = Icons.Default.WaterDrop,
                            actionLabel = "Refresh",
                            onAction = { scope.launch { load() } }
                        )
                    }
                    reading?.let { current ->
                        item {
                            HydroCard(containerColor = MaterialTheme.colorScheme.primaryContainer, shape = RoundedCornerShape(20.dp)) {
                                Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
                                        Text("WATER QUALITY", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
                                    }
                                    ApplicationIndexSummary(index?.index, index?.category?.displayName)
                                    if (isAdmin) Text("${provenanceLabel(current.source)} · ${current.timestamp}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                            }
                        }
                        item {
                            SectionHeader(
                                if (isAdmin) "Sensor grid" else "Current readings",
                                subtitle = if (isAdmin) "Five-parameter water-quality contract" else null
                            )
                        }
                        val metrics = currentMetrics(current)
                        metrics.take(4).chunked(2).forEachIndexed { rowIndex, row ->
                            item(key = "current-metrics-$rowIndex") {
                                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                    row.forEach { metric ->
                                        MetricCard(
                                            label = metric.label,
                                            value = metric.value,
                                            unit = metric.unit,
                                            note = metric.note,
                                            badge = metric.badge,
                                            tone = metric.tone,
                                            modifier = Modifier.weight(1f)
                                        )
                                    }
                                    if (row.size == 1) Spacer(Modifier.weight(1f))
                                }
                            }
                        }
                        metrics.lastOrNull()?.let { metric ->
                            item(key = "current-optical-colour") {
                                MetricCard(
                                    label = metric.label,
                                    value = metric.value,
                                    unit = metric.unit,
                                    note = metric.note,
                                    badge = metric.badge,
                                    tone = metric.tone,
                                    modifier = Modifier.fillMaxWidth()
                                )
                            }
                        }
                        if (!isAdmin) item {
                            Text("Last updated · ${current.timestamp}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    if (isAdmin) {
                        item { SectionHeader("Alert summary") }
                        if (alertsFailure == null) item {
                            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                item { StatusChip("Active $activeCount", tone = if (activeCount > 0) StatusTone.ATTENTION else StatusTone.HEALTHY) }
                                item { StatusChip("Acknowledged $acknowledgedCount", tone = StatusTone.NEUTRAL) }
                                item { StatusChip("Resolved $resolvedCount", tone = StatusTone.HEALTHY) }
                            }
                        }
                        alertsFailure?.let { requestFailure ->
                            item { FailureSummary(requestFailure, { scope.launch { load() } }, onSignIn, isAdmin) }
                        }
                        item { AdminForecastSummary(forecast, forecastFailure, onSignIn) }
                    }
                    if (reading == null && !noReading && failure == null && !loading) {
                        item {
                            EmptyState(
                                if (isAdmin) "Current reading unavailable" else "Water data temporarily unavailable",
                                if (isAdmin) "Refresh to request the latest reading." else "We couldn't load this information right now.",
                                actionLabel = "Retry",
                                onAction = { scope.launch { load() } }
                            )
                        }
                    }
                }
                1 -> {
                    item { SectionHeader(if (isAdmin) "Historical trends" else "Trends", subtitle = if (isAdmin) "Actual readings returned by the backend" else "Recent water readings") }
                    historyFailure?.let { requestFailure -> item { FailureSummary(requestFailure, { scope.launch { load() } }, onSignIn, isAdmin) } }
                    item {
                        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            items(trendFields) { field ->
                                FilterChip(
                                    selected = trendFields[selectedTrendField] == field,
                                    onClick = { selectedTrendField = trendFields.indexOf(field) },
                                    label = { Text(field.label, maxLines = 1, softWrap = false) }
                                )
                            }
                        }
                    }
                    item {
                        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            items(trendPeriods) { period ->
                                FilterChip(
                                    selected = trendPeriods[selectedPeriod] == period,
                                    onClick = { selectedPeriod = trendPeriods.indexOf(period) },
                                    label = { Text(period) }
                                )
                            }
                        }
                    }
                    val field = trendFields[selectedTrendField]
                    val maxAgeMillis = when (trendPeriods[selectedPeriod]) {
                        "Today" -> 24L * 60 * 60 * 1000
                        "7 Days" -> 7L * 24 * 60 * 60 * 1000
                        else -> 30L * 24 * 60 * 60 * 1000
                    }
                    val points = history
                        .filter { isWithinPeriod(it.timestamp, maxAgeMillis) }
                        .sortedWith(compareBy<HistoricalReadingResponse>({ parseTimestampMillis(it.timestamp) ?: Long.MIN_VALUE }, { it.id }))
                        .mapNotNull { row -> field.value(row)?.let { row.timestamp to it } }
                    if (historyFailure == null && points.size < 2) item {
                        EmptyState(
                            "Not enough ${field.label} readings",
                            "At least two actual observations in ${trendPeriods[selectedPeriod].lowercase()} are needed to draw a trend.",
                            icon = Icons.Default.WaterDrop
                        )
                    } else if (historyFailure == null) {
                        item {
                            HydroCard {
                                Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
                                        Column {
                                            Text("${field.label} trend", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                                            Text(
                                                if (isAdmin) "${points.size} backend observations · ${trendPeriods[selectedPeriod]}" else "${points.size} readings · ${trendPeriods[selectedPeriod]}",
                                                style = MaterialTheme.typography.bodySmall,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant
                                            )
                                        }
                                        if (field.label == "Optical Colour") StatusChip("EXPERIMENTAL", tone = StatusTone.AI)
                                    }
                                    TrendPlot(points.map { it.second })
                                    val min = points.minOf { it.second }
                                    val max = points.maxOf { it.second }
                                    Text("Observed range ${formatValue(min)} – ${formatValue(max)} ${field.unit}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    Text("${points.first().first.take(16)}  →  ${points.last().first.take(16)}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                            }
                        }
                    item { SectionHeader(if (isAdmin) "Recent observations" else "Recent readings") }
                        items(points.takeLast(8).asReversed(), key = { it.first }) { (timestamp, value) ->
                            HydroCard {
                                Row(Modifier.fillMaxWidth().padding(14.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                                    Text(timestamp.take(16), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    Text("${formatValue(value)} ${field.unit}".trim(), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                                }
                            }
                        }
                    }
                }
                2 -> {
                    item {
                        SectionHeader(
                            if (isAdmin) "Five-parameter forecast" else "Next-Day Forecast",
                            subtitle = if (isAdmin) "LSTM · PatchTST · TimeMixer · Adaptive Ensemble" else "Estimated changes based on recent readings"
                        )
                    }
                    if (forecastFailure != null && forecast == null) {
                        item {
                            if (forecastFailure?.kind == ApiFailureKind.INSUFFICIENT_DATA) {
                                EmptyState(
                                    "Forecast not available yet",
                                    if (isAdmin) failureDetail(forecastFailure!!, true) else "Not enough complete historical readings are available to generate the next-day forecast.",
                                    icon = Icons.Default.WaterDrop
                                )
                            } else {
                                FailureSummary(forecastFailure!!, { scope.launch { load() } }, onSignIn, isAdmin)
                            }
                        }
                    }
                    forecast?.let { result ->
                        item {
                            HydroCard(containerColor = HydroGuardColors.experimentalTint, shape = RoundedCornerShape(20.dp)) {
                                Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                                        Column(Modifier.weight(1f)) {
                                             Text(if (isAdmin) "ADAPTIVE ENSEMBLE" else "FORECAST ESTIMATE", style = MaterialTheme.typography.labelMedium, color = HydroGuardColors.experimental)
                                            Text("${result.forecastHorizonHours}-hour forecast", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                                        }
                                     if (isAdmin) StatusChip(forecastSourceLabel(result.dataSource), tone = if (isDevelopmentSource(result.dataSource)) StatusTone.AI else StatusTone.NEUTRAL)
                                    }
                                     Text(
                                         if (isAdmin) "Forecast ${result.forecastDate} · Inputs ${result.inputStart.take(10)} to ${result.inputEnd.take(10)}" else "Forecast for ${result.forecastDate}",
                                         style = MaterialTheme.typography.bodySmall
                                     )
                                     if (isAdmin) Text("Weight status: ${result.weightStatus.replace('_', ' ')} · Strategy: ${result.weightStrategy.replace('_', ' ')}", style = MaterialTheme.typography.bodySmall)
                                }
                            }
                        }
                        item { SectionHeader(if (isAdmin) "Ensemble prediction" else "Forecast values", subtitle = if (isAdmin) "Values returned by the forecast API" else null) }
                        forecastMetrics(result).take(4).chunked(2).forEachIndexed { rowIndex, row ->
                            item(key = "forecast-metrics-$rowIndex") {
                                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                    row.forEach { metric ->
                                        MetricCard(metric.label, metric.value, unit = metric.unit, tone = metric.tone, badge = metric.badge, modifier = Modifier.weight(1f))
                                    }
                                    if (row.size == 1) Spacer(Modifier.weight(1f))
                                }
                            }
                        }
                        forecastMetrics(result).lastOrNull()?.let { metric ->
                            item(key = "forecast-optical-colour") {
                                MetricCard(metric.label, metric.value, unit = metric.unit, note = metric.note, tone = metric.tone, badge = metric.badge, modifier = Modifier.fillMaxWidth())
                            }
                        }
                        if (isAdmin) {
                            item { SectionHeader("Adaptive model weights", subtitle = "Actual weights returned with this forecast") }
                            result.weights.orEmpty().toSortedMap().forEach { (parameter, weights) ->
                                item(key = "weights-$parameter") {
                                    HydroCard {
                                        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                            Text(parameterLabel(parameter), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                                            WeightRow("LSTM", weights.LSTM)
                                            WeightRow("PatchTST", weights.PatchTST)
                                            WeightRow("TimeMixer", weights.TimeMixer)
                                        }
                                    }
                                }
                            }
                            item { SectionHeader("Model predictions") }
                            val modelOrder = listOf("LSTM", "PatchTST", "TimeMixer")
                            modelOrder.forEach { model ->
                                result.modelPredictions?.get(model)?.let { prediction ->
                                    item(key = "model-$model") {
                                        HydroCard {
                                            Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                                Text(model, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                                                result.modelVersions[model]?.let { Text("Model version $it", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                                                Text("pH ${formatValue(prediction.pH)} · TDS ${formatValue(prediction.TDS)} ppm", style = MaterialTheme.typography.bodyMedium)
                                                Text("Turbidity ${formatValue(prediction.turbidity)} NTU · Temperature ${formatValue(prediction.temperature)} °C", style = MaterialTheme.typography.bodyMedium)
                                                Text("Optical Colour Index ${formatValue(prediction.opticalColourIndex)} · Experimental", style = MaterialTheme.typography.bodySmall, color = HydroGuardColors.experimental)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        item { Text("Optical Colour is for information only and is not a safety measurement.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                    }
                }
                else -> {
                    item { SectionHeader("Alerts", subtitle = if (isAdmin) "Alert records returned by the HydroGuard backend" else "Water alerts") }
                    alertsFailure?.let { requestFailure -> item { FailureSummary(requestFailure, { scope.launch { load() } }, onSignIn, isAdmin) } }
                    if (isAdmin && alertsFailure == null) item {
                        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            item { StatusChip("Active $activeCount", tone = if (activeCount > 0) StatusTone.ATTENTION else StatusTone.HEALTHY) }
                            item { StatusChip("Acknowledged $acknowledgedCount", tone = StatusTone.NEUTRAL) }
                            item { StatusChip("Resolved $resolvedCount", tone = StatusTone.HEALTHY) }
                        }
                    }
                    val visibleAlerts = if (isAdmin) alerts else alerts.filter { it.status.equals("ACTIVE", true) }
                    if (alertsFailure == null && visibleAlerts.isEmpty() && !loading) item {
                        EmptyState(
                            if (isAdmin) "No alert records" else "No active water alerts",
                            if (isAdmin) "No alerts have been recorded." else "Everything looks good right now.",
                            icon = Icons.Default.WaterDrop
                        )
                    }
                    items(visibleAlerts.sortedByDescending { it.timestamp }, key = { it.id }) { alert ->
                        AlertCard(alert, isAdmin)
                    }
                }
            }
        }
    }
}

private data class DisplayMetric(
    val label: String,
    val value: String,
    val unit: String,
    val note: String? = null,
    val badge: String? = null,
    val tone: StatusTone = StatusTone.NEUTRAL
)

private fun currentMetrics(reading: LatestReadingResponse): List<DisplayMetric> = listOf(
    DisplayMetric("pH", formatValue(reading.ph), ""),
    DisplayMetric("TDS", formatValue(reading.tds), "ppm"),
    DisplayMetric("Turbidity", formatValue(reading.turbidity), "NTU"),
    DisplayMetric("Temperature", reading.temperature?.let(::formatValue) ?: "—", "°C", if (reading.temperature == null) "Not reported" else null),
    DisplayMetric(
        "Optical Colour",
        reading.opticalColourIndex?.let(::formatValue) ?: "—",
        "index",
        if (reading.opticalColourIndex == null) "Not reported" else "Experimental measure",
        "EXPERIMENTAL",
        StatusTone.AI
    )
)

private fun forecastMetrics(forecast: ForecastResponse): List<DisplayMetric> = listOf(
    DisplayMetric("pH", formatValue(forecast.prediction.pH), ""),
    DisplayMetric("TDS", formatValue(forecast.prediction.TDS), "ppm"),
    DisplayMetric("Turbidity", formatValue(forecast.prediction.turbidity), "NTU"),
    DisplayMetric("Temperature", formatValue(forecast.prediction.temperature), "°C"),
    DisplayMetric("Optical Colour", formatValue(forecast.prediction.opticalColourIndex), "index", "Experimental", "EXPERIMENTAL", StatusTone.AI)
)

private data class ForecastHistoryReadiness(
    val totalReadings: Int,
    val recent30Readings: Int,
    val forecastRows: List<HistoricalReadingResponse>,
    val forecastSource: String,
    val missingRecent30: Map<String, Int>,
    val invalidTimestamps: Int,
    val futureTimestamps: Int,
    val duplicateTimestamps: Int,
    val detail: String
)

private fun assessForecastHistory(history: List<HistoricalReadingResponse>): ForecastHistoryReadiness {
    val now = System.currentTimeMillis()
    val thirtyDaysAgo = now - 30L * 24 * 60 * 60 * 1000
    val parsed = history.mapNotNull { row ->
        parseTimestampMillis(row.timestamp)?.let { row to it }
    }
    val invalidTimestampCount = history.size - parsed.size
    val futureRows = parsed.filter { it.second > now }
    val usableTimeRows = parsed.filter { it.second <= now }
    val recent30 = usableTimeRows.filter { it.second >= thirtyDaysAgo }
    val duplicateGroups = usableTimeRows.groupBy { it.second }.filterValues { it.size > 1 }
    val duplicateCount = duplicateGroups.values.sumOf { it.size }
    val uniqueTimestampRows = usableTimeRows.filter { row ->
        usableTimeRows.count { it.second == row.second } == 1
    }
    val fields = listOf(
        "pH" to { row: HistoricalReadingResponse -> row.ph.isFinite() },
        "TDS" to { row: HistoricalReadingResponse -> row.tds.isFinite() },
        "Turbidity" to { row: HistoricalReadingResponse -> row.turbidity.isFinite() },
        "Temperature" to { row: HistoricalReadingResponse -> row.temperature?.isFinite() == true },
        "Optical Colour Index" to { row: HistoricalReadingResponse -> row.opticalColourIndex?.isFinite() == true }
    )
    val missingRecent30 = fields.mapNotNull { (label, hasValue) ->
        val missing = recent30.count { !hasValue(it.first) }
        label.takeIf { missing > 0 }?.let { it to missing }
    }.toMap()
    val complete = uniqueTimestampRows.filter { (row, _) -> fields.all { (_, hasValue) -> hasValue(row) } }
    val completeBySource = complete.groupBy { normalizedForecastSource(it.first.source) }
    val selected = completeBySource.maxByOrNull { it.value.size }
    val forecastSource = selected?.key ?: "unknown source"
    val forecastRows = selected?.value
        .orEmpty()
        .sortedWith(compareBy({ parseTimestampMillis(it.first.timestamp) ?: Long.MIN_VALUE }, { it.first.id }))
        .map { it.first }
    val missingSummary = missingRecent30.entries.joinToString { "${it.key} missing in ${it.value} of ${recent30.size}" }
        .ifBlank { "No missing parameters in the last 30 days." }
    val sourceSummary = completeBySource.entries.joinToString { "${it.key}: ${it.value.size}" }
        .ifBlank { "no complete observations" }
    val detail = buildString {
        append("Forecast needs at least ${ApiRepository.FORECAST_MIN_HISTORY} complete five-parameter observations from one data source. ")
        append("Found ${forecastRows.size} complete readings among ${history.size} observations ($sourceSummary). ")
        append("The last 30 days contain ${recent30.size} observations; $missingSummary. ")
        if (invalidTimestampCount > 0) append("$invalidTimestampCount timestamps could not be parsed. ")
        if (futureRows.isNotEmpty()) append("${futureRows.size} readings are future-dated. ")
        if (duplicateCount > 0) append("$duplicateCount readings have duplicate timestamps. ")
        append("No missing values were filled in.")
    }
    return ForecastHistoryReadiness(
        totalReadings = history.size,
        recent30Readings = recent30.size,
        forecastRows = forecastRows,
        forecastSource = forecastSource,
        missingRecent30 = missingRecent30,
        invalidTimestamps = invalidTimestampCount,
        futureTimestamps = futureRows.size,
        duplicateTimestamps = duplicateCount,
        detail = detail
    )
}

private fun normalizedForecastSource(source: String): String = when (source.trim().uppercase()) {
    "ESP32" -> "REAL_SENSOR"
    "MANUAL" -> "HISTORICAL_DATA"
    "HISTORICAL_DEMO", "HISTORICAL_OR_SIMULATED" -> "DEMO"
    else -> source.trim().uppercase()
}

@Composable
private fun WeightRow(model: String, weight: Float) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(model, style = MaterialTheme.typography.bodyMedium)
            Text("${(weight * 100).roundToInt()}%", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold)
        }
        androidx.compose.material3.LinearProgressIndicator(
            progress = { weight.coerceIn(0f, 1f) },
            modifier = Modifier.fillMaxWidth().height(6.dp),
            color = MaterialTheme.colorScheme.primary,
            trackColor = MaterialTheme.colorScheme.primaryContainer
        )
    }
}

@Composable
private fun AdminForecastSummary(forecast: ForecastResponse?, failure: ApiRequestFailure?, onSignIn: (() -> Unit)?) {
    SectionHeader("Forecast summary")
    if (forecast == null) {
        HydroCard {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("Forecast unavailable", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
        Text(failure?.let { failureDetail(it, isAdmin = true) } ?: "No forecast response is available.", style = MaterialTheme.typography.bodySmall)
                if (failure?.kind == ApiFailureKind.AUTHENTICATION && failure.statusCode != 403 && onSignIn != null) {
                    androidx.compose.material3.TextButton(onClick = onSignIn) { Text("Sign in") }
                }
            }
        }
    } else {
        HydroCard {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                StatusChip(forecastSourceLabel(forecast.dataSource), tone = if (isDevelopmentSource(forecast.dataSource)) StatusTone.AI else StatusTone.NEUTRAL)
                Text("${forecast.forecastHorizonHours}-hour adaptive forecast · ${forecast.forecastDate}", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                Text("pH ${formatValue(forecast.prediction.pH)} · TDS ${formatValue(forecast.prediction.TDS)} · Turbidity ${formatValue(forecast.prediction.turbidity)} · Temp ${formatValue(forecast.prediction.temperature)} °C", style = MaterialTheme.typography.bodySmall)
                Text("Optical Colour Index ${formatValue(forecast.prediction.opticalColourIndex)} · Experimental", style = MaterialTheme.typography.bodySmall, color = HydroGuardColors.experimental)
                Text("Weight status: ${forecast.weightStatus.replace('_', ' ')}", style = MaterialTheme.typography.bodySmall)
            }
        }
        SectionHeader("Model information")
        HydroCard {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                forecast.modelVersions.toSortedMap().forEach { (name, version) ->
                    Text("$name · $version", style = MaterialTheme.typography.bodySmall)
                }
                Text("Weight strategy: ${forecast.weightStrategy.replace('_', ' ')}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun AlertCard(alert: AlertResponse, isAdmin: Boolean) {
    val severityTone = when (alert.severity.uppercase()) {
        "CRITICAL" -> StatusTone.CRITICAL
        "ATTENTION", "WARNING" -> StatusTone.ATTENTION
        else -> StatusTone.NEUTRAL
    }
    val statusTone = when (alert.status.uppercase()) {
        "RESOLVED" -> StatusTone.HEALTHY
        "ACKNOWLEDGED" -> StatusTone.NEUTRAL
        else -> severityTone
    }
    HydroCard {
        Row(Modifier.fillMaxWidth().padding(start = 4.dp)) {
            androidx.compose.foundation.layout.Box(Modifier.size(4.dp, 112.dp).background(severityTone.colorValue()))
            Column(Modifier.weight(1f).padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    StatusChip(alert.severity.uppercase(), tone = severityTone)
                    if (isAdmin) StatusChip(alert.status.replace('_', ' '), tone = statusTone)
                }
                Text(if (isAdmin) "${parameterLabel(alert.parameter)} threshold alert" else parameterLabel(alert.parameter), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                Text(alert.message, style = MaterialTheme.typography.bodyMedium)
                if (isAdmin) Text("Observed ${formatValue(alert.value)} · threshold ${formatValue(alert.threshold)}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text(if (isAdmin) "${alert.timestamp} · Node ${alert.nodeId}" else alert.timestamp, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun FailureSummary(failure: ApiRequestFailure, onRetry: () -> Unit, onSignIn: (() -> Unit)?, isAdmin: Boolean) {
    val canSignIn = failure.kind == ApiFailureKind.AUTHENTICATION && failure.statusCode != 403 && onSignIn != null
    ErrorState(
        failureTitle(failure, isAdmin),
        failureDetail(failure, isAdmin),
        actionLabel = if (canSignIn) "Sign in" else "Retry",
        onAction = if (canSignIn) onSignIn!! else onRetry
    )
}

private fun failureTitle(failure: ApiRequestFailure, isAdmin: Boolean): String = if (!isAdmin) {
    if (failure.kind == ApiFailureKind.AUTHENTICATION && failure.statusCode == 401) "Sign in required"
    else "Water data temporarily unavailable"
} else when (failure.kind) {
    ApiFailureKind.SERVER_UNREACHABLE -> "Server unavailable"
    ApiFailureKind.NO_READING -> "No reading yet"
    ApiFailureKind.AUTHENTICATION -> if (failure.statusCode == 403) "Access denied" else "Sign in required"
    ApiFailureKind.API_ERROR -> "Unable to retrieve water data"
    ApiFailureKind.MALFORMED_RESPONSE -> "Unexpected server response"
    ApiFailureKind.INSUFFICIENT_DATA -> "Not enough historical data"
}

private fun failureDetail(failure: ApiRequestFailure, isAdmin: Boolean = false): String {
    if (!isAdmin) {
        return when {
            failure.kind == ApiFailureKind.AUTHENTICATION && failure.statusCode == 401 -> "Please sign in again to continue."
            failure.kind == ApiFailureKind.INSUFFICIENT_DATA -> "Not enough complete historical readings are available to generate the next-day forecast."
            else -> "We couldn't load this information right now."
        }
    }
    return when (failure.kind) {
        ApiFailureKind.SERVER_UNREACHABLE -> "Check the connection and try again."
        ApiFailureKind.NO_READING -> "Waiting for the monitoring node to send readings."
        ApiFailureKind.AUTHENTICATION -> if (failure.statusCode == 403) "This account does not have access to this service." else "Your session is no longer valid. Please sign in again."
        ApiFailureKind.API_ERROR -> "The server could not complete this request. Try again shortly."
        ApiFailureKind.MALFORMED_RESPONSE -> "The server sent data that HydroGuard could not display."
        ApiFailureKind.INSUFFICIENT_DATA -> failure.userDetail ?: "Forecasting needs at least 30 complete, timestamped observations from the same source."
    }
}

private fun provenanceLabel(source: String): String = when (source.uppercase()) {
    "REAL_SENSOR" -> "REAL SENSOR DATA"
    "DEMO", "HISTORICAL_DEMO" -> "HISTORICAL DEMO DATA"
    "SIMULATED", "DEVELOPMENT" -> "DEVELOPMENT / SIMULATED DATA"
    else -> source.uppercase().replace('_', ' ')
}

private fun isDevelopmentSource(source: String): Boolean =
    source.uppercase().let { it.contains("SIMULATED") || it.contains("DEVELOPMENT") || it.contains("DEMO") }

private fun forecastSourceLabel(source: String): String =
    if (isDevelopmentSource(source)) "DEVELOPMENT / SIMULATED" else source.uppercase().replace('_', ' ')

private fun parameterLabel(parameter: String): String = when (parameter.lowercase()) {
    "ph" -> "pH"
    "tds" -> "TDS"
    "optical_colour_index" -> "Optical Colour"
    else -> parameter.replaceFirstChar { it.uppercase() }
}

private fun formatValue(value: Float): String = String.format(Locale.US, "%.2f", value)

private val isoTimestampPattern =
    Regex("""^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:?\d{2})?$""")

private fun parseTimestampMillis(timestamp: String): Long? {
    val parts = isoTimestampPattern.matchEntire(timestamp)?.groupValues ?: return null
    val fraction = parts[2].padEnd(3, '0').take(3)
    val zone = when (val offset = parts[3]) {
        "", "Z" -> "+0000"
        else -> offset.replace(":", "")
    }
    val normalized = "${parts[1]}.$fraction$zone"
    val parser = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSZ", Locale.US).apply {
        isLenient = false
        timeZone = TimeZone.getTimeZone("UTC")
    }
    val position = ParsePosition(0)
    val parsed = parser.parse(normalized, position) ?: return null
    return parsed.time.takeIf { position.index == normalized.length }
}

private fun isWithinPeriod(timestamp: String, periodMillis: Long): Boolean {
    val readingTime = parseTimestampMillis(timestamp) ?: return false
    val now = System.currentTimeMillis()
    return readingTime >= now - periodMillis && readingTime <= now
}

@Composable
private fun StatusTone.colorValue(): androidx.compose.ui.graphics.Color = when (this) {
    StatusTone.HEALTHY -> HydroGuardColors.healthy
    StatusTone.ATTENTION -> HydroGuardColors.warning
    StatusTone.CRITICAL -> HydroGuardColors.critical
    StatusTone.AI -> HydroGuardColors.experimental
    StatusTone.NEUTRAL -> MaterialTheme.colorScheme.primary
    StatusTone.DISCONNECTED -> HydroGuardColors.disconnected
}

@Composable
private fun TrendPlot(values: List<Float>) {
    val lineColor = MaterialTheme.colorScheme.primary
    val gridColor = MaterialTheme.colorScheme.outlineVariant
    Canvas(Modifier.fillMaxWidth().height(176.dp)) {
        if (values.size < 2) return@Canvas
        val low = values.minOrNull() ?: return@Canvas
        val high = values.maxOrNull() ?: return@Canvas
        val range = (high - low).takeIf { it > 0f } ?: 1f
        repeat(3) { index ->
            val y = size.height * index / 2f
            drawLine(gridColor, Offset(0f, y), Offset(size.width, y), strokeWidth = 1.dp.toPx())
        }
        val points = values.mapIndexed { index, value ->
            Offset(size.width * index / values.lastIndex, size.height - ((value - low) / range) * size.height)
        }
        val path = Path().apply {
            moveTo(points.first().x, points.first().y)
            points.drop(1).forEach { lineTo(it.x, it.y) }
        }
        drawPath(path, color = lineColor, style = Stroke(width = 3.dp.toPx(), cap = StrokeCap.Round))
        points.forEach { drawCircle(lineColor, radius = 4.dp.toPx(), center = it) }
    }
}
