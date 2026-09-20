package com.example.ui.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.ui.components.GlassCard
import com.example.ui.theme.*
import com.example.ui.viewmodel.HydroViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FeedbackScreen(
    viewModel: HydroViewModel,
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    val isDark = isSystemInDarkTheme()
    val currentUser by viewModel.currentUser.collectAsState()

    var odorLevel by remember { mutableIntStateOf(1) } // 1 (None) to 5 (Severe)
    var clarityRating by remember { mutableIntStateOf(5) } // 1 (Turbid) to 5 (Crystal Clear)
    var scalingSeverity by remember { mutableIntStateOf(1) } // 1 (None) to 5 (Heavy Limescale)
    var comments by remember { mutableStateOf("") }
    var selectedCategory by remember { mutableStateOf("HARDNESS") } // "HARDNESS", "DISCOLORATION", "ODOR", "TASTE", "PRESSURE"

    var showSuccessDialog by remember { mutableStateOf(false) }

    val backgroundBrush = if (isDark) DarkMeshBackground else LightMeshBackground

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(
                            text = "Report Observation",
                            fontSize = 19.sp,
                            fontWeight = FontWeight.Black,
                            color = CobaltBlue
                        )
                        Text(
                            text = "Hostel Infrastructure Feedback Desk",
                            style = MaterialTheme.typography.labelSmall,
                            color = SlateBlueSubtle
                        )
                    }
                },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testTag("feedback_back_btn")
                    ) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "Back",
                            tint = CobaltBlue
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
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Smart Infrastructure Advisory Banner
            GlassCard(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(20.dp),
                isDark = isDark,
                borderGlow = CeruleanBlueBright.copy(alpha = 0.3f)
            ) {
                Row(
                    modifier = Modifier
                        .background(CeruleanBlueBright.copy(alpha = if (isDark) 0.12f else 0.06f))
                        .padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(
                        modifier = Modifier
                            .size(38.dp)
                            .clip(CircleShape)
                            .background(CeruleanBlueBright.copy(alpha = 0.15f)),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            imageVector = Icons.Default.Info,
                            contentDescription = "Info",
                            tint = CeruleanBlueBright,
                            modifier = Modifier.size(22.dp)
                        )
                    }
                    Spacer(modifier = Modifier.width(12.dp))
                    Text(
                        text = "Your observations directly assist hostel maintenance teams in identifying limescale risk, plumbing blockages, and pipe corrosion across blocks.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurface,
                        lineHeight = 16.sp
                    )
                }
            }

            // Primary Feedback Form Card
            GlassCard(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(24.dp),
                isDark = isDark
            ) {
                Column(modifier = Modifier.padding(20.dp)) {
                    Text(
                        text = "OBSERVATION CATEGORY",
                        style = MaterialTheme.typography.labelSmall,
                        color = CeruleanBlueBright
                    )
                    Spacer(modifier = Modifier.height(10.dp))

                    // Issue Category Selection Chips
                    val categories = listOf(
                        "HARDNESS" to "Hardwater / Scaling",
                        "DISCOLORATION" to "Discoloration",
                        "ODOR" to "Unusual Odor",
                        "TASTE" to "Metallic / Salty Taste",
                        "PRESSURE" to "Low Flow / Pressure"
                    )

                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        categories.forEach { (catKey, catLabel) ->
                            val isSelected = selectedCategory == catKey
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(12.dp))
                                    .background(
                                        if (isSelected) CobaltBlue.copy(alpha = if (isDark) 0.25f else 0.1f)
                                        else Color.Transparent
                                    )
                                    .border(
                                        width = 1.dp,
                                        color = if (isSelected) CobaltBlue else if (isDark) GlassBorderDark else GlassBorderLight,
                                        shape = RoundedCornerShape(12.dp)
                                    )
                                    .clickable { selectedCategory = catKey }
                                    .padding(horizontal = 14.dp, vertical = 10.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text(
                                    text = catLabel,
                                    fontSize = 13.sp,
                                    fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium,
                                    color = if (isSelected) CobaltBlue else MaterialTheme.colorScheme.onSurface
                                )
                                RadioButton(
                                    selected = isSelected,
                                    onClick = { selectedCategory = catKey },
                                    colors = RadioButtonDefaults.colors(selectedColor = CobaltBlue)
                                )
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(20.dp))
                    HorizontalDivider(color = if (isDark) GlassBorderDark else GlassBorderLight)
                    Spacer(modifier = Modifier.height(20.dp))

                    // Clarity Rating (1 to 5)
                    RatingCriteriaRow(
                        title = "Visual Clarity Rating",
                        subtitle = "1 = Very Turbid/Murky, 5 = Crystal Clear",
                        rating = clarityRating,
                        onRatingChanged = { clarityRating = it }
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    // Odor Intensity (1 to 5)
                    RatingCriteriaRow(
                        title = "Odor Intensity",
                        subtitle = "1 = Zero Odor, 5 = Strong Sulfur/Chlorine",
                        rating = odorLevel,
                        onRatingChanged = { odorLevel = it }
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    // Scaling / Hardwater Severity (1 to 5)
                    RatingCriteriaRow(
                        title = "Limescale & Hardwater Buildup",
                        subtitle = "1 = Clean Taps, 5 = Heavy White Mineral Encrustation",
                        rating = scalingSeverity,
                        onRatingChanged = { scalingSeverity = it }
                    )

                    Spacer(modifier = Modifier.height(20.dp))
                    HorizontalDivider(color = if (isDark) GlassBorderDark else GlassBorderLight)
                    Spacer(modifier = Modifier.height(20.dp))

                    // Comments Text Field
                    Text(
                        text = "ADDITIONAL OBSERVATIONS",
                        style = MaterialTheme.typography.labelSmall,
                        color = CeruleanBlueBright
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    OutlinedTextField(
                        value = comments,
                        onValueChange = { comments = it },
                        placeholder = { Text("e.g. White residue observed on shower fixtures after heating...") },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(110.dp)
                            .testTag("feedback_comments_input"),
                        shape = RoundedCornerShape(14.dp),
                        maxLines = 4
                    )

                    Spacer(modifier = Modifier.height(24.dp))

                    // Submit Button
                    Button(
                        onClick = {
                            val categoryLabel = when (selectedCategory) {
                                "HARDNESS" -> "Hardwater & Scaling"
                                "DISCOLORATION" -> "Discoloration"
                                "ODOR" -> "Unusual Odor"
                                "TASTE" -> "Metallic / Salty Taste"
                                else -> "Low Pressure"
                            }
                            val detailedDescription = buildString {
                                append(if (comments.isNotBlank()) comments else "Resident reported $categoryLabel observation.")
                                append(" (Clarity: $clarityRating/5, Odor: $odorLevel/5, Scaling: $scalingSeverity/5)")
                            }
                            viewModel.submitWaterFeedback(
                                rating = clarityRating,
                                issueType = categoryLabel,
                                description = detailedDescription,
                                block = currentUser?.hostelBlock ?: "A",
                                room = currentUser?.roomNumber ?: "304",
                                imagePath = null
                            )
                            showSuccessDialog = true
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(52.dp)
                            .shadow(8.dp, RoundedCornerShape(14.dp), ambientColor = Color(0x330047AB), spotColor = Color(0x660047AB))
                            .testTag("submit_feedback_button"),
                        shape = RoundedCornerShape(14.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = CobaltBlue)
                    ) {
                        Icon(Icons.Default.Send, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("Transmit Observation Report", fontWeight = FontWeight.Bold, fontSize = 14.sp)
                    }
                }
            }
        }
    }

    if (showSuccessDialog) {
        AlertDialog(
            onDismissRequest = {
                showSuccessDialog = false
                onNavigateBack()
            },
            icon = {
                Icon(
                    Icons.Default.CheckCircle,
                    contentDescription = "Success",
                    tint = SafeGreen,
                    modifier = Modifier.size(48.dp)
                )
            },
            title = {
                Text(
                    text = "Observation Logged Successfully",
                    fontWeight = FontWeight.ExtraBold,
                    color = MaterialTheme.colorScheme.onSurface
                )
            },
            text = {
                Text(
                    text = "Your water condition feedback has been recorded. Facility administration and maintenance teams will review your observation for localized filtration and scaling maintenance.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = SlateBlueSubtle
                )
            },
            confirmButton = {
                Button(
                    onClick = {
                        showSuccessDialog = false
                        onNavigateBack()
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = CobaltBlue),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Text("Return to Dashboard", fontWeight = FontWeight.Bold)
                }
            },
            shape = RoundedCornerShape(22.dp),
            containerColor = if (isDark) GlassSurfaceDark else CoolWhite
        )
    }
}

@Composable
fun RatingCriteriaRow(
    title: String,
    subtitle: String,
    rating: Int,
    onRatingChanged: (Int) -> Unit
) {
    Column {
        Text(
            text = title,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onSurface
        )
        Text(
            text = subtitle,
            style = MaterialTheme.typography.bodySmall,
            color = SlateBlueSubtle
        )
        Spacer(modifier = Modifier.height(8.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            (1..5).forEach { star ->
                val isSelected = star <= rating
                Box(
                    modifier = Modifier
                        .size(42.dp)
                        .clip(RoundedCornerShape(10.dp))
                        .background(
                            if (isSelected) CobaltBlue.copy(alpha = 0.15f)
                            else Color.LightGray.copy(alpha = 0.15f)
                        )
                        .border(
                            1.dp,
                            if (isSelected) CobaltBlue else Color.Transparent,
                            RoundedCornerShape(10.dp)
                        )
                        .clickable { onRatingChanged(star) },
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = "$star",
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Black,
                        color = if (isSelected) CobaltBlue else SlateBlueSubtle
                    )
                }
            }
        }
    }
}
