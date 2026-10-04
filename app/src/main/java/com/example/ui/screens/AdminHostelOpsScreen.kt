package com.example.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.example.data.api.*
import com.google.firebase.auth.FirebaseAuth
import kotlinx.coroutines.launch

@Composable
fun AdminHostelOpsScreen(onLogout: () -> Unit, modifier: Modifier = Modifier) {
    val api = remember { RetrofitClient.apiService }
    val scope = rememberCoroutineScope()
    var issues by remember { mutableStateOf(emptyList<HostelIssueResponse>()) }
    var summary by remember { mutableStateOf<IssueSummaryResponse?>(null) }
    var notices by remember { mutableStateOf(emptyList<HostelNoticeResponse>()) }
    var contacts by remember { mutableStateOf(emptyList<EmergencyContactResponse>()) }
    var events by remember { mutableStateOf(emptyList<HostelEventResponse>()) }
    var lostFound by remember { mutableStateOf(emptyList<LostFoundResponse>()) }
    var feedback by remember { mutableStateOf(emptyList<HostelFeedbackRecord>()) }
    var resolutionFeedback by remember { mutableStateOf(emptyList<IssueFeedbackResponse>()) }
    var message by remember { mutableStateOf("Loading persisted hostel operations…") }
    var showNotice by remember { mutableStateOf(false) }
    var editingNoticeId by remember { mutableStateOf<Int?>(null) }
    var noticeTitle by remember { mutableStateOf("") }
    var noticeBody by remember { mutableStateOf("") }
    var noticeCategory by remember { mutableStateOf("GENERAL") }
    var noticeExpiry by remember { mutableStateOf("") }
    var showContact by remember { mutableStateOf(false) }
    var editingContactId by remember { mutableStateOf<Int?>(null) }
    var contactName by remember { mutableStateOf("") }
    var contactPhone by remember { mutableStateOf("") }
    var contactCategory by remember { mutableStateOf("WARDEN") }
    var showEvent by remember { mutableStateOf(false) }
    var editingEventId by remember { mutableStateOf<Int?>(null) }
    var eventName by remember { mutableStateOf("") }
    var eventDate by remember { mutableStateOf("") }
    var eventLocation by remember { mutableStateOf("") }
    var eventDescription by remember { mutableStateOf("") }
    var eventOrganizer by remember { mutableStateOf("") }

    fun reload() = scope.launch {
        message = "Loading persisted hostel operations…"
        runCatching {
            val i = api.getHostelIssues(); val s = api.getIssueSummary(); val n = api.getHostelNotices()
            val c = api.getEmergencyContacts(); val e = api.getHostelEvents(); val l = api.getLostFoundItems()
            val f = api.getAdminFeedback(); val rf = api.getAdminResolutionFeedback()
            if (!i.isSuccessful || !s.isSuccessful || !n.isSuccessful || !c.isSuccessful || !e.isSuccessful || !l.isSuccessful || !f.isSuccessful || !rf.isSuccessful)
                error("Admin API returned an error. Confirm this account has the ADMIN Firebase claim and retry.")
            issues = i.body().orEmpty(); summary = s.body(); notices = n.body().orEmpty()
            contacts = c.body().orEmpty(); events = e.body().orEmpty(); lostFound = l.body().orEmpty()
            feedback = f.body().orEmpty(); resolutionFeedback = rf.body().orEmpty()
            message = "Data loaded from the configured backend."
        }.onFailure { message = it.message ?: "Could not load backend data." }
    }
    LaunchedEffect(Unit) { reload() }

    if (showNotice) AlertDialog(
        onDismissRequest = { showNotice = false; editingNoticeId = null }, title = { Text(if (editingNoticeId == null) "New notice" else "Edit notice") },
        text = { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(noticeTitle, { noticeTitle = it }, label = { Text("Title") })
            OutlinedTextField(noticeBody, { noticeBody = it }, label = { Text("Message") })
            OutlinedTextField(noticeCategory, { noticeCategory = it.uppercase() }, label = { Text("Category: GENERAL / MAINTENANCE / WATER / EMERGENCY / EVENT") })
            OutlinedTextField(noticeExpiry, { noticeExpiry = it }, label = { Text("Optional expiry (ISO 8601)") })
        } }, confirmButton = { TextButton(onClick = { scope.launch {
            runCatching {
                val request = NoticeCreateRequest(noticeTitle, noticeBody, noticeCategory, "NORMAL", noticeExpiry.ifBlank { null })
                val response = editingNoticeId?.let { api.updateNotice(it, request) } ?: api.createNotice(request)
                response
                .also { if (!it.isSuccessful) error("Notice was not saved (${it.code()}).") } }
                .onSuccess { showNotice = false; editingNoticeId = null; noticeTitle = ""; noticeBody = ""; reload() }
                .onFailure { message = it.message ?: "Notice could not be saved." }
        } }) { Text(if (editingNoticeId == null) "Publish" else "Save") } }, dismissButton = { TextButton(onClick = { showNotice = false; editingNoticeId = null }) { Text("Cancel") } }
    )

    if (showContact) AlertDialog(
        onDismissRequest = { showContact = false; editingContactId = null }, title = { Text(if (editingContactId == null) "Add verified emergency contact" else "Edit verified emergency contact") },
        text = { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(contactCategory, { contactCategory = it.uppercase() }, label = { Text("WARDEN / SECURITY / COLLEGE_EMERGENCY / AMBULANCE / FIRE") })
            OutlinedTextField(contactName, { contactName = it }, label = { Text("Contact name") })
            OutlinedTextField(contactPhone, { contactPhone = it }, label = { Text("Verified phone") })
        } }, confirmButton = { TextButton(onClick = { scope.launch {
            runCatching {
                val request = EmergencyContactCreateRequest(contactCategory, contactName, contactPhone)
                val response = editingContactId?.let { api.updateEmergencyContact(it, request) } ?: api.createEmergencyContact(request)
                response
                .also { if (!it.isSuccessful) error("Contact was not saved (${it.code()}).") } }
                .onSuccess { showContact = false; editingContactId = null; contactName = ""; contactPhone = ""; reload() }
                .onFailure { message = it.message ?: "Contact could not be saved." }
        } }) { Text(if (editingContactId == null) "Save verified contact" else "Update contact") } }, dismissButton = { TextButton(onClick = { showContact = false; editingContactId = null }) { Text("Cancel") } }
    )

    if (showEvent) AlertDialog(
        onDismissRequest = { showEvent = false; editingEventId = null }, title = { Text(if (editingEventId == null) "New hostel event" else "Edit hostel event") },
        text = { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(eventName, { eventName = it }, label = { Text("Event name") })
            OutlinedTextField(eventDate, { eventDate = it }, label = { Text("Start time (ISO 8601, e.g. 2026-10-05T10:00:00Z)") })
            OutlinedTextField(eventLocation, { eventLocation = it }, label = { Text("Location") })
            OutlinedTextField(eventDescription, { eventDescription = it }, label = { Text("Description") })
            OutlinedTextField(eventOrganizer, { eventOrganizer = it }, label = { Text("Organizer") })
        } }, confirmButton = { TextButton(onClick = { scope.launch {
            runCatching {
                val request = EventCreateRequest(eventName, eventDate, eventLocation, eventDescription, eventOrganizer)
                val response = editingEventId?.let { api.updateHostelEvent(it, request) } ?: api.createHostelEvent(request)
                response.also { if (!it.isSuccessful) error("Event was not saved (${it.code()}).") }
            }.onSuccess { showEvent = false; editingEventId = null; eventName = ""; reload() }
                .onFailure { message = it.message ?: "Event could not be saved." }
        } }) { Text(if (editingEventId == null) "Create event" else "Save event") } }, dismissButton = { TextButton(onClick = { showEvent = false; editingEventId = null }) { Text("Cancel") } }
    )

    LazyColumn(modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("Hostel operations", style = MaterialTheme.typography.headlineSmall)
            Row {
                TextButton(onClick = { reload() }) { Text("Refresh") }
                TextButton(onClick = onLogout) { Text("Sign out") }
            }
        } }
        item { Text(message, style = MaterialTheme.typography.bodySmall) }
        summary?.let { stats -> item {
            Card { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("ISSUE SUMMARY · ${stats.total} total", style = MaterialTheme.typography.titleMedium)
                Text("Open / awaiting action: ${stats.byStatus.filterKeys { it !in setOf("RESOLVED", "CLOSED") }.values.sum()}")
                Text("High priority: ${issues.count { (it.severity == "HIGH" || it.severity == "URGENT") && it.status !in setOf("RESOLVED", "CLOSED") }}")
            Text("Acknowledged: ${stats.byStatus["ACKNOWLEDGED"] ?: 0} · Assigned: ${stats.byStatus["ASSIGNED"] ?: 0}")
            Text("In progress: ${stats.byStatus["IN_PROGRESS"] ?: 0} · Resolved: ${stats.byStatus["RESOLVED"] ?: 0}")
            Text("Reopened: ${stats.byStatus["REOPENED"] ?: 0} · Closed: ${stats.byStatus["CLOSED"] ?: 0}")
            Text("By status: ${stats.byStatus.entries.joinToString { "${it.key} ${it.value}" }}")
                Text("By category: ${stats.byCategory.entries.joinToString { "${it.key} ${it.value}" }}")
            } }
        } }
        item { Text("ISSUES", style = MaterialTheme.typography.titleLarge) }
        if (issues.isEmpty()) item { Text("No persisted issues have been reported.") }
        items(issues, key = { it.id }) { issue ->
            Card { Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("${issue.category} · ${issue.severity} · ${issue.status}", style = MaterialTheme.typography.titleMedium)
                Text("${issue.location}\n${issue.description}")
                Text("Reporter ${issue.reporterUid} · ${issue.createdAt}", style = MaterialTheme.typography.bodySmall)
                issue.resolution?.let { Text("Resolution: $it") }
                val next = when (issue.status) {
                    "SUBMITTED" -> "ACKNOWLEDGED"; "ACKNOWLEDGED" -> "ASSIGNED"; "ASSIGNED" -> "IN_PROGRESS"
                    "IN_PROGRESS" -> "RESOLVED"; "RESOLVED" -> "CLOSED"; "REOPENED" -> "ACKNOWLEDGED"; else -> null
                }
                if (next != null) Button(onClick = { scope.launch {
                    val assignee = if (next == "ASSIGNED") FirebaseAuth.getInstance().currentUser?.uid else null
                    if (next == "ASSIGNED" && assignee == null) {
                        message = "Could not verify the signed-in administrator for assignment."
                        return@launch
                    }
                    val resolution = if (next == "RESOLVED") "Resolved by hostel administration." else null
                    val response = api.updateIssueStatus(issue.id, IssueStatusRequest(next, "Status updated by administration", assignee, resolution))
                    if (!response.isSuccessful) message = "Could not update ${issue.id}: ${response.code()}" else reload()
                } }) { Text(if (next == "ASSIGNED") "Assign to admin" else "Move to $next") }
            } }
        }
        item { Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("NOTICES", style = MaterialTheme.typography.titleLarge)
            TextButton(onClick = { editingNoticeId = null; noticeTitle = ""; noticeBody = ""; noticeCategory = "GENERAL"; noticeExpiry = ""; showNotice = true }) { Text("Add") }
        } }
        if (notices.isEmpty()) item { Text("No active notices.") }
        items(notices, key = { "notice-${it.id}" }) { item ->
            Card { Row(Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Column(Modifier.weight(1f)) { Text("${item.title} · ${item.priority}", style = MaterialTheme.typography.titleMedium); Text("${item.category} · ${item.body}"); Text("Posted ${item.createdAt} · Expires ${item.expiresAt ?: "No expiry"}", style = MaterialTheme.typography.bodySmall) }
                TextButton(onClick = { editingNoticeId = item.id; noticeTitle = item.title; noticeBody = item.body; noticeCategory = item.category; noticeExpiry = item.expiresAt.orEmpty(); showNotice = true }) { Text("Edit") }
                TextButton(onClick = { scope.launch { api.deleteNotice(item.id); reload() } }) { Text("Delete") }
            } }
        }
        item { Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("EMERGENCY CONTACTS", style = MaterialTheme.typography.titleLarge)
            TextButton(onClick = { editingContactId = null; contactName = ""; contactPhone = ""; contactCategory = "WARDEN"; showContact = true }) { Text("Add") }
        } }
        if (contacts.isEmpty()) item { Text("No verified emergency contacts configured.") }
        items(contacts, key = { "contact-${it.id}" }) { item ->
            Card { Row(Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("${item.category}: ${item.name} · ${item.phone}")
                TextButton(onClick = { editingContactId = item.id; contactName = item.name; contactPhone = item.phone; contactCategory = item.category; showContact = true }) { Text("Edit") }
                TextButton(onClick = { scope.launch { api.deleteEmergencyContact(item.id); reload() } }) { Text("Deactivate") }
            } }
        }
        item { Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("EVENTS", style = MaterialTheme.typography.titleLarge)
            TextButton(onClick = { editingEventId = null; eventName = ""; eventDate = ""; eventLocation = ""; eventDescription = ""; eventOrganizer = ""; showEvent = true }) { Text("Add") }
        } }
        if (events.isEmpty()) item { Text("No upcoming events configured.") }
        items(events, key = { "event-${it.id}" }) { item ->
            Card { Row(Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("${item.name} · ${item.startsAt}\n${item.location} · ${item.organizer}", Modifier.weight(1f))
                TextButton(onClick = { editingEventId = item.id; eventName = item.name; eventDate = item.startsAt; eventLocation = item.location; eventDescription = item.description; eventOrganizer = item.organizer; showEvent = true }) { Text("Edit") }
                TextButton(onClick = { scope.launch { api.deleteHostelEvent(item.id); reload() } }) { Text("Delete") }
            } }
        }
        item { Text("LOST & FOUND MODERATION", style = MaterialTheme.typography.titleLarge) }
        if (lostFound.isEmpty()) item { Text("No submissions awaiting moderation.") }
        items(lostFound, key = { "lost-${it.id}" }) { item ->
            Card { Column(Modifier.padding(12.dp)) {
                Text("${item.kind}: ${item.title} · ${item.category}")
                Text("${item.location} · ${item.description}")
                Row { listOf("APPROVED", "REJECTED").forEach { status -> TextButton(onClick = { scope.launch {
                    val response = api.moderateLostFoundItem(item.id, mapOf("moderation_status" to status))
                    if (response.isSuccessful) reload() else message = "Moderation failed (${response.code()})."
                } }) { Text(status) } } }
            } }
        }
        item { Text("HOSTEL FEEDBACK", style = MaterialTheme.typography.titleLarge) }
        if (feedback.isEmpty()) item { Text("No feedback has been submitted.") }
        items(feedback, key = { "feedback-${it.id}" }) { Text("${it.category} · ${it.rating}/5 · ${it.createdAt}\n${it.comment.orEmpty()}") }
        item { Text("ISSUE RESOLUTION RATINGS", style = MaterialTheme.typography.titleLarge) }
        if (resolutionFeedback.isEmpty()) item { Text("No issue resolutions have been rated.") }
        items(resolutionFeedback, key = { "resolution-${it.id}" }) {
            Text("Issue ${it.issueId} · ${it.stars}/5 · ${it.createdAt}\n${it.comment.orEmpty()}")
        }
    }
}
