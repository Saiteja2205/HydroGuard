package com.example.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.outlined.StarOutline
import androidx.compose.material3.IconButton
import androidx.compose.ui.graphics.Shape
import com.example.ui.theme.HydroGuardColors
import com.example.ui.theme.HydroGuardDimensions
import com.example.ui.theme.HydroGuardShapes

enum class StatusTone { HEALTHY, ATTENTION, CRITICAL, AI, NEUTRAL, DISCONNECTED }

@Composable
fun HydroCard(
    modifier: Modifier = Modifier,
    shape: Shape = HydroGuardShapes.card,
    containerColor: Color = MaterialTheme.colorScheme.surface,
    content: @Composable ColumnScope.() -> Unit
) {
    Card(
        modifier = modifier,
        shape = shape,
        colors = CardDefaults.cardColors(containerColor = containerColor),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
        content = content
    )
}

@Composable
fun SectionHeader(
    title: String,
    modifier: Modifier = Modifier,
    subtitle: String? = null,
    trailing: (@Composable () -> Unit)? = null
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            subtitle?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
        trailing?.invoke()
    }
}

@Composable
fun MetricCard(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
    unit: String? = null,
    note: String? = null,
    icon: ImageVector? = null,
    tone: StatusTone = StatusTone.NEUTRAL,
    badge: String? = null
) {
    val accent = tone.color()
    HydroCard(modifier = modifier) {
        Column(
            Modifier.fillMaxWidth().padding(HydroGuardDimensions.metricCardPadding),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                icon?.let {
                    Box(
                        Modifier.size(32.dp).clip(RoundedCornerShape(10.dp)).background(accent.copy(alpha = 0.10f)),
                        contentAlignment = Alignment.Center
                    ) { Icon(it, contentDescription = null, tint = accent, modifier = Modifier.size(18.dp)) }
                }
                Text(
                    label,
                    modifier = Modifier.weight(1f),
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    softWrap = false
                )
                badge?.let { StatusChip(it, tone = if (it.contains("EXPERIMENT", true)) StatusTone.AI else tone) }
            }
            Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(value, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurface)
                unit?.takeIf { it.isNotBlank() }?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(bottom = 3.dp)) }
            }
            note?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
    }
}

@Composable
fun StatusChip(label: String, modifier: Modifier = Modifier, tone: StatusTone = StatusTone.NEUTRAL) {
    val accent = tone.color()
    Row(
        modifier = modifier
            .clip(CircleShape)
            .background(tone.container())
            .padding(horizontal = 10.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        Box(Modifier.size(6.dp).clip(CircleShape).background(accent))
        Text(label, style = MaterialTheme.typography.labelSmall, color = accent, fontWeight = FontWeight.SemiBold, maxLines = 1)
    }
}

@Composable
fun ConnectionChip(connected: Boolean?, modifier: Modifier = Modifier) {
    val text = when (connected) {
        true -> "Server connected"
        false -> "Server unavailable"
        null -> "Connecting to server"
    }
    StatusChip(
        label = text,
        modifier = modifier,
        tone = when (connected) {
            true -> StatusTone.HEALTHY
            false -> StatusTone.DISCONNECTED
            null -> StatusTone.NEUTRAL
        }
    )
}

@Composable
fun ApplicationIndexSummary(
    index: Int?,
    category: String?,
    modifier: Modifier = Modifier
) {
    val tone = when (category?.uppercase()) {
        "EXCELLENT", "GOOD" -> StatusTone.HEALTHY
        "MODERATE" -> StatusTone.ATTENTION
        "POOR", "CRITICAL" -> StatusTone.CRITICAL
        else -> StatusTone.DISCONNECTED
    }
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text("Application Water Quality Index", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(index?.toString() ?: "Unavailable", style = MaterialTheme.typography.displaySmall, fontWeight = FontWeight.Bold)
            StatusChip(category ?: "UNAVAILABLE", tone = tone, modifier = Modifier.padding(bottom = 5.dp))
        }
        Text("Application-specific monitoring indicator", style = MaterialTheme.typography.bodyMedium)
        Text(
            "Uses pH, TDS, turbidity, and temperature. Optical colour is shown separately and is not included in this score.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            "This application-specific index is not a drinking-water certification.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

@Composable
fun EmptyState(
    title: String,
    detail: String? = null,
    modifier: Modifier = Modifier,
    icon: ImageVector = Icons.Default.Info,
    actionLabel: String? = null,
    onAction: (() -> Unit)? = null
) {
    HydroCard(modifier = modifier.fillMaxWidth()) {
        Column(
            Modifier.fillMaxWidth().padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Box(Modifier.size(44.dp).clip(CircleShape).background(MaterialTheme.colorScheme.primaryContainer), contentAlignment = Alignment.Center) {
                Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            }
            Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
            detail?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            if (actionLabel != null && onAction != null) SecondaryButton(actionLabel, onAction = onAction)
        }
    }
}

@Composable
fun ErrorState(
    title: String,
    detail: String,
    modifier: Modifier = Modifier,
    actionLabel: String = "Retry",
    onAction: () -> Unit
) {
    HydroCard(modifier = modifier.fillMaxWidth(), containerColor = MaterialTheme.colorScheme.errorContainer) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.Warning, contentDescription = null, tint = MaterialTheme.colorScheme.error)
                Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
            }
            Text(detail, style = MaterialTheme.typography.bodySmall)
            SecondaryButton(actionLabel, onAction = onAction)
        }
    }
}

@Composable
fun LoadingState(label: String = "Loading HydroGuard data…", modifier: Modifier = Modifier) {
    Row(
        modifier = modifier.fillMaxWidth().padding(vertical = 12.dp),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically
    ) {
        CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
        Spacer(Modifier.width(10.dp))
        Text(label, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
fun PrimaryButton(text: String, onAction: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    Button(
        onClick = onAction,
        enabled = enabled,
        modifier = modifier.fillMaxWidth().height(HydroGuardDimensions.buttonHeight),
        shape = HydroGuardShapes.button
    ) { Text(text, style = MaterialTheme.typography.labelLarge) }
}

@Composable
fun SecondaryButton(text: String, onAction: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    OutlinedButton(
        onClick = onAction,
        enabled = enabled,
        modifier = modifier.height(HydroGuardDimensions.buttonHeight),
        shape = HydroGuardShapes.button
    ) { Text(text, style = MaterialTheme.typography.labelLarge) }
}

@Composable
fun RatingStars(rating: Int, onRatingChanged: (Int) -> Unit, modifier: Modifier = Modifier) {
    Row(modifier = modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        (1..5).forEach { value ->
            IconButton(onClick = { onRatingChanged(value) }, modifier = Modifier.size(48.dp)) {
                Icon(
                    imageVector = if (value <= rating) Icons.Filled.Star else Icons.Outlined.StarOutline,
                    contentDescription = "$value star${if (value == 1) "" else "s"}",
                    tint = if (value <= rating) HydroGuardColors.experimental else MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@Composable
private fun StatusTone.color(): Color = when (this) {
    StatusTone.HEALTHY -> HydroGuardColors.healthy
    StatusTone.ATTENTION -> HydroGuardColors.warning
    StatusTone.CRITICAL -> HydroGuardColors.critical
    StatusTone.AI -> HydroGuardColors.experimental
    StatusTone.NEUTRAL -> MaterialTheme.colorScheme.primary
    StatusTone.DISCONNECTED -> HydroGuardColors.disconnected
}

@Composable
private fun StatusTone.container(): Color = when (this) {
    StatusTone.HEALTHY -> HydroGuardColors.healthyTint
    StatusTone.ATTENTION -> HydroGuardColors.warningTint
    StatusTone.CRITICAL -> HydroGuardColors.criticalTint
    StatusTone.AI -> HydroGuardColors.experimentalTint
    StatusTone.NEUTRAL -> MaterialTheme.colorScheme.primaryContainer
    StatusTone.DISCONNECTED -> HydroGuardColors.disconnectedTint
}
