package com.example.ui.screens.student

import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.WaterDrop
import androidx.compose.material.icons.filled.AddAPhoto
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.example.data.api.*
import com.example.data.repository.ApiFailureKind
import com.example.data.repository.ApiRepository
import com.example.data.repository.ApiRequestFailure
import com.example.data.service.WaterQualityIndexService
import com.example.ui.viewmodel.HydroViewModel
import com.example.ui.components.EmptyState
import com.example.ui.components.ErrorState
import com.example.ui.components.HydroCard
import com.example.ui.components.LoadingState
import com.example.ui.components.MetricCard
import com.example.ui.components.SectionHeader
import com.example.ui.components.StatusChip
import com.example.ui.components.StatusTone
import com.example.ui.theme.HydroGuardColors
import com.example.ui.theme.HydroGuardShapes
import com.example.ui.components.PrimaryButton
import com.example.ui.components.SecondaryButton
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

private fun nowUtcIso(): String = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US)
    .apply { timeZone = TimeZone.getTimeZone("UTC") }
    .format(Date())

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HostelHomeScreen(
    viewModel: HydroViewModel,
    onNavigate: (Int) -> Unit,
    modifier: Modifier = Modifier,
    onNavigateToAlerts: (() -> Unit)? = null,
    onSignIn: () -> Unit = {}
) {
    val user by viewModel.currentUser.collectAsState()
    val node by viewModel.selectedNodeId.collectAsState()
    val api = remember { ApiRepository() }
    var notices by remember { mutableStateOf<List<HostelNoticeResponse>>(emptyList()) }
    var serverFailure by remember { mutableStateOf<ApiRequestFailure?>(null) }
    var loading by remember { mutableStateOf(false) }
    var currentReading by remember { mutableStateOf<LatestReadingResponse?>(null) }
    var activeAlerts by remember { mutableStateOf<List<AlertResponse>>(emptyList()) }
    val scope = rememberCoroutineScope()

    suspend fun reloadOverview() {
        loading = true
        serverFailure = null
        api.getLatestReading(node).onSuccess {
            currentReading = it
        }.onFailure { failure ->
            currentReading = null
            serverFailure = failure as? ApiRequestFailure
                ?: ApiRequestFailure(ApiFailureKind.API_ERROR, "/api/v1/nodes/$node/readings/latest", cause = failure)
        }
        api.getAlerts(node).onSuccess { result ->
            activeAlerts = result.alerts.filter { it.status.equals("ACTIVE", ignoreCase = true) }
        }.onFailure {
            activeAlerts = emptyList()
        }
        api.getHostelNotices().onSuccess { notices = it }.onFailure { notices = emptyList() }
        loading = false
    }
    LaunchedEffect(node) { reloadOverview() }

    val score = currentReading?.temperature?.let { temperature ->
        currentReading?.let { WaterQualityIndexService.calculate(it.ph, it.tds, it.turbidity, temperature) }
    }
    val qualityStatus = when {
        serverFailure != null || currentReading == null -> "UNAVAILABLE"
        activeAlerts.any { it.severity.equals("CRITICAL", true) } -> "CRITICAL"
        activeAlerts.isNotEmpty() -> "ATTENTION"
        score?.category?.name in setOf("EXCELLENT", "GOOD") -> "GOOD"
        score?.category?.name == "MODERATE" -> "ATTENTION"
        score?.category?.name in setOf("POOR", "CRITICAL") -> "CRITICAL"
        else -> "UNAVAILABLE"
    }
    val qualityTone = when (qualityStatus) {
        "GOOD" -> StatusTone.HEALTHY
        "ATTENTION" -> StatusTone.ATTENTION
        "CRITICAL" -> StatusTone.CRITICAL
        else -> StatusTone.NEUTRAL
    }
    val qualityExplanation = when (qualityStatus) {
        "GOOD" -> "Your latest monitored readings are within the expected range."
        "ATTENTION" -> "Some readings may need attention."
        "CRITICAL" -> "A critical water alert is active."
        else -> if (serverFailure?.kind == ApiFailureKind.AUTHENTICATION && serverFailure?.statusCode == 401) {
            "Please sign in again to continue."
        } else "Water data temporarily unavailable."
    }

    Scaffold(
        modifier = modifier,
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            TopAppBar(
                title = {
                    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text("HydroGuard", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                        Text("Welcome back, ${user?.name?.ifBlank { "there" } ?: "there"}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                },
                actions = {
                    IconButton(onClick = { scope.launch { reloadOverview() } }, enabled = !loading) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh water data")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background)
            )
        }
    ) { padding ->
        LazyColumn(
            Modifier.fillMaxSize().padding(padding).padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
            contentPadding = PaddingValues(top = 12.dp, bottom = 24.dp)
        ) {
            item {
                HydroCard(shape = RoundedCornerShape(20.dp), containerColor = MaterialTheme.colorScheme.primaryContainer) {
                    Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("WATER QUALITY", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
                        StatusChip(qualityStatus, tone = qualityTone)
                        Text(qualityExplanation, style = MaterialTheme.typography.bodyMedium)
                        if (qualityStatus == "UNAVAILABLE" && serverFailure?.kind == ApiFailureKind.AUTHENTICATION && serverFailure?.statusCode != 403) {
                            TextButton(onClick = onSignIn) { Text("Sign in") }
                        } else if (qualityStatus == "UNAVAILABLE") {
                            SecondaryButton("Retry", onAction = { scope.launch { reloadOverview() } })
                        } else {
                            SecondaryButton("View Water Details", onAction = { onNavigate(1) })
                        }
                        if (loading && currentReading == null) LoadingState("Loading water quality")
                    }
                }
            }

            currentReading?.let { reading ->
                item { SectionHeader("Current readings") }
                val metrics = listOf(
                    Triple("pH", "%.2f".format(Locale.getDefault(), reading.ph), null),
                    Triple("TDS", "%.0f".format(Locale.getDefault(), reading.tds), "ppm"),
                    Triple("Turbidity", "%.2f".format(Locale.getDefault(), reading.turbidity), "NTU"),
                    Triple("Temperature", reading.temperature?.let { "%.1f".format(Locale.getDefault(), it) } ?: "—", "°C"),
                    Triple("Optical Colour", reading.opticalColourIndex?.let { "%.3f".format(Locale.getDefault(), it) } ?: "—", "index")
                )
                metrics.take(4).chunked(2).forEachIndexed { rowIndex, pair ->
                    item(key = "home-metrics-$rowIndex") {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            pair.forEach { (label, value, unit) ->
                                MetricCard(
                                    label = label,
                                    value = value,
                                    unit = unit,
                                    note = if (label == "Temperature" && reading.temperature == null) "Not reported" else null,
                                    modifier = Modifier.weight(1f)
                                )
                            }
                        }
                    }
                }
                item {
                    MetricCard(
                        label = "Optical Colour",
                        value = reading.opticalColourIndex?.let { "%.3f".format(Locale.getDefault(), it) } ?: "—",
                        unit = "index",
                        note = "Experimental",
                        tone = StatusTone.AI,
                        badge = "EXPERIMENTAL",
                        modifier = Modifier.fillMaxWidth()
                    )
                }
            }

            if (activeAlerts.isNotEmpty()) {
                item { SectionHeader("Active Alerts") }
                item {
                val newestAlert = activeAlerts.maxByOrNull { it.timestamp }
                HydroCard(containerColor = if (activeAlerts.any { it.severity.equals("CRITICAL", true) }) HydroGuardColors.criticalTint else HydroGuardColors.warningTint) {
                    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("${activeAlerts.size} active alert${if (activeAlerts.size == 1) "" else "s"}", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                        newestAlert?.let { Text(it.message, style = MaterialTheme.typography.bodySmall) }
                        TextButton(onClick = { onNavigateToAlerts?.invoke() ?: onNavigate(1) }) { Text("View alerts") }
                    }
                }
                }
            }

            item { SectionHeader("Quick Actions") }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    listOf("Report Issue" to 2, "My Issues" to 3).forEach { (label, tab) ->
                        OutlinedButton(onClick = { onNavigate(tab) }, modifier = Modifier.weight(1f), shape = RoundedCornerShape(12.dp)) {
                            Text(label, maxLines = 1, style = MaterialTheme.typography.labelSmall)
                        }
                    }
                }
            }

            if (notices.isNotEmpty()) {
                item { SectionHeader("Notices") }
                items(notices.take(5), key = { "home-notice-${it.id}" }) { notice ->
                    HydroCard {
                        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            StatusChip("${notice.priority} · ${notice.category}", tone = StatusTone.NEUTRAL)
                            Text(notice.title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                            Text(notice.body, style = MaterialTheme.typography.bodyMedium)
                        }
                    }
                }
            }
        }
    }
}

private fun apiFailureDetail(failure: ApiRequestFailure): String = when (failure.kind) {
    ApiFailureKind.AUTHENTICATION -> if (failure.statusCode == 401) "Please sign in again to continue." else "We couldn't load this information right now."
    ApiFailureKind.NO_READING -> "Water data temporarily unavailable."
    ApiFailureKind.API_ERROR, ApiFailureKind.MALFORMED_RESPONSE, ApiFailureKind.SERVER_UNREACHABLE -> "We couldn't load this information right now."
    ApiFailureKind.INSUFFICIENT_DATA -> "Not enough complete historical readings are available to generate the next-day forecast."
}

private fun friendlyIssueStatus(status: String): String = when (status.uppercase()) {
    "SUBMITTED" -> "Submitted"
    "ACKNOWLEDGED" -> "Acknowledged"
    "ASSIGNED" -> "Assigned"
    "IN_PROGRESS" -> "In Progress"
    "RESOLVED" -> "Resolved"
    "CLOSED" -> "Closed"
    "REOPENED" -> "Reopened"
    else -> status.lowercase().replace('_', ' ').replaceFirstChar { it.uppercase() }
}

private fun issueTitle(issue: HostelIssueResponse): String = issue.description
    .lineSequence()
    .firstOrNull()
    .orEmpty()
    .trim()
    .let { title -> if (title.length > 72) "${title.take(69)}…" else title.ifBlank { issue.category } }

private fun safeHttpFailureMessage(statusCode: Int, fallback: String): String = when (statusCode) {
    401 -> "Please sign in again to continue."
    403 -> "We couldn't load this information right now."
    else -> fallback
}

private fun safeServiceFailureMessage(error: Throwable, fallback: String): String {
    val apiFailure = error as? ApiRequestFailure
    return when {
        apiFailure?.kind == ApiFailureKind.AUTHENTICATION -> apiFailureDetail(apiFailure)
        apiFailure?.kind == ApiFailureKind.SERVER_UNREACHABLE -> "We couldn't load this information right now."
        apiFailure?.kind == ApiFailureKind.MALFORMED_RESPONSE -> "We couldn't load this information right now."
        error is retrofit2.HttpException -> safeHttpFailureMessage(error.code(), "We couldn't load this information right now.")
        error is java.io.IOException -> "We couldn't load this information right now."
        else -> fallback
    }
}

private fun requiresSignIn(error: Throwable): Boolean {
    val apiFailure = error as? ApiRequestFailure
    return (apiFailure?.kind == ApiFailureKind.AUTHENTICATION && apiFailure.statusCode != 403) ||
        (error as? retrofit2.HttpException)?.code() == 401
}

@Composable
fun WaterScreen(
    viewModel: HydroViewModel,
    modifier: Modifier = Modifier,
    initialTab: Int = 0,
    onSignIn: (() -> Unit)? = null
) {
    ServerWaterScreen(viewModel, modifier, initialTab = initialTab, onSignIn = onSignIn)
}

@Composable
fun ReportIssueScreen(modifier: Modifier = Modifier, onSignIn: () -> Unit = {}) {
    val categories = listOf("Water", "Plumbing", "Electrical", "Room / Furniture", "Cleaning", "Bathroom", "Wi-Fi", "Other")
    var category by remember { mutableStateOf(categories.first()) }
    var location by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var severity by remember { mutableStateOf("Medium") }
    var selectedPhoto by remember { mutableStateOf<Uri?>(null) }
    var message by remember { mutableStateOf<String?>(null) }
    var authRequired by remember { mutableStateOf(false) }
    var submittedIssue by remember { mutableStateOf<HostelIssueResponse?>(null) }
    var sending by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    Column(
        modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).imePadding().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        SectionHeader("Report an issue", subtitle = "Send a service request to hostel operations")
        Text("Your report is saved to the hostel service. Do not include passwords or other sensitive personal information.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        HydroCard {
            Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                CategorySelector("Issue category", categories, category) { category = it }
                OutlinedTextField(
                    value = location,
                    onValueChange = { location = it },
                    label = { Text("Room / Location") },
                    placeholder = { Text("Room number or location") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                OutlinedTextField(description, { description = it }, label = { Text("Describe the issue") }, modifier = Modifier.fillMaxWidth(), minLines = 3)
                CategorySelector("Urgency", listOf("Low", "Medium", "High", "Urgent"), severity) { severity = it }
                PhotoAttachmentPicker(selectedPhoto) { selectedPhoto = it }
                PrimaryButton(
                    text = if (sending) "Submitting…" else "Submit issue",
                    enabled = !sending && location.isNotBlank() && description.trim().length >= 5,
                    onAction = {
                        sending = true
                        message = null
                        authRequired = false
                        val includedPhoto = selectedPhoto != null
                        scope.launch {
                            runCatching {
                                val apiCategory = if (category == "Room / Furniture") "Room/Furniture" else category
                                val response = RetrofitClient.apiService.createHostelIssue(
                                    CreateIssueRequest(
                                        category = apiCategory,
                                        location = location.trim(),
                                        description = description.trim(),
                                        severity = severity.uppercase(),
                                        imageUrl = null
                                    )
                                )
                                if (!response.isSuccessful) {
                                    authRequired = response.code() == 401
                                    error(safeHttpFailureMessage(response.code(), "We couldn't submit this report. Please try again."))
                                }
                                response.body() ?: error("We couldn't submit this report. Please try again.")
                            }.onSuccess { issue ->
                                submittedIssue = issue
                                selectedPhoto = null
                                message = if (includedPhoto) {
                    "Issue submitted. Photos are not attached to reports yet."
                                } else {
                                    "Issue submitted successfully."
                                }
                            }.onFailure { failure ->
                                message = if (authRequired) "Please sign in again to continue."
                                    else safeServiceFailureMessage(failure, "We couldn't submit this report. Please try again.")
                            }
                            sending = false
                        }
                    }
                )
                message?.let {
                    Text(it, color = if (submittedIssue != null) HydroGuardColors.healthy else MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                }
                if (authRequired) TextButton(onClick = onSignIn) { Text("Sign in") }
            }
        }
        submittedIssue?.let { issue ->
            HydroCard {
                Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Issue submitted", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                    StatusChip(friendlyIssueStatus(issue.status), tone = StatusTone.NEUTRAL)
                }
            }
        }
    }
}

@Composable
private fun PhotoAttachmentPicker(selectedPhoto: Uri?, onPhotoSelected: (Uri?) -> Unit) {
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) onPhotoSelected(uri)
    }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedButton(
            onClick = { picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) },
            modifier = Modifier.fillMaxWidth(),
            shape = HydroGuardShapes.button
        ) {
            Icon(Icons.Default.AddAPhoto, contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text(if (selectedPhoto == null) "Add Photo" else "Replace Photo")
        }
        selectedPhoto?.let { uri ->
            HydroCard {
                Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    AsyncImage(
                        model = uri,
                        contentDescription = "Selected photo preview",
                        contentScale = ContentScale.Crop,
                        modifier = Modifier.fillMaxWidth().height(180.dp).clip(RoundedCornerShape(12.dp))
                    )
                    TextButton(onClick = { onPhotoSelected(null) }, modifier = Modifier.align(Alignment.End)) { Text("Remove photo") }
                }
            }
        }
        Text(
            "Photos can be previewed here, but they are not attached to reports yet.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

@Composable
fun MyIssuesScreen(modifier: Modifier = Modifier, onSignIn: () -> Unit = {}) {
    var issues by remember { mutableStateOf<List<HostelIssueResponse>>(emptyList()) }
    var selected by remember { mutableStateOf<HostelIssueResponse?>(null) }
    var timeline by remember { mutableStateOf<List<IssueEventResponse>>(emptyList()) }
    var message by remember { mutableStateOf<String?>(null) }
    var issuesLoadFailure by remember { mutableStateOf<ApiRequestFailure?>(null) }
    var loading by remember { mutableStateOf(false) }
    var stars by remember { mutableIntStateOf(0) }
    var comment by remember { mutableStateOf("") }
    var reopenReason by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    val api = remember { ApiRepository() }

    suspend fun reload() {
        loading = true
        issuesLoadFailure = null
        api.getHostelIssues()
            .onSuccess { issues = it; issuesLoadFailure = null }
            .onFailure {
                issuesLoadFailure = it as? ApiRequestFailure
                    ?: ApiRequestFailure(ApiFailureKind.API_ERROR, "/api/v1/hostel/issues", cause = it)
            }
        loading = false
    }
    LaunchedEffect(Unit) { reload() }

    Column(modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        SectionHeader(
            if (selected == null) "My issues" else "Issue ${selected!!.id}",
            subtitle = if (selected == null) "Track reports sent to hostel operations" else "Review progress, feedback, or reopen this issue",
            trailing = {
                if (selected == null) IconButton(onClick = { scope.launch { reload() } }, enabled = !loading) { Icon(Icons.Default.Refresh, contentDescription = "Refresh issues") }
                else TextButton(onClick = { selected = null; message = null }) { Text("All issues", maxLines = 1) }
            }
        )
        issuesLoadFailure?.let { failure ->
            val authFailure = failure.kind == ApiFailureKind.AUTHENTICATION && failure.statusCode != 403
            ErrorState(
                title = if (authFailure) "Sign in required" else "Couldn't load your issues",
                detail = if (authFailure) "Please sign in again to continue." else "We couldn't load this information right now.",
                actionLabel = if (authFailure) "Sign in" else "Retry",
                onAction = { if (authFailure) onSignIn() else scope.launch { reload() } }
            )
        }
        message?.let { Text(it, color = if (it.contains("saved", true) || it.contains("reopened", true)) HydroGuardColors.healthy else MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
        if (loading) LinearProgressIndicator(Modifier.fillMaxWidth())
        if (selected == null) {
            if (issues.isEmpty() && !loading && issuesLoadFailure == null) {
                EmptyState("No issues yet", "You haven't reported any hostel issues.", icon = Icons.Default.Info)
            } else if (issues.isNotEmpty()) {
                LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(12.dp), contentPadding = PaddingValues(bottom = 16.dp)) {
                    items(issues, key = { it.id }) { issue ->
                        HydroCard {
                            Column(
                                Modifier.fillMaxWidth().clickable {
                                    selected = issue
                                    scope.launch {
                                        api.getIssueTimeline(issue.id)
                                            .onSuccess { timeline = it; issuesLoadFailure = null }
                                            .onFailure {
                                                issuesLoadFailure = it as? ApiRequestFailure
                                                    ?: ApiRequestFailure(ApiFailureKind.API_ERROR, "/api/v1/hostel/issues/${issue.id}/timeline", cause = it)
                                            }
                                    }
                                }.padding(16.dp),
                                verticalArrangement = Arrangement.spacedBy(6.dp)
                            ) {
                                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                                    Text(issueTitle(issue), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                                    StatusChip(friendlyIssueStatus(issue.status), tone = if (issue.status in setOf("RESOLVED", "CLOSED")) StatusTone.HEALTHY else StatusTone.NEUTRAL)
                                }
                                Text("Category: ${issue.category}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Text("${issue.location} · ${issue.createdAt.take(10)}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                }
            }
        } else {
            val issue = selected!!
            LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(12.dp), contentPadding = PaddingValues(bottom = 20.dp)) {
                item {
                    HydroCard {
                        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                                Text(issueTitle(issue), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                                StatusChip(friendlyIssueStatus(issue.status), tone = if (issue.status in setOf("RESOLVED", "CLOSED")) StatusTone.HEALTHY else StatusTone.NEUTRAL)
                            }
                            Text("Category: ${issue.category} · ${issue.location} · ${issue.createdAt.take(10)}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text(issue.description, style = MaterialTheme.typography.bodyMedium)
                            issue.resolution?.let { Text("Resolution: $it", style = MaterialTheme.typography.bodySmall) }
                        }
                    }
                }
                item { SectionHeader("Status timeline") }
                if (timeline.isEmpty()) item { EmptyState("Timeline unavailable", "No status events were returned for this issue.") }
                items(timeline, key = { it.id }) { event ->
                    HydroCard {
                        Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            StatusChip(friendlyIssueStatus(event.toStatus), tone = StatusTone.NEUTRAL)
                            Text(event.createdAt, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            event.comment?.takeIf { it.isNotBlank() }?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                        }
                    }
                }
                if (issue.status == "RESOLVED" || issue.status == "CLOSED") item {
                    HydroCard {
                        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            SectionHeader("Resolution feedback", subtitle = "Rate the resolved service from 1 to 5")
                            com.example.ui.components.RatingStars(rating = stars, onRatingChanged = { stars = it })
                            OutlinedTextField(comment, { comment = it }, label = { Text("Optional comment") }, modifier = Modifier.fillMaxWidth())
                            PrimaryButton(enabled = stars > 0, text = "Send feedback", onAction = {
                                scope.launch {
                                    api.submitResolutionFeedback(issue.id, IssueFeedbackRequest(stars, comment.ifBlank { null }))
                                        .onSuccess { message = "Feedback saved." }
                                        .onFailure {
                                            val failure = it as? ApiRequestFailure
                                            if (failure?.kind == ApiFailureKind.AUTHENTICATION) issuesLoadFailure = failure
                                            else message = safeServiceFailureMessage(it, "Could not save feedback.")
                                        }
                                }
                            })
                            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                            Text("Need more help? Reopen the issue with a short reason.", style = MaterialTheme.typography.bodySmall)
                            OutlinedTextField(reopenReason, { reopenReason = it }, label = { Text("Reason to reopen") }, modifier = Modifier.fillMaxWidth())
                            SecondaryButton(enabled = reopenReason.trim().length >= 5, text = "Reopen issue", onAction = {
                                scope.launch {
                                    api.reopenIssue(issue.id, IssueReopenRequest(reopenReason.trim()))
                                        .onSuccess { reopened -> message = "Issue reopened."; selected = reopened; reload() }
                                        .onFailure {
                                            val failure = it as? ApiRequestFailure
                                            if (failure?.kind == ApiFailureKind.AUTHENTICATION) issuesLoadFailure = failure
                                            else message = safeServiceFailureMessage(it, "Could not reopen this issue.")
                                        }
                                }
                            })
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StudentProfileScreen(viewModel: HydroViewModel, onLogout: () -> Unit, modifier: Modifier = Modifier) {
    val user by viewModel.currentUser.collectAsState()
    val darkMode by viewModel.isDarkMode.collectAsState()
    var contacts by remember { mutableStateOf<List<EmergencyContactResponse>>(emptyList()) }
    var lostItems by remember { mutableStateOf<List<LostFoundResponse>>(emptyList()) }
    var feedbackCategory by remember { mutableStateOf("Overall Hostel Experience") }
    var feedbackRating by remember { mutableIntStateOf(0) }
    var feedbackComment by remember { mutableStateOf("") }
    var lostKind by remember { mutableStateOf("LOST") }
    var lostCategory by remember { mutableStateOf("Other") }
    var lostTitle by remember { mutableStateOf("") }
    var lostDescription by remember { mutableStateOf("") }
    var lostLocation by remember { mutableStateOf("") }
    var lostItemDate by remember { mutableStateOf(nowUtcIso()) }
    var selectedLostPhoto by remember { mutableStateOf<Uri?>(null) }
    var showDatePicker by remember { mutableStateOf(false) }
    val datePickerState = rememberDatePickerState(initialSelectedDateMillis = System.currentTimeMillis())
    var serviceMessage by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var authRequired by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    suspend fun reloadServices() {
        error = null
        authRequired = false
        runCatching {
            val api = RetrofitClient.apiService
            val contactResponse = api.getEmergencyContacts()
            val lostResponse = api.getLostFoundItems()
            val failedResponse = listOf(contactResponse, lostResponse).firstOrNull { !it.isSuccessful }
            if (failedResponse != null) {
                authRequired = failedResponse.code() == 401
                error = safeHttpFailureMessage(failedResponse.code(), "We couldn't load this information right now.")
                return@runCatching
            }
            contacts = contactResponse.body().orEmpty()
            lostItems = lostResponse.body().orEmpty()
        }.onFailure { failure ->
            authRequired = requiresSignIn(failure)
            error = if (authRequired) "Please sign in again to continue."
                else safeServiceFailureMessage(failure, "We couldn't load this information right now.")
        }
    }
    LaunchedEffect(Unit) { reloadServices() }
    val visibleContacts = contacts.filter {
        it.active && it.verified && it.category.uppercase() in setOf("WARDEN", "SECURITY")
    }

    LazyColumn(
        modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
        contentPadding = PaddingValues(top = 16.dp, bottom = 24.dp)
    ) {
        item { SectionHeader("Profile", subtitle = "Account and hostel services") }
        item {
            HydroCard(containerColor = MaterialTheme.colorScheme.primaryContainer) {
                Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(user?.name ?: "Signed-in account", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    Text(user?.email.orEmpty(), style = MaterialTheme.typography.bodyMedium)
                    StatusChip("${friendlyIssueStatus(user?.role ?: "STUDENT")}", tone = StatusTone.NEUTRAL)
                    user?.roomNumber?.takeIf { it.isNotBlank() }?.let { Text("Room $it", style = MaterialTheme.typography.bodySmall) }
                }
            }
        }
        item {
            HydroCard {
                Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                    Column { Text("Dark theme", fontWeight = FontWeight.SemiBold); Text("Appearance preference", style = MaterialTheme.typography.bodySmall) }
                    Switch(checked = darkMode, onCheckedChange = { viewModel.toggleDarkMode() })
                }
            }
        }
        item { SectionHeader("Emergency contacts", subtitle = "Verified Warden and Security contacts") }
        if (visibleContacts.isEmpty() && error == null) {
            item { EmptyState("Emergency contacts unavailable", "Ask hostel administration to add a verified contact.") }
        } else {
            items(visibleContacts, key = { "emergency-${it.id}" }) { contact ->
                HydroCard(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(contact.category.lowercase().replaceFirstChar { it.uppercase() }, style = MaterialTheme.typography.labelLarge)
                        Text(contact.name, fontWeight = FontWeight.SemiBold)
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(contact.phone, modifier = Modifier.weight(1f))
                            TextButton(onClick = {
                                val dialIntent = Intent(Intent.ACTION_DIAL, Uri.fromParts("tel", contact.phone, null))
                                runCatching { context.startActivity(dialIntent) }
                                    .onFailure { Toast.makeText(context, "Calling is unavailable on this device.", Toast.LENGTH_SHORT).show() }
                            }) {
                                Text("Call ${contact.category.lowercase().replaceFirstChar { it.uppercase() }}")
                            }
                        }
                        contact.details?.takeIf(String::isNotBlank)?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                    }
                }
            }
        }

        item { SectionHeader("Lost & Found", subtitle = "Items submitted to hostel operations") }
        if (lostItems.isEmpty() && error == null) item { EmptyState("No listings", "There are no lost or found items to show.") }
        items(lostItems, key = { it.id }) { item ->
            HydroCard(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    StatusChip("${friendlyIssueStatus(item.kind)} · ${friendlyIssueStatus(item.moderationStatus)}", tone = StatusTone.NEUTRAL)
                    Text(item.title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                    Text("${item.category} · ${item.location} · ${item.itemDate.take(10)}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(item.description)
                }
            }
        }
        item { SectionHeader("Report a lost or found item", subtitle = "Submitted items go to an administrator for review") }
        item {
            HydroCard {
                Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    CategorySelector("Lost / Found", listOf("LOST", "FOUND"), lostKind) { lostKind = it }
                    CategorySelector("Category", listOf("ID", "Keys", "Phone", "Wallet", "Books", "Bag", "Electronics", "Other"), lostCategory) { lostCategory = it }
                    OutlinedTextField(lostTitle, { lostTitle = it }, label = { Text("Item title") }, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(lostDescription, { lostDescription = it }, label = { Text("Description") }, modifier = Modifier.fillMaxWidth(), minLines = 2)
                    OutlinedTextField(lostLocation, { lostLocation = it }, label = { Text("Location") }, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(
                        value = lostItemDate.take(10),
                        onValueChange = {},
                        label = { Text("Date") },
                        readOnly = true,
                        modifier = Modifier.fillMaxWidth(),
                        trailingIcon = {
                            IconButton(onClick = { showDatePicker = true }) {
                                Icon(Icons.Default.CalendarMonth, contentDescription = "Choose date")
                            }
                        }
                    )
                    PhotoAttachmentPicker(selectedLostPhoto) { selectedLostPhoto = it }
                    PrimaryButton(
                        enabled = lostTitle.isNotBlank() && lostDescription.trim().length >= 5 && lostLocation.isNotBlank(),
                        text = "Submit listing",
                        onAction = {
                            scope.launch {
                                val includedPhoto = selectedLostPhoto != null
                                runCatching {
                                    val response = RetrofitClient.apiService.createLostFoundItem(
                                        CreateLostFoundRequest(
                                            kind = lostKind,
                                            title = lostTitle.trim(),
                                            description = lostDescription.trim(),
                                            category = lostCategory,
                                            imageUrl = null,
                                            location = lostLocation.trim(),
                                            itemDate = lostItemDate
                                        )
                                    )
                                    if (!response.isSuccessful) {
                                        authRequired = response.code() == 401
                                        throw IllegalStateException(safeHttpFailureMessage(response.code(), "We couldn't submit this listing. Please try again."))
                                    }
                                    lostItems = RetrofitClient.apiService.getLostFoundItems().body().orEmpty()
                                    serviceMessage = if (includedPhoto) {
                                        "Listing submitted. Photos are not attached to listings yet."
                                    } else {
                                        "Item submitted for administrator review."
                                    }
                                    selectedLostPhoto = null
                                }.onFailure { failure ->
                                    authRequired = authRequired || requiresSignIn(failure)
                                    serviceMessage = if (authRequired) "Please sign in again to continue."
                                        else safeServiceFailureMessage(failure, "We couldn't submit this listing. Please try again.")
                                }
                            }
                        }
                    )
                }
            }
        }
        item { SectionHeader("General hostel feedback", subtitle = "Share a rating and optional comment") }
        item {
            HydroCard {
                Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    CategorySelector("Feedback category", listOf("Water", "Cleanliness", "Maintenance", "Wi-Fi", "Common Areas", "Overall Hostel Experience"), feedbackCategory) { feedbackCategory = it }
                    com.example.ui.components.RatingStars(rating = feedbackRating, onRatingChanged = { feedbackRating = it })
                    OutlinedTextField(feedbackComment, { feedbackComment = it }, label = { Text("Optional comment") }, modifier = Modifier.fillMaxWidth())
                    PrimaryButton(
                        enabled = feedbackRating > 0,
                        text = "Send feedback",
                        onAction = {
                            scope.launch {
                                runCatching { RetrofitClient.apiService.submitHostelFeedback(HostelFeedbackRequest(feedbackCategory, feedbackRating, feedbackComment.ifBlank { null })) }
                                    .onSuccess {
                                        authRequired = !it.isSuccessful && it.code() == 401
                                        serviceMessage = if (it.isSuccessful) "Feedback saved." else safeHttpFailureMessage(it.code(), "We couldn't save your feedback. Please try again.")
                                    }
                                    .onFailure { failure ->
                                        authRequired = requiresSignIn(failure)
                                        serviceMessage = if (authRequired) "Please sign in again to continue."
                                            else safeServiceFailureMessage(failure, "We couldn't save your feedback. Please try again.")
                                    }
                            }
                        }
                    )
                }
            }
        }
        item { SectionHeader("About HydroGuard") }
        item {
            HydroCard {
                Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("HydroGuard", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    Text("Smart Hostel Water Intelligence", style = MaterialTheme.typography.bodyMedium)
                    Text("Monitor hostel water quality, understand trends and forecasts, receive alerts, and report hostel issues in one application.", style = MaterialTheme.typography.bodySmall)
                    Text("Parameters: pH · TDS · Turbidity · Temperature · Optical Colour (Experimental)", style = MaterialTheme.typography.bodySmall)
                    Text("Your information helps hostel teams monitor water quality and respond to service requests.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
        item { SectionHeader("Privacy & Data") }
        item {
            HydroCard {
                Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Google authentication", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                    Text("Google sign-in protects access to your account.", style = MaterialTheme.typography.bodySmall)
                    Text("Water readings come from the connected monitoring service. Issue reports, feedback, and Lost & Found listings are shared with hostel operations.", style = MaterialTheme.typography.bodySmall)
                    Text("Selected photos can be previewed here, but they are not included with reports or listings.", style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        serviceMessage?.let { message ->
            item {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(
                        message,
                        color = if (message.contains("saved", true) || message.contains("submitted", true)) HydroGuardColors.healthy else MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall
                    )
                    if (authRequired) TextButton(onClick = onLogout) { Text("Sign in") }
                }
            }
        }
        error?.let { failure ->
            item {
                ErrorState(
                    if (authRequired) "Sign in required" else "We couldn't load hostel services",
                    if (authRequired) "Please sign in again to continue." else "We couldn't load this information right now.",
                    actionLabel = if (authRequired) "Sign in" else "Retry",
                    onAction = { if (authRequired) onLogout() else scope.launch { reloadServices() } }
                )
            }
        }
        item { SecondaryButton("Sign out", onAction = onLogout, modifier = Modifier.fillMaxWidth()) }
    }

    if (showDatePicker) {
        DatePickerDialog(
            onDismissRequest = { showDatePicker = false },
            confirmButton = {
                TextButton(onClick = {
                    datePickerState.selectedDateMillis?.let { millis ->
                        lostItemDate = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US)
                            .apply { timeZone = TimeZone.getTimeZone("UTC") }
                            .format(Date(millis))
                    }
                    showDatePicker = false
                }) { Text("Done") }
            },
            dismissButton = { TextButton(onClick = { showDatePicker = false }) { Text("Cancel") } }
        ) { DatePicker(state = datePickerState) }
    }
}

@Composable
private fun CategorySelector(label: String, options: List<String>, selected: String, onSelected: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(label, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
        options.chunked(3).forEach { rowOptions ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                rowOptions.forEach { option ->
                    FilterChip(
                        selected = selected == option,
                        onClick = { onSelected(option) },
                        label = { Text(option, maxLines = 2, style = MaterialTheme.typography.labelSmall) },
                        modifier = Modifier.weight(1f)
                    )
                }
                repeat(3 - rowOptions.size) { Spacer(Modifier.weight(1f)) }
            }
        }
    }
}
