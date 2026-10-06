package com.example.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.material3.Shapes
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val LightColorScheme = lightColorScheme(
    primary = HydroGuardColors.primary,
    onPrimary = HydroGuardColors.surface,
    primaryContainer = HydroGuardColors.primaryTint,
    onPrimaryContainer = HydroGuardColors.deepText,
    secondary = HydroGuardColors.secondary,
    onSecondary = HydroGuardColors.surface,
    secondaryContainer = Color(0xFFE8EEF5),
    onSecondaryContainer = HydroGuardColors.deepText,
    tertiary = HydroGuardColors.experimental,
    onTertiary = CoolWhite,
    tertiaryContainer = HydroGuardColors.experimentalTint,
    onTertiaryContainer = HydroGuardColors.experimental,
    background = HydroGuardColors.background,
    onBackground = HydroGuardColors.deepText,
    surface = HydroGuardColors.surface,
    onSurface = HydroGuardColors.deepText,
    surfaceVariant = CoolWhiteContainer,
    onSurfaceVariant = HydroGuardColors.secondary,
    outline = Color(0xFF94A3B8),
    outlineVariant = HydroGuardColors.border,
    error = HydroGuardColors.critical,
    onError = CoolWhite,
    errorContainer = HydroGuardColors.criticalTint,
    onErrorContainer = Color(0xFF991B1B)
)

private val DarkColorScheme = darkColorScheme(
    primary = CeruleanBlueLight,
    onPrimary = SlateBlueDark,
    primaryContainer = Color(0xFF1E3A8A),
    onPrimaryContainer = Color(0xFFBFDBFE),
    secondary = SmartTealLight,
    onSecondary = SlateBlueDark,
    secondaryContainer = Color(0xFF134E4A),
    onSecondaryContainer = Color(0xFF99F6E4),
    tertiary = CobaltBlueLight,
    onTertiary = CoolWhite,
    tertiaryContainer = Color(0xFF1E293B),
    onTertiaryContainer = Color(0xFF93C5FD),
    background = DarkBackground,
    onBackground = TextPrimaryLight,
    surface = DarkSurface,
    onSurface = TextPrimaryLight,
    surfaceVariant = Color(0xFF334155),
    onSurfaceVariant = TextSecondaryLight,
    outline = SlateBlueSubtle,
    outlineVariant = SlateBlueBorder,
    error = CriticalRed,
    onError = CoolWhite,
    errorContainer = Color(0xFF7F1D1D),
    onErrorContainer = Color(0xFFFECACA)
)

@Composable
fun HydroGuardTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {
    val colorScheme = if (darkTheme) DarkColorScheme else LightColorScheme

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        shapes = Shapes(
            extraSmall = HydroGuardShapes.small,
            small = HydroGuardShapes.small,
            medium = HydroGuardShapes.medium,
            large = HydroGuardShapes.card,
            extraLarge = HydroGuardShapes.large
        ),
        content = content
    )
}
