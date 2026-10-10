package com.aistudio.hydroguard.wxqpzx.data.api;

import android.util.Log;

import com.aistudio.hydroguard.wxqpzx.BuildConfig;
import com.aistudio.hydroguard.wxqpzx.data.repository.DevelopmentAuthPolicy;
import com.google.android.gms.tasks.Tasks;
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseUser;

import java.io.IOException;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import okhttp3.Authenticator;
import okhttp3.Interceptor;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.Route;
import retrofit2.Retrofit;

public final class RetrofitClient {
    private static final String BASE_URL = BuildConfig.API_BASE_URL;
    private static final long TOKEN_WAIT_SECONDS = 10L;
    private static volatile android.content.Context appContext;
    private static final OkHttpClient CLIENT = createClient();
    private static final Retrofit RETROFIT = new Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(CLIENT)
            .build();
    private static final HydroGuardApiService API = RETROFIT.create(HydroGuardApiService.class);

    private RetrofitClient() { }

    /**
     * Called once from HydroGuardApplication. Kept optional so plain JVM unit tests
     * can load this class without an Android context; without it the client uses
     * default routing, exactly as before.
     */
    public static void attach(android.content.Context context) {
        appContext = context.getApplicationContext();
    }

    private static OkHttpClient createClient() {
        if (!(BASE_URL.startsWith("https://") || (BuildConfig.DEBUG && BASE_URL.startsWith("http://")))) {
            throw new IllegalStateException("Release builds require an HTTPS HydroGuard API URL.");
        }
        if (!BASE_URL.endsWith("/")) {
            throw new IllegalStateException("HYDROGUARD_API_BASE_URL must end with '/'.");
        }
        OkHttpClient.Builder builder = new OkHttpClient.Builder()
                .addInterceptor(RetrofitClient::authenticateRequest)
                .addInterceptor(RetrofitClient::logRequest)
                .authenticator(RetrofitClient::refreshFirebaseToken)
                .connectTimeout(12, TimeUnit.SECONDS)
                .readTimeout(30, TimeUnit.SECONDS)
                .writeTimeout(30, TimeUnit.SECONDS);
        if (appContext != null && LanApiRoute.isLanApiHost(BASE_URL)) {
            builder.socketFactory(LanApiRoute.wifiSocketFactory());
        }
        OkHttpClient client = builder.build();
        if (appContext != null && LanApiRoute.isLanApiHost(BASE_URL)) {
            LanApiRoute.setRouteLostListener(() -> client.connectionPool().evictAll());
        }
        return client;
    }

    private static Response authenticateRequest(Interceptor.Chain chain) throws IOException {
        Request.Builder request = chain.request().newBuilder();
        Map<String, String> developmentHeaders = DevelopmentAuthPolicy.headers(
                BuildConfig.DEBUG, BuildConfig.ALLOW_DEVELOPMENT_LOGIN, BuildConfig.DEVELOPMENT_API_TOKEN);
        if (!developmentHeaders.isEmpty()) {
            for (Map.Entry<String, String> header : developmentHeaders.entrySet()) {
                request.header(header.getKey(), header.getValue());
            }
        } else {
            String token = firebaseToken(false);
            if (token != null) request.header("Authorization", "Bearer " + token);
        }
        return chain.proceed(request.build());
    }

    private static Response logRequest(Interceptor.Chain chain) throws IOException {
        Request request = chain.request();
        String endpoint = request.url().scheme() + "://" + request.url().host() + ":" + request.url().port()
                + request.url().encodedPath();
        long started = System.nanoTime();
        if (BuildConfig.DEBUG) Log.d("HydroGuardApi", "request " + request.method() + " " + endpoint);
        try {
            Response response = chain.proceed(request);
            if (BuildConfig.DEBUG) {
                long duration = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started);
                Log.d("HydroGuardApi", "response " + response.code() + " " + request.method()
                        + " " + endpoint + " " + duration + "ms");
            }
            return response;
        } catch (IOException error) {
            if (BuildConfig.DEBUG) {
                Log.e("HydroGuardApi", "Network request failed: " + error.getMessage() + " " + endpoint, error);
            }
            throw error;
        }
    }

    private static Request refreshFirebaseToken(Route route, Response response) {
        if (responseCount(response) >= 2 || !DevelopmentAuthPolicy.current().isEmpty()) return null;
        String token = firebaseToken(true);
        if (token == null) return null;
        return response.request().newBuilder().header("Authorization", "Bearer " + token).build();
    }

    private static int responseCount(Response response) {
        int count = 1;
        for (Response prior = response.priorResponse(); prior != null; prior = prior.priorResponse()) count++;
        return count;
    }

    private static String firebaseToken(boolean forceRefresh) {
        try {
            FirebaseUser user = FirebaseAuth.getInstance().getCurrentUser();
            if (user == null) return null;
            String uid = user.getUid();
            String token = Tasks.await(user.getIdToken(forceRefresh), TOKEN_WAIT_SECONDS, TimeUnit.SECONDS).getToken();
            FirebaseUser stillSignedIn = FirebaseAuth.getInstance().getCurrentUser();
            return token != null && !token.trim().isEmpty() && stillSignedIn != null
                    && uid.equals(stillSignedIn.getUid()) ? token : null;
        } catch (Exception error) {
            if (BuildConfig.DEBUG) Log.w("HydroGuardApi", "Firebase token retrieval failed: " + error.getClass().getSimpleName());
            return null;
        }
    }

    public static HydroGuardApiService api() { return API; }
    public static String baseUrl() { return BASE_URL; }
    public static OkHttpClient httpClient() { return CLIENT; }
}
