package com.aistudio.hydroguard.wxqpzx;

import com.aistudio.hydroguard.wxqpzx.data.service.WaterQualityIndexService;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

public class WaterQualityIndexServiceTest {

    @Test
    public void indexUsesFourProductParametersAndReportsCategory() {
        WaterQualityIndexService.Result result = WaterQualityIndexService.calculate(7.0f, 250.0f, 1.0f, 22.0f);
        assertEquals(100, result.index);
        assertEquals(WaterQualityIndexService.Category.EXCELLENT, result.category);
    }

    @Test
    public void highTdsReducesTheApplicationIndex() {
        WaterQualityIndexService.Result result = WaterQualityIndexService.calculate(7.0f, 1200.0f, 1.0f, 22.0f);
        assertEquals(75, result.index);
        assertEquals("High", WaterQualityIndexService.getParameterStatus("tds", 1200.0f));
    }

    @Test
    public void evaluateAdvisoryScoreAllNormalParameters() {
        WaterQualityIndexService.AdvisoryEvaluation eval =
                WaterQualityIndexService.evaluateAdvisoryScore(7.2, 220.0, 0.8, 24.0, false);

        assertEquals(100, eval.score);
        assertEquals(WaterQualityIndexService.ScoreState.VALID, eval.state);
        assertEquals("EXCELLENT", eval.badgeText);
        assertEquals(WaterQualityIndexService.Category.EXCELLENT, eval.category);
        assertEquals(4, eval.normalParameters);
        assertEquals(0, eval.outsideRangeParameters);
        assertEquals("All 4 parameters within normal ranges", eval.breakdownText);
        assertTrue(eval.disclaimer.contains("Not a drinking-water safety certification"));
    }

    @Test
    public void evaluateAdvisoryScoreWithOutsideRangeParameters() {
        // pH 4.0 (acidic -> score 0), TDS 800 (elevated -> score 40)
        // Turbidity 0.8 (normal -> score 100), Temp 24 (normal -> score 100)
        WaterQualityIndexService.AdvisoryEvaluation eval =
                WaterQualityIndexService.evaluateAdvisoryScore(4.0, 800.0, 0.8, 24.0, false);

        assertEquals(WaterQualityIndexService.ScoreState.VALID, eval.state);
        assertEquals(2, eval.normalParameters);
        assertEquals(2, eval.outsideRangeParameters);
        assertEquals("2 parameters outside configured ranges", eval.breakdownText);
    }

    @Test
    public void evaluateAdvisoryScoreMissingParametersReturnsUnavailable() {
        // Completely missing parameters
        WaterQualityIndexService.AdvisoryEvaluation eval =
                WaterQualityIndexService.evaluateAdvisoryScore(null, null, null, null, false);

        assertEquals(-1, eval.score);
        assertEquals(WaterQualityIndexService.ScoreState.UNAVAILABLE, eval.state);
        assertEquals("UNAVAILABLE", eval.badgeText);
        assertNull(eval.category);
        assertTrue(eval.breakdownText.contains("Sensor readings currently unavailable"));
    }

    @Test
    public void evaluateAdvisoryScorePartialTelemetryReturnsProvisional() {
        // Missing pH and TDS
        WaterQualityIndexService.AdvisoryEvaluation eval =
                WaterQualityIndexService.evaluateAdvisoryScore(null, null, 1.2, 22.0, false);

        assertEquals(-1, eval.score);
        assertEquals(WaterQualityIndexService.ScoreState.PROVISIONAL, eval.state);
        assertEquals("PROVISIONAL", eval.badgeText);
        assertTrue(eval.breakdownText.contains("Requires all 4 primary sensors"));
    }

    @Test
    public void evaluateAdvisoryScoreUnphysicalDropoutWithholdsScore() {
        // pH <= 0.05 is an open-circuit / 0V analog sensor dropout
        WaterQualityIndexService.AdvisoryEvaluation eval =
                WaterQualityIndexService.evaluateAdvisoryScore(0.02, 250.0, 1.0, 22.0, false);

        assertEquals(-1, eval.score);
        assertEquals(WaterQualityIndexService.ScoreState.PROVISIONAL, eval.state);
        assertEquals("PROVISIONAL", eval.badgeText);
        assertTrue(eval.breakdownText.contains("open-circuit dropout"));
    }

    @Test
    public void evaluateAdvisoryScoreStaleTelemetryMarksProvisional() {
        WaterQualityIndexService.AdvisoryEvaluation eval =
                WaterQualityIndexService.evaluateAdvisoryScore(7.2, 250.0, 1.0, 22.0, true);

        assertEquals(100, eval.score);
        assertEquals(WaterQualityIndexService.ScoreState.PROVISIONAL, eval.state);
        assertEquals("PROVISIONAL", eval.badgeText);
        assertTrue(eval.statusText.contains("Provisional"));
        assertTrue(eval.breakdownText.contains("Telemetry delayed"));
    }

    @Test
    public void evaluateAdvisoryScoreNegativeValuesHandled() {
        WaterQualityIndexService.AdvisoryEvaluation eval =
                WaterQualityIndexService.evaluateAdvisoryScore(7.0, -50.0, 1.0, 22.0, false);

        assertEquals(-1, eval.score);
        assertEquals(WaterQualityIndexService.ScoreState.PROVISIONAL, eval.state);
        assertTrue(eval.breakdownText.contains("Negative sensor reading"));
    }

    @Test
    public void parameterStatusResolutions() {
        assertEquals("Normal", WaterQualityIndexService.getParameterStatus("ph", 7.4f));
        assertEquals("Acidic", WaterQualityIndexService.getParameterStatus("ph", 6.1f));
        assertEquals("Alkaline", WaterQualityIndexService.getParameterStatus("ph", 9.0f));

        assertEquals("Normal", WaterQualityIndexService.getParameterStatus("tds", 280f));
        assertEquals("Elevated", WaterQualityIndexService.getParameterStatus("tds", 450f));
        assertEquals("High", WaterQualityIndexService.getParameterStatus("tds", 650f));

        assertEquals("Normal", WaterQualityIndexService.getParameterStatus("turbidity", 1.2f));
        assertEquals("Elevated", WaterQualityIndexService.getParameterStatus("turbidity", 3.5f));
        assertEquals("High", WaterQualityIndexService.getParameterStatus("turbidity", 7.0f));

        assertEquals("Normal", WaterQualityIndexService.getParameterStatus("temperature", 24f));
        assertEquals("Low", WaterQualityIndexService.getParameterStatus("temperature", 12f));
        assertEquals("High", WaterQualityIndexService.getParameterStatus("temperature", 34f));
    }
}
