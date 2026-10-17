package com.aistudio.hydroguard.wxqpzx.ui;

import android.content.Context;
import android.widget.TextView;

import com.aistudio.hydroguard.wxqpzx.R;
import com.github.mikephil.charting.components.MarkerView;
import com.github.mikephil.charting.data.Entry;
import com.github.mikephil.charting.highlight.Highlight;
import com.github.mikephil.charting.utils.MPPointF;

import java.util.List;
import java.util.Locale;

/**
 * Interactive tooltip marker for HydroGuard MPAndroidChart telemetry plots.
 * Displays observed parameter value and observation timestamp when touched.
 */
public class HydroGuardMarkerView extends MarkerView {

    private final TextView valueView;
    private final TextView timeView;
    private List<String> labels;
    private String unit = "";

    public HydroGuardMarkerView(Context context, List<String> labels, String unit) {
        super(context, R.layout.view_chart_marker);
        this.labels = labels;
        this.unit = unit != null ? unit.trim() : "";
        valueView = findViewById(R.id.marker_value);
        timeView = findViewById(R.id.marker_time);
    }

    public void updateLabels(List<String> labels, String unit) {
        this.labels = labels;
        this.unit = unit != null ? unit.trim() : "";
    }

    @Override
    public void refreshContent(Entry e, Highlight highlight) {
        if (valueView != null) {
            String valStr = String.format(Locale.ROOT, "%.2f", e.getY());
            if (!unit.isEmpty()) {
                valStr += " " + unit;
            }
            valueView.setText(valStr);
        }

        if (timeView != null) {
            int index = Math.round(e.getX());
            if (labels != null && index >= 0 && index < labels.size()) {
                timeView.setText(labels.get(index));
                timeView.setVisibility(VISIBLE);
            } else {
                timeView.setVisibility(GONE);
            }
        }

        super.refreshContent(e, highlight);
    }

    @Override
    public MPPointF getOffset() {
        return new MPPointF(-(getWidth() / 2f), -getHeight() - 10f);
    }
}
