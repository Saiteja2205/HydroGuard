package com.example.ui.screens.student

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.data.api.*
import com.example.data.service.WaterQualityIndexService
import com.example.ui.components.EmptyState
import com.example.ui.components.SectionHeader
import com.example.ui.viewmodel.HydroViewModel
import kotlinx.coroutines.launch
import java.util.Locale

@Composable
fun ServerWaterScreen(viewModel: HydroViewModel, modifier: Modifier = Modifier, isAdmin: Boolean = false, onLogout: (() -> Unit)? = null) {
    val nodeId by viewModel.selectedNodeId.collectAsState()
    var reading by remember { mutableStateOf<LatestReadingResponse?>(null) }
    var history by remember { mutableStateOf<List<HistoricalReadingResponse>>(emptyList()) }
    var alerts by remember { mutableStateOf<List<AlertResponse>>(emptyList()) }
    var forecast by remember { mutableStateOf<ForecastResponse?>(null) }
    var nodeHealth by remember { mutableStateOf<NodeHealthResponse?>(null) }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var selected by remember { mutableIntStateOf(0) }
    val scope = rememberCoroutineScope()

    suspend fun load() {
        loading = true; error = null
        try {
            val api = RetrofitClient.apiService
            nodeHealth = if (isAdmin) api.getNodeHealth(nodeId).takeIf { it.isSuccessful }?.body() else null
            val live = api.getLatestReading(nodeId)
            if (!live.isSuccessful) error("Unable to connect to HydroGuard server")
            reading = live.body()
            val hist = api.getHistoricalReadings(nodeId, 100)
            if (hist.isSuccessful) history = hist.body()?.readings.orEmpty()
            val alertResponse = api.getAlerts(nodeId)
            if (alertResponse.isSuccessful) alerts = alertResponse.body()?.alerts.orEmpty()
            val completeForecastHistory = history.filter { it.temperature != null && it.opticalColourIndex != null }
            if (completeForecastHistory.size >= 30) {
                val req = ForecastRequest(nodeId, completeForecastHistory.map { h ->
                    ForecastReading(h.timestamp, h.ph, h.tds, h.turbidity, h.temperature!!, h.red, h.green, h.blue, h.clear, h.opticalColourIndex!!, h.calibrationId, h.source)
                })
                val forecastResponse = api.generateForecast(req)
                if (forecastResponse.isSuccessful) forecast = forecastResponse.body()
            } else forecast = null
        } catch (e: Exception) {
            error = "Unable to connect to HydroGuard server"
            reading = null; history = emptyList(); alerts = emptyList(); forecast = null
        } finally { loading = false }
    }
    LaunchedEffect(nodeId) { load() }

    Column(modifier.fillMaxSize()) {
        ScrollableTabRow(selectedTabIndex = selected) {
            listOf("Current", "Trends", "Forecast", "Alerts").forEachIndexed { i, label -> Tab(selected == i, { selected = i }, text = { Text(label) }) }
        }
        LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item {
                SectionHeader(if (isAdmin) "Admin Dashboard · Water Monitoring" else "Water quality", trailing = {
                    Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                        IconButton(onClick = { scope.launch { load() } }, enabled = !loading) { Icon(Icons.Default.Refresh, "Refresh server data") }
                        if (onLogout != null) TextButton(onClick = onLogout) { Text("Sign out") }
                    }
                })
                Text("Node $nodeId", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                if (isAdmin) {
                    nodeHealth?.let { health ->
                        Text("Sensor/Node Health · ${health.status.uppercase()} · ${health.name} · ${health.location} · Last seen ${health.last_seen ?: "not reported"}", style = MaterialTheme.typography.bodySmall)
                    }
                    if (nodeHealth == null && !loading) Text("Sensor/Node Health unavailable", style = MaterialTheme.typography.bodySmall)
                }
            }
            if (loading) item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
            error?.let { item { EmptyState("Unable to connect to HydroGuard server", "Check the connection and try again.") } }
            when (selected) {
                0 -> {
                    if (!loading && error == null && reading == null) item {
                        EmptyState(if (isAdmin) "Analytics unavailable" else "No current reading available", "The server has no current observation for this node.")
                    }
                    reading?.let { r ->
                        item { Card(shape = RoundedCornerShape(20.dp)) { Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text("Current observation", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                            val index = r.temperature?.let { WaterQualityIndexService.calculate(r.ph, r.tds, r.turbidity, it) }
                            Text(index?.let { "Application Water Quality Index ${it.index} · ${it.category.displayName}" } ?: "Application Water Quality Index unavailable: temperature is missing", style = MaterialTheme.typography.bodyLarge)
                            Text("This application index is not drinking-water certification.", style = MaterialTheme.typography.bodySmall)
                            Text("${provenanceLabel(r.source)} · ${r.timestamp}", style = MaterialTheme.typography.labelSmall)
                        } } }
                        item { SectionHeader("Sensor readings") }
                        item { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Metric("pH", r.ph, "")
                            Metric("TDS", r.tds, "ppm")
                            Metric("Turbidity", r.turbidity, "NTU")
                            Metric("Temperature", r.temperature, "°C")
                            Metric("Experimental Optical Colour Index", r.opticalColourIndex, "index")
                        } }
                    }
                    item { Text("Provenance: values shown here are returned by the HydroGuard server. Source and timestamp are shown with the current observation.", style = MaterialTheme.typography.bodySmall) }
                }
                1 -> {
                    item { SectionHeader("Historical trends") }
                    if (history.size < 2) item { EmptyState("No sufficient historical data", "Historical observations are needed to show a trend.") }
                    else item {
                        Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(14.dp)) {
                            Text("pH · historical observations", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                            Text("${history.size} server records · source varies by observation", style = MaterialTheme.typography.bodySmall)
                            TrendPlot(history.takeLast(30).map { it.ph })
                        } }
                    }
                    items(history.takeLast(30), key = { it.id }) { h ->
                        Card(Modifier.fillMaxWidth()) { Row(Modifier.padding(12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                            Column(Modifier.weight(1f)) { Text(h.timestamp.take(16)); Text(h.source, style = MaterialTheme.typography.bodySmall) }
                            Text(String.format(Locale.getDefault(), "pH %.2f · TDS %.0f", h.ph, h.tds), fontWeight = FontWeight.Medium)
                        } }
                    }
                }
                2 -> {
                    item { SectionHeader("Forecast") }
                    val f = forecast
                    if (f == null) item { EmptyState("No sufficient historical data", "Forecast requires at least 30 complete, timestamped server observations.") }
                    else {
                        item { Card { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text("Adaptive Ensemble · ${f.forecastDate} · ${f.forecastHorizonHours} hour horizon", fontWeight = FontWeight.Bold)
                            Text("pH ${f.prediction.pH} · TDS ${f.prediction.TDS} · Turbidity ${f.prediction.turbidity} · Temperature ${f.prediction.temperature}°C · Optical colour ${f.prediction.opticalColourIndex}")
                            Text("Source ${f.dataSource} · weights ${f.weightStatus}", style = MaterialTheme.typography.bodySmall)
                        } } }
                        item { Text("Individual model forecasts", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold) }
                        f.modelPredictions.orEmpty().toSortedMap().forEach { (model, prediction) ->
                            item {
                                Column {
                                    Text("$model · pH ${prediction.pH} · TDS ${prediction.TDS} · Turbidity ${prediction.turbidity} · Temperature ${prediction.temperature}°C · Optical colour ${prediction.opticalColourIndex}", style = MaterialTheme.typography.bodySmall)
                                    f.modelVersions[model]?.let { Text("Model version: $it", style = MaterialTheme.typography.labelSmall) }
                                }
                            }
                        }
                        f.weights.orEmpty().toSortedMap().forEach { (parameter, modelWeights) ->
                            item { Text("$parameter ensemble weights · LSTM ${modelWeights.LSTM} · PatchTST ${modelWeights.PatchTST} · TimeMixer ${modelWeights.TimeMixer}", style = MaterialTheme.typography.labelSmall) }
                        }
                        item { Text("Optical colour is an experimental development feature, not a validated water-safety measure.", style = MaterialTheme.typography.bodySmall) }
                    }
                }
                else -> {
                    item { SectionHeader("Alerts and anomalies") }
                    if (!loading && error == null && alerts.isEmpty()) item { EmptyState("No active alerts recorded", "This does not establish water safety.") }
                    items(alerts, key = { it.id }) { a ->
                        Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
                            Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                Text("${a.severity} · ${a.parameter}", fontWeight = FontWeight.Bold)
                                Text(a.message)
                                Text("${a.timestamp} · status ${a.status}", style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                }
            }
        }
    }
}

private fun provenanceLabel(source: String): String = when (source.uppercase()) {
    "REAL_SENSOR" -> "REAL SENSOR"
    "DEMO", "HISTORICAL_DEMO" -> "HISTORICAL DEMO"
    "SIMULATED", "DEVELOPMENT" -> "SIMULATED / DEVELOPMENT"
    else -> source.uppercase()
}

@Composable
private fun Metric(label: String, value: Float?, unit: String) {
    Card(Modifier.fillMaxWidth()) { Row(Modifier.padding(horizontal = 14.dp, vertical = 12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
        Text(value?.let { String.format(Locale.getDefault(), "%.2f %s", it, unit).trim() } ?: "Unavailable", fontWeight = FontWeight.SemiBold)
    } }
}

@Composable
private fun TrendPlot(values: List<Float>) {
    val color = MaterialTheme.colorScheme.primary
    Canvas(Modifier.fillMaxWidth().height(140.dp)) {
        if (values.size < 2) return@Canvas
        val lo = values.minOrNull() ?: return@Canvas
        val hi = values.maxOrNull() ?: return@Canvas
        val range = (hi - lo).takeIf { it > 0f } ?: 1f
        val points = values.mapIndexed { i, value ->
            Offset(size.width * i / (values.lastIndex), size.height - ((value - lo) / range) * size.height)
        }
        points.zipWithNext().forEach { (a, b) -> drawLine(color, a, b, strokeWidth = 4.dp.toPx(), cap = StrokeCap.Round) }
        points.forEach { drawCircle(color, radius = 3.dp.toPx(), center = it) }
    }
}
