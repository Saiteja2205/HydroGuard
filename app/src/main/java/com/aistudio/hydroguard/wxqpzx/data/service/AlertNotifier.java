package com.aistudio.hydroguard.wxqpzx.data.service;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;

import com.aistudio.hydroguard.wxqpzx.DashboardActivity;
import com.aistudio.hydroguard.wxqpzx.R;
import com.aistudio.hydroguard.wxqpzx.data.database.AppDatabase;
import com.aistudio.hydroguard.wxqpzx.data.database.NotificationLog;

import org.json.JSONObject;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Posts local notifications for server alerts and stale sensor data.
 * Repeat suppression uses a per-issue dedupe key enforced by a unique Room index.
 */
public class AlertNotifier {
    private static final String CHANNEL_ID = "hydroguard_alerts";
    private final Context context;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    public AlertNotifier(Context context) {
        this.context = context.getApplicationContext();
        createChannel();
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationManager manager = context.getSystemService(NotificationManager.class);
            if (manager.getNotificationChannel(CHANNEL_ID) == null) {
                NotificationChannel channel = new NotificationChannel(CHANNEL_ID,
                        "Water quality alerts", NotificationManager.IMPORTANCE_DEFAULT);
                channel.setDescription("Threshold and sensor connection alerts from HydroGuard");
                manager.createNotificationChannel(channel);
            }
        }
    }

    /** Notifies once per server alert id; acknowledged or resolved alerts are skipped. */
    public void notifyServerAlert(String nodeId, JSONObject alert) {
        if (!"ACTIVE".equals(alert.optString("status", "ACTIVE"))) return;
        String severity = alert.optString("severity", "WARNING");
        if ("INFO".equals(severity)) return;
        String title = severity + " · " + alert.optString("parameter", "Water quality");
        String body = alert.optString("message", "Water quality threshold exceeded");
        String dedupeKey = "alert:" + nodeId + ":" + alert.optInt("id");
        post(dedupeKey, title, body);
    }

    /** Notifies at most once per node per day when the newest reading is older than maxAgeHours. */
    public void notifyStaleSensor(String nodeId, long newestTimestampMillis, long maxAgeMillis, String ageLabel) {
        if (System.currentTimeMillis() - newestTimestampMillis <= maxAgeMillis) return;
        String dayKey = String.valueOf(System.currentTimeMillis() / 86_400_000L);
        post("stale:" + nodeId + ":" + dayKey, "Sensor connection warning",
                "No new reading from " + nodeId + " for " + ageLabel + ". Check the sensor connection.");
    }

    private void post(String dedupeKey, String title, String body) {
        executor.execute(() -> {
            AppDatabase database = AppDatabase.getDatabase(context);
            NotificationLog entry = new NotificationLog();
            entry.title = title;
            entry.body = body;
            entry.type = "ALERT";
            entry.dedupeKey = dedupeKey;
            long insertedId = database.hydroDao().insertNotificationIfAbsent(entry);
            if (insertedId == -1) return;
            Intent tapIntent = new Intent(context, DashboardActivity.class);
            tapIntent.setFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            int flags = android.app.PendingIntent.FLAG_UPDATE_CURRENT;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) flags |= android.app.PendingIntent.FLAG_IMMUTABLE;
            android.app.PendingIntent pendingIntent = android.app.PendingIntent.getActivity(
                    context, dedupeKey.hashCode(), tapIntent, flags);
            NotificationCompat.Builder builder = new NotificationCompat.Builder(context, CHANNEL_ID)
                    .setSmallIcon(R.mipmap.ic_launcher)
                    .setContentTitle(title)
                    .setContentText(body)
                    .setStyle(new NotificationCompat.BigTextStyle().bigText(body))
                    .setContentIntent(pendingIntent)
                    .setAutoCancel(true);
            NotificationManagerCompat.from(context).notify(dedupeKey.hashCode(), builder.build());
        });
    }
}
