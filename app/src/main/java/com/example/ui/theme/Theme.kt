package com.example.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val LightColorScheme = lightColorScheme(
    primary = CobaltBlue,
    onPrimary = CoolWhite,
    primaryContainer = Color(0xFFDBEAFE),
    onPrimaryContainer = CobaltBlueDark,
    secondary = CeruleanBlueBright,
    onSecondary = CoolWhite,
    secondaryContainer = Color(0xFFE0F2FE),
    onSecondaryContainer = Color(0xFF0369A1),
    tertiary = SmartTeal,
    onTertiary = CoolWhite,
    tertiaryContainer = SmartTealSoft,
    onTertiaryContainer = Color(0xFF115E59),
    background = CoolWhiteSubtle,
    onBackground = SlateBlueDark,
    surface = CoolWhite,
    onSurface = SlateBlueDark,
    surfaceVariant = CoolWhiteContainer,
    onSurfaceVariant = SlateBlueSubtle,
    outline = SlateBlueLight,
    outlineVariant = CoolWhiteBorder,
    error = CriticalRed,
    onError = CoolWhite,
    errorContainer = CriticalRedSoft,
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
        content = content
    )
}
