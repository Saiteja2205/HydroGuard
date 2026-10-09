package com.aistudio.hydroguard.wxqpzx;

import com.aistudio.hydroguard.wxqpzx.data.service.WaterQualityIndexService;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class WaterQualityIndexServiceTest {
    @Test public void indexUsesFourProductParametersAndReportsCategory() {
        WaterQualityIndexService.Result result = WaterQualityIndexService.calculate(7.0f, 250.0f, 1.0f, 22.0f);
        assertEquals(100, result.index);
        assertEquals(WaterQualityIndexService.Category.EXCELLENT, result.category);
    }

    @Test public void highTdsReducesTheApplicationIndex() {
        WaterQualityIndexService.Result result = WaterQualityIndexService.calculate(7.0f, 1200.0f, 1.0f, 22.0f);
        assertEquals(75, result.index);
        assertEquals("High", WaterQualityIndexService.getParameterStatus("tds", 1200.0f));
    }
}
