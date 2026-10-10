package com.aistudio.hydroguard.wxqpzx.data.api;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.util.Log;

import com.aistudio.hydroguard.wxqpzx.BuildConfig;

import java.io.IOException;
import java.net.InetAddress;
import java.net.Socket;
import java.net.SocketException;
import java.net.URI;
import java.net.UnknownHostException;

import javax.net.SocketFactory;

/**
 * Routes HydroGuard API sockets through the connected Wi-Fi network when the API
 * host is a private LAN address. Phones with no-internet Wi-Fi fall back to
 * cellular as the default network, which cannot reach a LAN backend; binding only
 * this client's sockets (never the whole process) leaves Firebase and Google
 * sign-in on the default network. The Wi-Fi network is resolved at socket
 * creation time so reconnects are picked up without caching a stale Network.
 */
public final class LanApiRoute {
    private static volatile ConnectivityManager connectivity;
    private static volatile Runnable routeLostListener;

    /** Thrown instead of a silent 12 s timeout when no usable Wi-Fi network exists. */
    public static final class LanRouteUnavailableException extends SocketException {
        public LanRouteUnavailableException(String message) { super(message); }
    }

    private LanApiRoute() { }

    /** Called once from the Application subclass before any API traffic. */
    public static void attach(Context context) {
        connectivity = (ConnectivityManager) context.getApplicationContext()
                .getSystemService(Context.CONNECTIVITY_SERVICE);
    }

    /**
     * Watches connectivity so debug logs show route changes and pooled sockets from
     * a dead network are evicted immediately.
     */
    public static void register(Context context) {
        attach(context);
        connectivity.registerDefaultNetworkCallback(new ConnectivityManager.NetworkCallback() {
            @Override public void onAvailable(Network network) {
                if (BuildConfig.DEBUG) Log.d("HydroGuardApi", "network available " + network);
            }

            @Override public void onLost(Network network) {
                if (BuildConfig.DEBUG) Log.w("HydroGuardApi", "network lost " + network);
                Runnable listener = routeLostListener;
                if (listener != null) listener.run();
            }
        });
    }

    static void setRouteLostListener(Runnable listener) {
        routeLostListener = listener;
    }

    /**
     * True only for private IPv4 API hosts that need a Wi-Fi route lock. The
     * emulator alias 10.0.2.2 and loopback already work through default routing,
     * and public release hosts must keep default behavior.
     */
    static boolean isLanApiHost(String baseUrl) {
        String host = hostOf(baseUrl);
        if (host == null || host.equalsIgnoreCase("localhost")) return false;
        if (host.equals("10.0.2.2") || host.startsWith("127.")) return false;
        String[] parts = host.split("\\.");
        if (parts.length != 4) return false;
        int[] octets = new int[4];
        for (int i = 0; i < 4; i++) {
            try {
                octets[i] = Integer.parseInt(parts[i]);
            } catch (NumberFormatException error) {
                return false;
            }
            if (octets[i] < 0 || octets[i] > 255) return false;
        }
        return octets[0] == 10
                || (octets[0] == 192 && octets[1] == 168)
                || (octets[0] == 172 && octets[1] >= 16 && octets[1] <= 31);
    }

    static boolean isWifiConnected() {
        return wifiNetwork() != null;
    }

    private static Network wifiNetwork() {
        ConnectivityManager manager = connectivity;
        if (manager == null) return null;
        Network fallback = null;
        for (Network network : manager.getAllNetworks()) {
            NetworkCapabilities capabilities = manager.getNetworkCapabilities(network);
            if (capabilities == null || !capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) continue;
            if (capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)) return network;
            if (fallback == null) fallback = network;
        }
        // A hotspot without upstream internet keeps its Wi-Fi transport, which is
        // still the only path to the LAN backend, so it is a usable fallback.
        return fallback;
    }

    static SocketFactory wifiSocketFactory() {
        return new WifiSocketFactory();
    }

    private static final class WifiSocketFactory extends SocketFactory {
        private SocketFactory delegate() throws IOException {
            Network network = wifiNetwork();
            if (network == null) {
                throw new LanRouteUnavailableException(
                        "The phone is not connected to Wi-Fi. The HydroGuard backend is reachable only "
                                + "through the development computer's Wi-Fi network; mobile data cannot "
                                + "reach a LAN address. Connect Wi-Fi and try again.");
            }
            return network.getSocketFactory();
        }

        @Override public Socket createSocket() throws IOException { return delegate().createSocket(); }
        @Override public Socket createSocket(String host, int port) throws IOException { return delegate().createSocket(host, port); }
        @Override public Socket createSocket(String host, int port, InetAddress localHost, int localPort) throws IOException {
            return delegate().createSocket(host, port, localHost, localPort);
        }
        @Override public Socket createSocket(InetAddress host, int port) throws IOException { return delegate().createSocket(host, port); }
        @Override public Socket createSocket(InetAddress address, int port, InetAddress localAddress, int localPort) throws IOException {
            return delegate().createSocket(address, port, localAddress, localPort);
        }
    }

    private static String hostOf(String baseUrl) {
        if (baseUrl == null) return null;
        try {
            return URI.create(baseUrl).getHost();
        } catch (IllegalArgumentException error) {
            return null;
        }
    }
}
