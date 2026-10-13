package com.aistudio.hydroguard.wxqpzx.data.api;

import android.os.Handler;
import android.os.Looper;

/**
 * Records whether the HydroGuard API is actually answering, for the navy top application bar.
 *
 * <p>The approved reference shows a persistent link state in the app bar, and an indicator that
 * claims "ONLINE" from a guess would be exactly the kind of fabricated telemetry this project
 * forbids. So the state here is derived only from real transport outcomes observed in
 * {@link ApiRepository}'s single request funnel: a response of any status means the server was
 * reached (it answered, even with 401 or 404), while a transport failure means it was not.
 * Nothing is inferred from timers, from the last value cached on disk, or from the presence of a
 * Wi-Fi association, which says nothing about whether this host is reachable.</p>
 *
 * <p>Writes happen on OkHttp worker threads; reads and listener callbacks are marshalled to the
 * main thread. The listener is deliberately cleared by the activity in {@code onDestroy} so a
 * destroyed activity is never retained.</p>
 */
public final class ServerLink {

    /** Transport state of the API link. {@link #UNKNOWN} until the first request settles. */
    public enum State {
        /** No request has completed yet (cold start, or every call still in flight). */
        UNKNOWN,
        /** A request received an HTTP response — the server is answering. */
        REACHABLE,
        /** A request failed before any HTTP response (refused, reset, timed out, no route). */
        UNREACHABLE
    }

    public interface Listener {
        void onServerLinkChanged(State state);
    }

    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    private static volatile State state = State.UNKNOWN;
    private static volatile Listener listener;

    private ServerLink() {
    }

    public static State current() {
        return state;
    }

    /** Register the activity that owns the app bar. Pass {@code null} to unregister. */
    public static void setListener(Listener newListener) {
        listener = newListener;
    }

    /** An HTTP response arrived: the server is reachable regardless of its status code. */
    static void recordResponseReceived() {
        publish(State.REACHABLE);
    }

    /** The request failed in transport: no HTTP response was ever produced. */
    static void recordTransportFailure() {
        publish(State.UNREACHABLE);
    }

    private static void publish(State next) {
        if (state == next) return;
        state = next;
        if (listener == null) return;
        MAIN.post(() -> {
            Listener current = listener;
            if (current != null) current.onServerLinkChanged(next);
        });
    }
}
