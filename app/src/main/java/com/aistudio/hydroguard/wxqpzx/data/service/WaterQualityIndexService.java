package com.aistudio.hydroguard.wxqpzx.data.service;

/** Application-specific index; it is not a regulatory water-safety standard. */
public final class WaterQualityIndexService {
    public enum Category {
        EXCELLENT("Excellent"), GOOD("Good"), MODERATE("Moderate"), POOR("Poor"), CRITICAL("Critical");
        public final String displayName;
        Category(String displayName) { this.displayName = displayName; }
    }

    public static final class Result {
        public final int index;
        public final Category category;
        public final double phScore, tdsScore, turbidityScore, temperatureScore;
        Result(int index, Category category, double ph, double tds, double turbidity, double temperature) {
            this.index = index; this.category = category; this.phScore = ph;
            this.tdsScore = tds; this.turbidityScore = turbidity; this.temperatureScore = temperature;
        }
    }

    private WaterQualityIndexService() { }

    public static Result calculate(float ph, float tds, float turbidity, float temperature) {
        double phScore = phScore(ph), tdsScore = tdsScore(tds);
        double turbidityScore = turbidityScore(turbidity), temperatureScore = temperatureScore(temperature);
        int index = Math.max(0, Math.min(100, (int) (phScore * .25 + tdsScore * .25
                + turbidityScore * .25 + temperatureScore * .25)));
        Category category = index >= 90 ? Category.EXCELLENT : index >= 75 ? Category.GOOD
                : index >= 60 ? Category.MODERATE : index >= 40 ? Category.POOR : Category.CRITICAL;
        return new Result(index, category, phScore, tdsScore, turbidityScore, temperatureScore);
    }

    public static String getParameterStatus(String parameter, float value) {
        switch (parameter == null ? "" : parameter.toLowerCase(java.util.Locale.ROOT)) {
            case "ph": return value >= 6.5f && value <= 8.5f ? "Normal" : value < 6.5f ? "Acidic" : "Alkaline";
            case "tds": return value <= 300f ? "Normal" : value <= 500f ? "Elevated" : "High";
            case "turbidity": return value <= 1.5f ? "Normal" : value <= 5f ? "Elevated" : "High";
            case "temperature": return value >= 15f && value <= 30f ? "Normal" : value < 15f ? "Low" : "High";
            default: return "Unknown";
        }
    }

    private static double phScore(float value) {
        if (value < 5f || value > 10f) return 0;
        if (value >= 6.5f && value <= 8.5f) return 100;
        if (value < 6.5f) return linear(value, 5f, 6.5f);
        return linear(10f - value, 0f, 1.5f);
    }
    private static double tdsScore(float value) {
        if (value < 0) return 0;
        if (value <= 300) return 100;
        if (value <= 500) return linear(500 - value, 0, 200);
        if (value <= 1000) return linear(1000 - value, 0, 500);
        return 0;
    }
    private static double turbidityScore(float value) {
        if (value < 0) return 0;
        if (value <= 1.5) return 100;
        if (value <= 5) return linear(5 - value, 0, 3.5f);
        if (value <= 10) return linear(10 - value, 0, 5);
        return 0;
    }
    private static double temperatureScore(float value) {
        if (value < 0) return 0;
        if (value >= 15 && value <= 30) return 100;
        if (value >= 10 && value < 15) return linear(value - 10, 0, 5);
        if (value > 30 && value <= 40) return linear(40 - value, 0, 10);
        return 0;
    }
    private static double linear(float value, float min, float max) {
        if (max == min) return 0;
        return Math.max(0, Math.min(1, (value - min) / (max - min))) * 100;
    }
}
