package com.example.ui.theme

import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color

// ==========================================
// HYDROGUARD SMART INFRASTRUCTURE PALETTE
// ==========================================

// Primary Blue Family
val CobaltBlue = Color(0xFF0047AB)       // Deep Cobalt Blue
val CobaltBlueDark = Color(0xFF1E3A8A)   // Rich Navy Cobalt
val CobaltBlueLight = Color(0xFF2563EB)  // Vibrant Cobalt Highlight

// Cerulean Blue Family
val CeruleanBlue = Color(0xFF007BA7)     // Classic Cerulean
val CeruleanBlueBright = Color(0xFF0284C7) // Bright Cerulean
val CeruleanBlueLight = Color(0xFF38BDF8) // Soft Cerulean

// Teal Family
val SmartTeal = Color(0xFF0D9488)        // Infrastructure Teal
val SmartTealLight = Color(0xFF14B8A6)   // Vibrant Cyan/Teal
val SmartTealSoft = Color(0xFFCCFBF1)    // Soft Tint Teal

// Slate Blue Family
val SlateBlueDark = Color(0xFF0F172A)    // Dark Base Slate-900
val SlateBlueMedium = Color(0xFF1E293B)  // Card Slate-800
val SlateBlueBorder = Color(0xFF334155)  // Border Slate-700
val SlateBlueSubtle = Color(0xFF64748B)  // Slate-500
val SlateBlueLight = Color(0xFF94A3B8)   // Muted Slate-400

// Cool White & Light Backgrounds
val CoolWhite = Color(0xFFFFFFFF)        // Pure White
val CoolWhiteSubtle = Color(0xFFF8FAFC)  // Slate-50 Base
val CoolWhiteContainer = Color(0xFFF1F5F9)// Slate-100 Container
val CoolWhiteBorder = Color(0xFFE2E8F0)   // Slate-200 Border

// Status Indicators
val SafeGreen = Color(0xFF10B981)        // Emerald Green (Optimal)
val SafeGreenSoft = Color(0xFFD1FAE5)    // Soft Green Pill
val WarningAmber = Color(0xFFF59E0B)     // Amber (Inspection Needed)
val WarningAmberSoft = Color(0xFFFEF3C7) // Soft Amber Pill
val CriticalRed = Color(0xFFEF4444)      // Coral Red (Critical Breach)
val CriticalRedSoft = Color(0xFFFEE2E2)  // Soft Red Pill
val InfoLightBlue = Color(0xFF0284C7)    // Cerulean Info

// Backward-compatibility aliases for existing references
val PrimaryBlue = CobaltBlue
val SecondaryTeal = CeruleanBlueBright
val BackgroundOffWhite = CoolWhiteSubtle
val SurfaceWhite = CoolWhite
val TextPrimaryDark = SlateBlueDark
val TextSecondaryDark = SlateBlueSubtle

// Sleek / Advisory Accent Tokens
val SleekNavPill = Color(0xFFE0F2FE)
val SleekNavText = CobaltBlueDark
val SleekForecastBg = Color(0xFFF0F9FF)
val SleekForecastTitle = CeruleanBlue
val SleekForecastText = SlateBlueDark

// Dark Mode Tokens
val DarkPrimary = CeruleanBlueLight
val DarkSecondary = SmartTealLight
val DarkBackground = Color(0xFF0B1120)
val DarkSurface = Color(0xFF1E293B)
val TextPrimaryLight = Color(0xFFF8FAFC)
val TextSecondaryLight = Color(0xFF94A3B8)

// ==========================================
// GLASSMORPHISM GRADIENTS & SURFACES
// ==========================================

// Light Mode Glass Colors
val GlassSurfaceLight = Color(0xE6FFFFFF)      // 90% white translucent
val GlassSurfaceSubtleLight = Color(0xB8F8FAFC) // 72% cool white
val GlassBorderLight = Color(0x33007BA7)       // 20% Cerulean border glow
val GlassBorderHighlightLight = Color(0x80FFFFFF) // 50% Top edge light

// Dark Mode Glass Colors
val GlassSurfaceDark = Color(0xD91E293B)       // 85% slate-800 translucent
val GlassSurfaceSubtleDark = Color(0x990F172A) // 60% slate-900
val GlassBorderDark = Color(0x2E38BDF8)        // 18% Cerulean border glow

// Ambient Smart Gradients
val LightMeshBackground = Brush.verticalGradient(
    colors = listOf(
        Color(0xFFF8FAFC),
        Color(0xFFF0F7FD),
        Color(0xFFE8F3FA)
    )
)

val DarkMeshBackground = Brush.verticalGradient(
    colors = listOf(
        Color(0xFF0B1120),
        Color(0xFF0F172A),
        Color(0xFF131D31)
    )
)

val CobaltCeruleanGradient = Brush.horizontalGradient(
    colors = listOf(CobaltBlue, CeruleanBlueBright)
)

val CeruleanTealGradient = Brush.horizontalGradient(
    colors = listOf(CeruleanBlueBright, SmartTeal)
)
