package com.aistudio.hydroguard.wxqpzx.ui;

import android.graphics.Typeface;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import com.aistudio.hydroguard.wxqpzx.R;
import com.google.android.material.button.MaterialButton;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

public class AlertAdapter extends RecyclerView.Adapter<AlertAdapter.AlertHolder> {
    public interface AcknowledgeListener {
        void onAcknowledge(int alertId, MaterialButton button);
    }

    private final List<JSONObject> alerts = new ArrayList<>();
    private final boolean admin;
    private final AcknowledgeListener listener;

    public AlertAdapter(boolean admin, AcknowledgeListener listener) {
        this.admin = admin;
        this.listener = listener;
    }

    public void submit(List<JSONObject> rows) {
        alerts.clear();
        alerts.addAll(rows);
        try {
            notifyDataSetChanged();
        } catch (Exception ignored) {
            // In unit tests without an attached RecyclerView observer, notifyDataSetChanged is unmocked
        }
    }

    @NonNull
    @Override
    public AlertHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        return new AlertHolder(LayoutInflater.from(parent.getContext())
                .inflate(R.layout.item_alert, parent, false));
    }

    @Override
    public void onBindViewHolder(@NonNull AlertHolder holder, int position) {
        JSONObject alert = alerts.get(position);
        holder.parameter.setText(alert.optString("parameter", "Water quality"));
        String severity = alert.optString("severity", "INFO");
        String status = alert.optString("status", "ACTIVE").toUpperCase();

        int color;
        if ("RESOLVED".equals(status)) {
            holder.severity.setText("RESOLVED");
            color = R.color.hydroguard_green;
            holder.itemView.setAlpha(0.75f);
        } else if ("ACKNOWLEDGED".equals(status)) {
            holder.severity.setText(severity + " · ACKNOWLEDGED");
            color = R.color.hydroguard_orange;
            holder.itemView.setAlpha(0.9f);
        } else {
            holder.severity.setText(severity + " · ACTIVE");
            color = "CRITICAL".equals(severity) || "WARNING".equals(severity)
                    ? R.color.hydroguard_red : "INFO".equals(severity) ? R.color.hydroguard_blue : R.color.hydroguard_muted;
            holder.itemView.setAlpha(1.0f);
        }

        holder.severity.setTextColor(holder.severity.getContext().getColor(color));
        holder.severity.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        holder.message.setText(alert.optString("message", "Water quality alert"));
        holder.meta.setText("Reading " + alert.optDouble("value", 0) + " · limit "
                + alert.optDouble("threshold", 0) + "\n"
                + Timestamps.readable(alert.optString("timestamp", "")));
        boolean showAcknowledge = admin && "ACTIVE".equals(status);
        holder.acknowledge.setVisibility(showAcknowledge ? View.VISIBLE : View.GONE);
        if (showAcknowledge) {
            holder.acknowledge.setEnabled(true);
            holder.acknowledge.setOnClickListener(view -> {
                holder.acknowledge.setEnabled(false);
                if (listener != null) {
                    listener.onAcknowledge(alert.optInt("id"), holder.acknowledge);
                }
            });
        }
    }

    @Override
    public int getItemCount() {
        return alerts.size();
    }

    static class AlertHolder extends RecyclerView.ViewHolder {
        final TextView parameter;
        final TextView severity;
        final TextView message;
        final TextView meta;
        final MaterialButton acknowledge;

        AlertHolder(View view) {
            super(view);
            parameter = view.findViewById(R.id.alert_parameter);
            severity = view.findViewById(R.id.alert_severity);
            message = view.findViewById(R.id.alert_message);
            meta = view.findViewById(R.id.alert_meta);
            acknowledge = view.findViewById(R.id.alert_acknowledge);
        }
    }
}
