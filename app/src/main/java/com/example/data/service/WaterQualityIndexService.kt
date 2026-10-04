package com.example.data.service

/**
 * HydroGuard Water Quality Index Service
 *
 * Calculates an application-specific indicator (0-100) from pH, TDS,
 * turbidity and temperature. It is not a regulatory or drinking-water standard.
 * Optical colour is intentionally excluded until a scoring method is validated.
 * 
 * Parameters scored:
 * - pH
 * - TDS (Total Dissolved Solids)
 * - Turbidity
 * - Temperature
 */
object WaterQualityIndexService {

    /**
     * Configurable weights for each parameter in the index calculation.
     * These are equal weights by default but can be adjusted based on research or requirements.
     */
    data class Weights(
        val ph: Double = 0.25,
        val tds: Double = 0.25,
        val turbidity: Double = 0.25,
        val temperature: Double = 0.25
    ) {
        init {
            val total = ph + tds + turbidity + temperature
            require(total == 1.0) { "Weights must sum to 1.0, but sum is $total" }
        }
    }

    /**
     * Water Quality Index result
     */
    data class WQIResult(
        val index: Int, // 0-100
        val category: Category,
        val phScore: Double,
        val tdsScore: Double,
        val turbidityScore: Double,
        val temperatureScore: Double
    )

    /**
     * Water Quality Index categories
     */
    enum class Category(val displayName: String, val description: String) {
        EXCELLENT("Excellent", "Application index is within its highest band"),
        GOOD("Good", "Application index is within its good band"),
        MODERATE("Moderate", "Some parameters require attention"),
        POOR("Poor", "Multiple parameters outside optimal ranges"),
        CRITICAL("Critical", "Water quality requires immediate attention")
    }

    /**
     * Calculate Water Quality Index from current parameter values
     * 
     * @param ph Current pH value (0-14)
     * @param tds Current TDS value in mg/L
     * @param turbidity Current turbidity value in NTU
     * @param temperature Current temperature in °C
     * @param weights Optional custom weights (defaults to equal 25% each)
     * @return WQIResult with index, category, and individual parameter scores
     */
    fun calculate(
        ph: Float,
        tds: Float,
        turbidity: Float,
        temperature: Float,
        weights: Weights = Weights()
    ): WQIResult {
        val phScore = calculatePHScore(ph)
        val tdsScore = calculateTDSScore(tds)
        val turbidityScore = calculateTurbidityScore(turbidity)
        val temperatureScore = calculateTemperatureScore(temperature)

        // Weighted combination
        val weightedIndex = (phScore * weights.ph) +
                           (tdsScore * weights.tds) +
                           (turbidityScore * weights.turbidity) +
                           (temperatureScore * weights.temperature)

        val index = weightedIndex.toInt().coerceIn(0, 100)
        val category = getCategory(index)

        return WQIResult(
            index = index,
            category = category,
            phScore = phScore,
            tdsScore = tdsScore,
            turbidityScore = turbidityScore,
            temperatureScore = temperatureScore
        )
    }

    /**
     * Calculate pH score (0-100)
     * Optimal range: 6.5 - 8.5
     * Linear scoring with 0 at pH < 5.0 or > 10.0
     */
    private fun calculatePHScore(ph: Float): Double {
        return when {
            ph < 5.0f -> 0.0
            ph > 10.0f -> 0.0
            ph in 6.5f..8.5f -> 100.0
            ph in 5.0f..6.5f -> linearScore(ph, 5.0f, 6.5f)
            ph in 8.5f..10.0f -> linearScore(10.0f - ph, 0.0f, 1.5f)
            else -> 0.0
        }
    }

    /**
     * Calculate TDS score (0-100)
     * Optimal: < 300 mg/L
     * Acceptable: 300-500 mg/L
     * Poor: > 500 mg/L
     */
    private fun calculateTDSScore(tds: Float): Double {
        return when {
            tds < 0f -> 0.0
            tds <= 300f -> 100.0
            tds <= 500f -> linearScore(500f - tds, 0f, 200f)
            tds <= 1000f -> linearScore(1000f - tds, 0f, 500f)
            else -> 0.0
        }
    }

    /**
     * Calculate Turbidity score (0-100)
     * Optimal: < 1.5 NTU
     * Acceptable: 1.5-5.0 NTU
     * Poor: > 5.0 NTU
     */
    private fun calculateTurbidityScore(turbidity: Float): Double {
        return when {
            turbidity < 0f -> 0.0
            turbidity <= 1.5f -> 100.0
            turbidity <= 5.0f -> linearScore(5.0f - turbidity, 0f, 3.5f)
            turbidity <= 10.0f -> linearScore(10.0f - turbidity, 0f, 5.0f)
            else -> 0.0
        }
    }

    /**
     * Calculate Temperature score (0-100)
     * Optimal: 15-30°C
     * Linear scoring outside this range
     */
    private fun calculateTemperatureScore(temperature: Float): Double {
        return when {
            temperature < 0f -> 0.0
            temperature in 15.0f..30.0f -> 100.0
            temperature in 10.0f..15.0f -> linearScore(temperature - 10.0f, 0f, 5.0f)
            temperature in 30.0f..40.0f -> linearScore(40.0f - temperature, 0f, 10.0f)
            else -> 0.0
        }
    }

    /**
     * Linear scoring helper
     * Maps a value in [min, max] range to [0, 100] score
     */
    private fun linearScore(value: Float, min: Float, max: Float): Double {
        if (max == min) return 0.0
        val normalized = ((value - min) / (max - min)).coerceIn(0f, 1f)
        return normalized * 100.0
    }

    /**
     * Get category from index value
     */
    private fun getCategory(index: Int): Category {
        return when {
            index >= 90 -> Category.EXCELLENT
            index >= 75 -> Category.GOOD
            index >= 60 -> Category.MODERATE
            index >= 40 -> Category.POOR
            else -> Category.CRITICAL
        }
    }

    /**
     * Get parameter status text based on value and thresholds
     * Used for UI parameter cards
     */
    fun getParameterStatus(
        parameter: String,
        value: Float
    ): String {
        return when (parameter.lowercase()) {
            "ph" -> when {
                value in 6.5f..8.5f -> "Normal"
                value < 6.5f -> "Acidic"
                value > 8.5f -> "Alkaline"
                else -> "Critical"
            }
            "tds" -> when {
                value <= 300f -> "Normal"
                value <= 500f -> "Elevated"
                else -> "High"
            }
            "turbidity" -> when {
                value <= 1.5f -> "Normal"
                value <= 5.0f -> "Elevated"
                else -> "High"
            }
            "temperature" -> when {
                value in 15.0f..30.0f -> "Normal"
                value < 15.0f -> "Low"
                value > 30.0f -> "High"
                else -> "Critical"
            }
            else -> "Unknown"
        }
    }
}
