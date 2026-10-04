package com.example.ui.screens.student

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.data.api.*
import com.example.data.service.WaterQualityIndexService
import com.example.ui.viewmodel.HydroViewModel
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
fun HostelHomeScreen(viewModel: HydroViewModel, onNavigate: (Int) -> Unit, modifier: Modifier = Modifier) {
    val user by viewModel.currentUser.collectAsState()
    val node by viewModel.selectedNodeId.collectAsState()
    var notices by remember { mutableStateOf<List<HostelNoticeResponse>>(emptyList()) }
    var issues by remember { mutableStateOf<List<HostelIssueResponse>>(emptyList()) }
    var dataError by remember { mutableStateOf<String?>(null) }
    var loading by remember { mutableStateOf(false) }
    var currentReading by remember { mutableStateOf<LatestReadingResponse?>(null) }
    var activeAlerts by remember { mutableStateOf<List<AlertResponse>>(emptyList()) }
    var alertStatusAvailable by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    suspend fun reloadOverview() {
        loading = true
        runCatching {
            val api = RetrofitClient.apiService
            val readingResponse = api.getLatestReading(node)
            if (readingResponse.isSuccessful) currentReading = readingResponse.body() else currentReading = null
            val alertsResponse = api.getAlerts(node)
            alertStatusAvailable = alertsResponse.isSuccessful
            activeAlerts = if (alertsResponse.isSuccessful) alertsResponse.body()?.alerts.orEmpty() else emptyList()
            val noticeResponse = api.getHostelNotices()
            val issueResponse = api.getHostelIssues()
            if (!noticeResponse.isSuccessful || !issueResponse.isSuccessful) error("Hostel information is unavailable.")
            notices = noticeResponse.body().orEmpty()
            issues = issueResponse.body().orEmpty()
            dataError = null
        }.onFailure { dataError = "Unable to connect to HydroGuard server" }
        loading = false
    }
    LaunchedEffect(node) { reloadOverview() }

    val score = remember(currentReading) {
        currentReading?.temperature?.let {
            WaterQualityIndexService.calculate(currentReading!!.ph, currentReading!!.tds, currentReading!!.turbidity, it)
        }
    }

    Scaffold(
        modifier = modifier,
        topBar = {
            TopAppBar(title = {
                Column {
                    Text("HydroGuard", fontWeight = FontWeight.Bold)
                    Text("${user?.hostelBlock?.takeIf { it.isNotBlank() }?.let { "Hostel $it" } ?: "Hostel not set"} · $node", style = MaterialTheme.typography.labelSmall)
                }
            }, actions = { IconButton(onClick = { scope.launch { reloadOverview() } }, enabled = !loading) { Icon(Icons.Default.Refresh, "Refresh") } })
        }
    ) { padding ->
        LazyColumn(Modifier.fillMaxSize().padding(padding).padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(12.dp), contentPadding = PaddingValues(bottom = 20.dp, top = 12.dp)) {
            item {
                Card(shape = RoundedCornerShape(20.dp)) {
                    Column(Modifier.fillMaxWidth().padding(18.dp)) {
                    Text("Water overview", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(6.dp))
                        Text(score?.let { "Application index: ${it.index} · ${it.category.displayName}" } ?: "Application index unavailable until required readings arrive.", style = MaterialTheme.typography.titleSmall)
                        Text("This application-specific index is not a drinking-water certification.", style = MaterialTheme.typography.bodySmall)
                        Spacer(Modifier.height(8.dp))
                        Text(currentReading?.let { "Source: ${it.source} · Updated ${it.timestamp}" } ?: "No current server reading available.", style = MaterialTheme.typography.bodySmall)
                        Text("Monitoring node: $node", style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            item { Text("SENSOR SUMMARY", style = MaterialTheme.typography.labelLarge) }
            currentReading?.let { r -> item {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    listOf("pH" to "${r.ph}", "TDS" to "${r.tds} ppm", "Turbidity" to "${r.turbidity} NTU", "Temperature" to (r.temperature?.let { "$it °C" } ?: "Unavailable"), "Experimental Optical Colour Index" to (r.opticalColourIndex?.toString() ?: "Unavailable")).forEach { (name, value) ->
                        Card(Modifier.fillMaxWidth()) { Row(Modifier.padding(horizontal = 14.dp, vertical = 10.dp), horizontalArrangement = Arrangement.SpaceBetween) { Text(name, Modifier.weight(1f)); Text(value, fontWeight = FontWeight.SemiBold) } }
                    }
                }
            } }
            item {
                Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = when {
                    !alertStatusAvailable -> MaterialTheme.colorScheme.surfaceVariant
                    activeAlerts.isEmpty() -> MaterialTheme.colorScheme.secondaryContainer
                    else -> MaterialTheme.colorScheme.errorContainer
                })) {
                    Column(Modifier.padding(14.dp)) {
                        Text(if (!alertStatusAvailable) "Alert status unavailable" else if (activeAlerts.isEmpty()) "No active alerts recorded" else "${activeAlerts.size} active alert${if (activeAlerts.size == 1) "" else "s"}", fontWeight = FontWeight.Bold)
                        Text(if (!alertStatusAvailable) "Unable to load alert status from the server." else if (activeAlerts.isEmpty()) "Monitoring has no current server alert. This does not establish water safety." else activeAlerts.first().message, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            item { Text("QUICK ACTIONS", style = MaterialTheme.typography.labelLarge) }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("Water" to 1, "Report issue" to 2, "My issues" to 3).forEach { (label, tab) ->
                        OutlinedButton(onClick = { onNavigate(tab) }, modifier = Modifier.weight(1f)) { Text(label) }
                    }
                }
            }
            item { Text("RECENT ISSUES", style = MaterialTheme.typography.labelLarge) }
            if (issues.isEmpty() && !loading) item { Text("No records available.", style = MaterialTheme.typography.bodyMedium) }
            items(issues.take(3), key = { it.id }) { issue ->
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(14.dp)) {
                        Text("${issue.category} · ${issue.status.replace('_', ' ')}", fontWeight = FontWeight.SemiBold)
                        Text(issue.location, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            item { Text("NOTICES", style = MaterialTheme.typography.labelLarge) }
            if (notices.isEmpty() && !loading) item { Text("No active notices.", style = MaterialTheme.typography.bodyMedium) }
            items(notices.take(5), key = { it.id }) { notice ->
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(14.dp)) {
                        Text("${notice.priority} · ${notice.category}", style = MaterialTheme.typography.labelSmall)
                        Text(notice.title, fontWeight = FontWeight.SemiBold)
                        Text(notice.body, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
            dataError?.let { message -> item { Text(message, color = MaterialTheme.colorScheme.error) } }
        }
    }
}

@Composable
fun WaterScreen(viewModel: HydroViewModel, modifier: Modifier = Modifier) {
    ServerWaterScreen(viewModel, modifier)
}

@Composable
fun ReportIssueScreen(modifier: Modifier = Modifier) {
    val categories = listOf("Water", "Plumbing", "Electrical", "Room/Furniture", "Cleaning", "Bathroom", "Wi-Fi", "Other")
    var category by remember { mutableStateOf(categories.first()) }
    var location by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var severity by remember { mutableStateOf("MEDIUM") }
    var imageUrl by remember { mutableStateOf("") }
    var message by remember { mutableStateOf<String?>(null) }
    var submittedIssue by remember { mutableStateOf<HostelIssueResponse?>(null) }
    var sending by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    Column(modifier.fillMaxSize().imePadding().verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Report an issue", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text("Your report is saved to the hostel service. Do not include passwords or other sensitive personal information.", style = MaterialTheme.typography.bodySmall)
        CategorySelector("Category", categories, category) { category = it }
        OutlinedTextField(location, { location = it }, label = { Text("Location") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        OutlinedTextField(description, { description = it }, label = { Text("Describe the issue") }, modifier = Modifier.fillMaxWidth(), minLines = 3)
        CategorySelector("Severity", listOf("LOW", "MEDIUM", "HIGH", "URGENT"), severity) { severity = it }
        OutlinedTextField(imageUrl, { imageUrl = it }, label = { Text("Optional HTTPS image link") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        Text("Direct image uploads are not configured. Only an HTTPS link is accepted.", style = MaterialTheme.typography.bodySmall)
        Button(
            onClick = {
                sending = true
                message = null
                scope.launch {
                    runCatching {
                        val response = RetrofitClient.apiService.createHostelIssue(
                            CreateIssueRequest(category, location.trim(), description.trim(), severity, imageUrl.trim().ifBlank { null })
                        )
                        if (!response.isSuccessful) error("Could not submit this report (${response.code()}).")
                        response.body() ?: error("The server did not return the created issue.")
                    }.onSuccess { issue -> submittedIssue = issue; message = "Issue submitted successfully." }
                        .onFailure { message = it.message ?: "Could not submit this report." }
                    sending = false
                }
            },
            enabled = !sending && location.isNotBlank() && description.trim().length >= 5,
            modifier = Modifier.fillMaxWidth()
        ) { Text(if (sending) "Submitting…" else "Submit report") }
        message?.let { Text(it, color = if (submittedIssue != null) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error) }
        submittedIssue?.let { issue ->
            Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(14.dp)) {
                Text("Issue ${issue.id}", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                Text("Status: ${issue.status}")
            } }
        }
    }
}

@Composable
fun MyIssuesScreen(modifier: Modifier = Modifier) {
    var issues by remember { mutableStateOf<List<HostelIssueResponse>>(emptyList()) }
    var selected by remember { mutableStateOf<HostelIssueResponse?>(null) }
    var timeline by remember { mutableStateOf<List<IssueEventResponse>>(emptyList()) }
    var message by remember { mutableStateOf<String?>(null) }
    var loading by remember { mutableStateOf(false) }
    var stars by remember { mutableIntStateOf(0) }
    var comment by remember { mutableStateOf("") }
    var reopenReason by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()

    suspend fun reload() {
        loading = true
        runCatching {
            val response = RetrofitClient.apiService.getHostelIssues()
            if (!response.isSuccessful) error(response.errorBody()?.string() ?: "Unable to load issues.")
            issues = response.body().orEmpty()
        }.onFailure { message = it.message ?: "Unable to load issues." }
        loading = false
    }
    LaunchedEffect(Unit) { reload() }

    Column(modifier.fillMaxSize().padding(16.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("My issues", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            TextButton(onClick = { scope.launch { reload() } }) { Text("Refresh") }
        }
        message?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        if (selected == null) {
            if (loading) LinearProgressIndicator(Modifier.fillMaxWidth())
            LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(issues, key = { it.id }) { issue ->
                    Card(onClick = {
                        selected = issue
                        scope.launch {
                            runCatching { RetrofitClient.apiService.getIssueTimeline(issue.id) }
                                .onSuccess { timeline = it.body().orEmpty() }
                        }
                    }, modifier = Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(14.dp)) {
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text(issue.category, fontWeight = FontWeight.Bold)
                                AssistChip(onClick = {}, label = { Text(issue.status.replace('_', ' ')) })
                            }
                            Text(issue.description, maxLines = 2, style = MaterialTheme.typography.bodyMedium)
                            Text("${issue.location} · ${issue.severity} · ${issue.createdAt.take(10)}", style = MaterialTheme.typography.bodySmall)
                            Text("ID ${issue.id}", style = MaterialTheme.typography.labelSmall)
                        }
                    }
                }
            }
            if (issues.isEmpty() && !loading) Text("No records available.")
        } else {
            val issue = selected!!
            TextButton(onClick = { selected = null; message = null }) { Text("← All issues") }
            Text(issue.category, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Text("${issue.status.replace('_', ' ')} · ${issue.severity} · ${issue.location}")
            Text(issue.description)
            issue.assignedUid?.let { Text("Assigned staff: $it") }
            issue.resolution?.let { Text("Resolution: $it") }
            Text("Status timeline", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            LazyColumn(Modifier.weight(1f, fill = false), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                items(timeline, key = { it.id }) { event ->
                    Text("${event.toStatus.replace('_', ' ')} · ${event.createdAt}${event.comment?.let { " · $it" } ?: ""}", style = MaterialTheme.typography.bodySmall)
                }
            }
            if (issue.status == "RESOLVED" || issue.status == "CLOSED") {
                Text("Resolution feedback", style = MaterialTheme.typography.titleSmall)
                com.example.ui.components.RatingStars(rating = stars, onRatingChanged = { stars = it })
                OutlinedTextField(comment, { comment = it }, label = { Text("Optional comment") }, modifier = Modifier.fillMaxWidth())
                Button(enabled = stars > 0, onClick = {
                    scope.launch {
                        runCatching { RetrofitClient.apiService.submitResolutionFeedback(issue.id, IssueFeedbackRequest(stars, comment.ifBlank { null })) }
                            .onSuccess { message = if (it.isSuccessful) "Feedback saved." else "Could not save feedback." }
                            .onFailure { message = it.message }
                    }
                }) { Text("Send feedback") }
                OutlinedTextField(reopenReason, { reopenReason = it }, label = { Text("Reason to reopen") }, modifier = Modifier.fillMaxWidth())
                OutlinedButton(enabled = reopenReason.trim().length >= 5, onClick = {
                    scope.launch {
                        runCatching { RetrofitClient.apiService.reopenIssue(issue.id, IssueReopenRequest(reopenReason.trim())) }
                            .onSuccess { if (it.isSuccessful) { message = "Issue reopened."; selected = it.body(); reload() } else message = "Could not reopen this issue." }
                            .onFailure { message = it.message }
                    }
                }) { Text("Reopen issue") }
            }
            message?.let { Text(it, color = MaterialTheme.colorScheme.primary) }
        }
    }
}

@Composable
fun StudentProfileScreen(viewModel: HydroViewModel, onLogout: () -> Unit, modifier: Modifier = Modifier) {
    val user by viewModel.currentUser.collectAsState()
    val darkMode by viewModel.isDarkMode.collectAsState()
    var contacts by remember { mutableStateOf<List<EmergencyContactResponse>>(emptyList()) }
    var events by remember { mutableStateOf<List<HostelEventResponse>>(emptyList()) }
    var lostItems by remember { mutableStateOf<List<LostFoundResponse>>(emptyList()) }
    var feedbackCategory by remember { mutableStateOf("Overall Hostel Experience") }
    var feedbackRating by remember { mutableIntStateOf(0) }
    var feedbackComment by remember { mutableStateOf("") }
    var lostKind by remember { mutableStateOf("LOST") }
    var lostCategory by remember { mutableStateOf("Other") }
    var lostTitle by remember { mutableStateOf("") }
    var lostDescription by remember { mutableStateOf("") }
    var lostLocation by remember { mutableStateOf("") }
    var lostImage by remember { mutableStateOf("") }
    var serviceMessage by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) {
        runCatching {
            val api = RetrofitClient.apiService
            val contactResponse = api.getEmergencyContacts()
            val eventResponse = api.getHostelEvents()
            val lostResponse = api.getLostFoundItems()
            if (!contactResponse.isSuccessful || !eventResponse.isSuccessful || !lostResponse.isSuccessful) throw IllegalStateException("Services are unavailable.")
            contacts = contactResponse.body().orEmpty()
            events = eventResponse.body().orEmpty()
            lostItems = lostResponse.body().orEmpty()
        }.onFailure { error = it.message }
    }
    LazyColumn(modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { Text("Profile", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold) }
        item { Text(user?.name ?: "Signed-in account") }
        item { Text(user?.email ?: "") }
        item { Text("Role: ${user?.role ?: "STUDENT"}", style = MaterialTheme.typography.bodySmall) }
        item { Text("Hostel ${user?.hostelBlock?.ifBlank { "not set" } ?: "not set"} · Room ${user?.roomNumber?.ifBlank { "not set" } ?: "not set"}") }
        item {
            Card(Modifier.fillMaxWidth()) { Row(Modifier.padding(horizontal = 14.dp, vertical = 8.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                Column { Text("Dark theme", fontWeight = FontWeight.SemiBold); Text("Appearance preference", style = MaterialTheme.typography.bodySmall) }
                Switch(checked = darkMode, onCheckedChange = { viewModel.toggleDarkMode() })
            } }
        }
        item { Text("Emergency hub", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold) }
        listOf("WARDEN", "SECURITY", "COLLEGE_EMERGENCY", "AMBULANCE", "FIRE").forEach { category ->
            val contact = contacts.firstOrNull { it.active && it.category.equals(category, ignoreCase = true) }
            item(key = "emergency-$category") {
                Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(12.dp)) {
                    Text(category.replace('_', ' '), style = MaterialTheme.typography.labelLarge)
                    if (contact == null) Text("Contact not configured", style = MaterialTheme.typography.bodyMedium)
                    else {
                        Text(contact.name, fontWeight = FontWeight.SemiBold)
                        Text(contact.phone)
                        contact.details?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                    }
                } }
            }
        }
        item { Text("Hostel events", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold) }
        if (events.isEmpty()) item { Text("No upcoming or listed events.") }
        items(events, key = { it.id }) { event ->
            Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) { Text(event.name, fontWeight = FontWeight.Bold); Text("${event.startsAt} · ${event.location}"); Text("Organized by ${event.organizer}", style = MaterialTheme.typography.bodySmall); Text(event.description) } }
        }
        item { Text("Lost & Found", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold) }
        items(lostItems, key = { it.id }) { item ->
            Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(12.dp)) { Text("${item.kind} · ${item.category} · ${item.moderationStatus}"); Text(item.title, fontWeight = FontWeight.Bold); Text("${item.location} · ${item.itemDate}"); Text(item.description) } }
        }
        item { CategorySelector("Entry type", listOf("LOST", "FOUND"), lostKind) { lostKind = it } }
        item { CategorySelector("Item category", listOf("ID", "Keys", "Phone", "Wallet", "Books", "Bag", "Electronics", "Other"), lostCategory) { lostCategory = it } }
        item { OutlinedTextField(lostTitle, { lostTitle = it }, label = { Text("Item title") }, modifier = Modifier.fillMaxWidth()) }
        item { OutlinedTextField(lostDescription, { lostDescription = it }, label = { Text("Description") }, modifier = Modifier.fillMaxWidth(), minLines = 2) }
        item { OutlinedTextField(lostLocation, { lostLocation = it }, label = { Text("Location") }, modifier = Modifier.fillMaxWidth()) }
        item { OutlinedTextField(lostImage, { lostImage = it }, label = { Text("Optional HTTPS image link") }, modifier = Modifier.fillMaxWidth()) }
        item {
            Button(enabled = lostTitle.isNotBlank() && lostDescription.trim().length >= 5 && lostLocation.isNotBlank(), onClick = {
                scope.launch {
                    runCatching {
                        val response = RetrofitClient.apiService.createLostFoundItem(
                            CreateLostFoundRequest(lostKind, lostTitle.trim(), lostDescription.trim(), lostCategory, lostImage.ifBlank { null }, lostLocation.trim(), nowUtcIso())
                        )
                        if (!response.isSuccessful) throw IllegalStateException(response.errorBody()?.string() ?: "Could not submit item.")
                        lostItems = RetrofitClient.apiService.getLostFoundItems().body().orEmpty()
                        serviceMessage = "Item submitted for administrator review."
                    }.onFailure { serviceMessage = it.message ?: "Could not submit item." }
                }
            }, modifier = Modifier.fillMaxWidth()) { Text("Submit Lost & Found item") }
        }
        item { Text("General hostel feedback", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold) }
        item { CategorySelector("Feedback category", listOf("Water", "Cleanliness", "Maintenance", "Wi-Fi", "Common Areas", "Overall Hostel Experience"), feedbackCategory) { feedbackCategory = it } }
        item { com.example.ui.components.RatingStars(rating = feedbackRating, onRatingChanged = { feedbackRating = it }) }
        item { OutlinedTextField(feedbackComment, { feedbackComment = it }, label = { Text("Optional comment") }, modifier = Modifier.fillMaxWidth()) }
        item {
            Button(enabled = feedbackRating > 0, onClick = {
                scope.launch {
                    runCatching { RetrofitClient.apiService.submitHostelFeedback(HostelFeedbackRequest(feedbackCategory, feedbackRating, feedbackComment.ifBlank { null })) }
                        .onSuccess { serviceMessage = if (it.isSuccessful) "Feedback saved." else "Could not save feedback." }
                        .onFailure { serviceMessage = it.message }
                }
            }, modifier = Modifier.fillMaxWidth()) { Text("Send feedback") }
        }
        serviceMessage?.let { item { Text(it, color = MaterialTheme.colorScheme.primary) } }
        error?.let { item { Text(it, color = MaterialTheme.colorScheme.error) } }
        item { OutlinedButton(onClick = onLogout, modifier = Modifier.fillMaxWidth()) { Text("Sign out") } }
    }
}

@Composable
private fun CategorySelector(label: String, options: List<String>, selected: String, onSelected: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Column {
        Text(label, style = MaterialTheme.typography.labelMedium)
        Box {
            OutlinedButton(onClick = { expanded = true }) { Text(selected) }
            DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                options.forEach { option -> DropdownMenuItem(text = { Text(option) }, onClick = { onSelected(option); expanded = false }) }
            }
        }
    }
}
