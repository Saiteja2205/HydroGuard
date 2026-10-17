package com.aistudio.hydroguard.wxqpzx.data.service;

/** Application-specific index; it is not a regulatory water-safety standard. */
public final class WaterQualityIndexService {
    public enum Category {
        EXCELLENT("Excellent"), GOOD("Good"), MODERATE("Moderate"), POOR("Poor"), CRITICAL("Critical");
        public final String displayName;
        Category(String displayName) { this.displayName = displayName; }
    }

    public enum ScoreState {
        VALID,
        PROVISIONAL,
        UNAVAILABLE
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

    public static final class AdvisoryEvaluation {
        public final int score; // 0..100, or -1 if unavailable
        public final Category category; // null if unavailable
        public final ScoreState state;
        public final String badgeLabel;
        public final String statusDescription;
        public final int normalCount;
        public final int totalEvaluated;
        public final int outsideRangeCount;
        public final String parameterBreakdown;
        public final String disclaimer;
        public final double phScore, tdsScore, turbidityScore, temperatureScore;

        // Semantic aliases
        public final String badgeText;
        public final String statusText;
        public final int normalParameters;
        public final int outsideRangeParameters;
        public final String breakdownText;

        public AdvisoryEvaluation(int score, Category category, ScoreState state,
                                  String badgeLabel, String statusDescription,
                                  int normalCount, int totalEvaluated, int outsideRangeCount,
                                  String parameterBreakdown, String disclaimer,
                                  double phScore, double tdsScore, double turbidityScore, double temperatureScore) {
            this.score = score;
            this.category = category;
            this.state = state;
            this.badgeLabel = badgeLabel;
            this.statusDescription = statusDescription;
            this.normalCount = normalCount;
            this.totalEvaluated = totalEvaluated;
            this.outsideRangeCount = outsideRangeCount;
            this.parameterBreakdown = parameterBreakdown;
            this.disclaimer = disclaimer;
            this.phScore = phScore;
            this.tdsScore = tdsScore;
            this.turbidityScore = turbidityScore;
            this.temperatureScore = temperatureScore;

            this.badgeText = badgeLabel;
            this.statusText = statusDescription;
            this.normalParameters = normalCount;
            this.outsideRangeParameters = outsideRangeCount;
            this.breakdownText = parameterBreakdown;
        }

        public boolean isScoreAvailable() {
            return score >= 0;
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

    public static AdvisoryEvaluation evaluateAdvisoryScore(Double ph, Double tds, Double turbidity, Double temperature, boolean isStale) {
        final String standardDisclaimer = "Based on available sensor readings · Not a drinking-water safety certification";

        // Check for completely missing readings
        if (ph == null && tds == null && turbidity == null && temperature == null) {
            return new AdvisoryEvaluation(-1, null, ScoreState.UNAVAILABLE, "UNAVAILABLE", "No Telemetry",
                    0, 4, 4, "Sensor readings currently unavailable", standardDisclaimer, 0, 0, 0, 0);
        }

        // Check for physical sensor dropout (e.g. open-circuit analog zero on pH probe)
        if (ph != null && !Double.isNaN(ph) && (ph <= 0.05 || ph > 14.0)) {
            return new AdvisoryEvaluation(-1, null, ScoreState.PROVISIONAL, "PROVISIONAL", "Sensor Dropout",
                    0, 4, 4, "pH open-circuit dropout detected · Score withheld", standardDisclaimer, 0, 0, 0, 0);
        }

        // Check for incomplete parameter set
        if (ph == null || Double.isNaN(ph) || tds == null || Double.isNaN(tds)
                || turbidity == null || Double.isNaN(turbidity) || temperature == null || Double.isNaN(temperature)) {
            return new AdvisoryEvaluation(-1, null, ScoreState.PROVISIONAL, "PROVISIONAL", "Incomplete Data",
                    0, 4, 4, "Partial telemetry · Requires all 4 primary sensors", standardDisclaimer, 0, 0, 0, 0);
        }

        // Check for negative or unphysical values
        if (tds < 0 || turbidity < 0 || temperature < -10) {
            return new AdvisoryEvaluation(-1, null, ScoreState.PROVISIONAL, "PROVISIONAL", "Invalid Data",
                    0, 4, 4, "Negative sensor reading detected · Sensor calibration required", standardDisclaimer, 0, 0, 0, 0);
        }

        // All 4 primary parameters are present and physically plausible:
        Result res = calculate(ph.floatValue(), tds.floatValue(), turbidity.floatValue(), temperature.floatValue());

        boolean phNormal = "Normal".equals(getParameterStatus("ph", ph.floatValue()));
        boolean tdsNormal = "Normal".equals(getParameterStatus("tds", tds.floatValue()));
        boolean turbidityNormal = "Normal".equals(getParameterStatus("turbidity", turbidity.floatValue()));
        boolean tempNormal = "Normal".equals(getParameterStatus("temperature", temperature.floatValue()));

        int normalCount = (phNormal ? 1 : 0) + (tdsNormal ? 1 : 0) + (turbidityNormal ? 1 : 0) + (tempNormal ? 1 : 0);
        int outsideCount = 4 - normalCount;

        String breakdown;
        if (outsideCount == 0) {
            breakdown = "All 4 parameters within normal ranges";
        } else if (outsideCount == 1) {
            breakdown = "1 parameter outside configured ranges";
        } else {
            breakdown = outsideCount + " parameters outside configured ranges";
        }

        if (isStale) {
            return new AdvisoryEvaluation(res.index, res.category, ScoreState.PROVISIONAL, "PROVISIONAL",
                    "Provisional (" + res.category.displayName + ")", normalCount, 4, outsideCount,
                    breakdown + " · Telemetry delayed", standardDisclaimer,
                    res.phScore, res.tdsScore, res.turbidityScore, res.temperatureScore);
        }

        return new AdvisoryEvaluation(res.index, res.category, ScoreState.VALID, res.category.name(),
                res.category.displayName, normalCount, 4, outsideCount,
                breakdown, standardDisclaimer,
                res.phScore, res.tdsScore, res.turbidityScore, res.temperatureScore);
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
