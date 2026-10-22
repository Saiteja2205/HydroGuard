package com.aistudio.hydroguard.wxqpzx.data.service;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;

import com.aistudio.hydroguard.wxqpzx.DashboardActivity;
import com.aistudio.hydroguard.wxqpzx.R;
import com.aistudio.hydroguard.wxqpzx.data.api.ApiCallback;
import com.aistudio.hydroguard.wxqpzx.data.api.ApiFailure;
import com.aistudio.hydroguard.wxqpzx.data.api.ApiRepository;
import com.aistudio.hydroguard.wxqpzx.data.database.AppDatabase;
import com.aistudio.hydroguard.wxqpzx.data.database.NotificationLog;
import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;

import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Handles Firebase Cloud Messaging (FCM) token refresh, background message delivery,
 * notification posting with local deduplication, and deep-linking into DashboardActivity.
 */
public class HydroGuardFirebaseMessagingService extends FirebaseMessagingService {
    private static final String TAG = "HydroGuardFCM";
    public static final String CHANNEL_ID = "hydroguard_alerts";
    public static final String PREFS_NAME = "hydroguard_fcm";
    public static final String KEY_FCM_TOKEN = "fcm_token";
    public static final String KEY_BACKEND_REGISTERED_TOKEN = "backend_registered_token";

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final ApiRepository api = new ApiRepository();

    @Override
    public void onNewToken(@NonNull String token) {
        super.onNewToken(token);
        Log.i(TAG, "New FCM token received: " + token);

        // Store token in local preferences
        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        prefs.edit().putString(KEY_FCM_TOKEN, token).apply();

        // Register token with backend API
        registerTokenWithBackend(token);
    }

    @Override
    public void onMessageReceived(@NonNull RemoteMessage remoteMessage) {
        super.onMessageReceived(remoteMessage);
        Log.i(TAG, "FCM message received from: " + remoteMessage.getFrom());

        Map<String, String> data = remoteMessage.getData();
        String title = null;
        String body = null;

        if (remoteMessage.getNotification() != null) {
            title = remoteMessage.getNotification().getTitle();
            body = remoteMessage.getNotification().getBody();
        }

        if ((title == null || title.isEmpty()) && data.containsKey("title")) {
            title = data.get("title");
        }
        if ((body == null || body.isEmpty()) && data.containsKey("body")) {
            body = data.get("body");
        }

        if (title == null || title.isEmpty()) {
            title = "HydroGuard: Water Quality Alert";
        }
        if (body == null || body.isEmpty()) {
            body = "A water quality parameter threshold violation was detected.";
        }

        String alertId = data.get("alert_id");
        String nodeId = data.get("node_id");
        String targetScreen = data.getOrDefault("target_screen", "water");

        String dedupeKey = alertId != null && !alertId.isEmpty()
                ? "fcm:alert:" + alertId
                : "fcm:msg:" + remoteMessage.getMessageId();

        postNotification(dedupeKey, title, body, targetScreen, alertId, nodeId);
    }

    public void registerTokenWithBackend(String token) {
        if (token == null || token.trim().isEmpty()) {
            return;
        }
        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        String registered = prefs.getString(KEY_BACKEND_REGISTERED_TOKEN, null);
        if (token.equals(registered)) {
            Log.d(TAG, "Token already registered with backend, skipping duplicate registration.");
            return;
        }

        api.registerDeviceToken(token, "android", new ApiCallback() {
            @Override
            public void onSuccess(String json) {
                Log.i(TAG, "FCM token successfully registered with backend.");
                prefs.edit().putString(KEY_BACKEND_REGISTERED_TOKEN, token).apply();
            }

            @Override
            public void onFailure(ApiFailure failure) {
                Log.w(TAG, "Failed to register FCM token with backend: " + failure.getMessage());
            }
        });
    }

    private void postNotification(
            String dedupeKey,
            String title,
            String body,
            String targetScreen,
            String alertId,
            String nodeId
    ) {
        postNotificationDirect(getApplicationContext(), dedupeKey, title, body, targetScreen, alertId, nodeId);
    }

    public static void postNotificationDirect(
            Context context,
            String dedupeKey,
            String title,
            String body,
            String targetScreen,
            String alertId,
            String nodeId
    ) {
        Executors.newSingleThreadExecutor().execute(() -> {
            try {
                ensureNotificationChannel(context);

                // Insert into local Room database for deduplication and local history
                AppDatabase database = AppDatabase.getDatabase(context);
                NotificationLog entry = new NotificationLog();
                entry.title = title;
                entry.body = body;
                entry.type = "ALERT";
                entry.dedupeKey = dedupeKey;
                long insertedId = database.hydroDao().insertNotificationIfAbsent(entry);
                if (insertedId == -1) {
                    Log.d(TAG, "Notification with dedupeKey '" + dedupeKey + "' already displayed; skipping.");
                    return;
                }

                // Create deep-link tap intent to DashboardActivity
                Intent tapIntent = new Intent(context, DashboardActivity.class);
                tapIntent.setFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
                tapIntent.putExtra("target_screen", targetScreen);
                if (alertId != null) {
                    tapIntent.putExtra("alert_id", alertId);
                }
                if (nodeId != null) {
                    tapIntent.putExtra("node_id", nodeId);
                }

                int flags = PendingIntent.FLAG_UPDATE_CURRENT;
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                    flags |= PendingIntent.FLAG_IMMUTABLE;
                }

                int notificationId = dedupeKey.hashCode();
                PendingIntent pendingIntent = PendingIntent.getActivity(
                        context,
                        notificationId,
                        tapIntent,
                        flags
                );

                NotificationCompat.Builder builder = new NotificationCompat.Builder(context, CHANNEL_ID)
                        .setSmallIcon(R.mipmap.ic_launcher)
                        .setContentTitle(title)
                        .setContentText(body)
                        .setStyle(new NotificationCompat.BigTextStyle().bigText(body))
                        .setContentIntent(pendingIntent)
                        .setPriority(NotificationCompat.PRIORITY_HIGH)
                        .setAutoCancel(true);

                NotificationManagerCompat.from(context).notify(notificationId, builder.build());
                Log.i(TAG, "Displayed push notification: " + title);
            } catch (SecurityException secEx) {
                Log.w(TAG, "Notification permission not granted: " + secEx.getMessage());
            } catch (Throwable t) {
                Log.e(TAG, "Error posting push notification: " + t.getMessage(), t);
            }
        });
    }

    public static void ensureNotificationChannel(Context context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationManager manager = context.getSystemService(NotificationManager.class);
            if (manager != null && manager.getNotificationChannel(CHANNEL_ID) == null) {
                NotificationChannel channel = new NotificationChannel(
                        CHANNEL_ID,
                        "Water quality alerts",
                        NotificationManager.IMPORTANCE_HIGH
                );
                channel.setDescription("Water quality alerts and threshold breach advisories from HydroGuard");
                manager.createNotificationChannel(channel);
            }
        }
    }
}
