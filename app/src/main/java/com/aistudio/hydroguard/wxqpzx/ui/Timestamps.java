package com.aistudio.hydroguard.wxqpzx.ui;

import java.text.ParsePosition;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

/**
 * Formats the timestamps the backend actually stores, in the viewer's local time
 * zone, for example {@code 5 Oct 2026, 10:45 PM}.
 *
 * <p>The machine-readable values in the API and the database are never modified —
 * this is presentation only. A missing or malformed value is returned unchanged
 * rather than replaced with the current time, because inventing a timestamp would
 * fabricate freshness that the data does not have.</p>
 */
public final class Timestamps {

    /** Patterns the backend emits for persisted timestamps, most specific first. */
    private static final String[] PATTERNS = {
            "yyyy-MM-dd'T'HH:mm:ss.SSSSSS'Z'",
            "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'",
            "yyyy-MM-dd'T'HH:mm:ss'Z'",
            "yyyy-MM-dd'T'HH:mm:ss.SSSSSS",
            "yyyy-MM-dd'T'HH:mm:ss.SSS",
            "yyyy-MM-dd'T'HH:mm:ss",
            "yyyy-MM-dd HH:mm:ss.SSSSSS",
            "yyyy-MM-dd HH:mm:ss",
            "yyyy-MM-dd HH:mm:ss.SSS",
    };

    private Timestamps() {
    }

    /**
     * @param raw the timestamp string returned by the API; may be null or empty
     * @return a readable local-time label, or the input unchanged when it cannot be
     *         parsed; empty string when there is no value at all
     */
    public static String readable(String raw) {
        if (raw == null) {
            return "";
        }
        String value = raw.trim();
        if (value.isEmpty()) {
            return "";
        }
        // SQLite stores naive UTC, so every pattern is parsed as UTC and then
        // rendered in the device's time zone.
        for (String pattern : PATTERNS) {
            SimpleDateFormat parser = new SimpleDateFormat(pattern, Locale.US);
            parser.setTimeZone(TimeZone.getTimeZone("UTC"));
            parser.setLenient(false);
            ParsePosition position = new ParsePosition(0);
            Date parsed = parser.parse(value, position);
            // Require the whole string to be consumed, so a short pattern cannot
            // silently match a prefix and drop the fractional seconds.
            if (parsed != null && position.getIndex() == value.length()) {
                return new SimpleDateFormat("d MMM yyyy, h:mm a", Locale.US).format(parsed);
            }
        }
        return value;
    }

    /**
     * @param raw the timestamp string returned by the API; may be null or empty
     * @return a short local date such as {@code 5 Oct}, an empty string when there is
     *         no value, or the input unchanged when it cannot be parsed
     */
    public static String shortDate(String raw) {
        if (raw == null || raw.trim().isEmpty()) {
            return "";
        }
        String readable = readable(raw);
        // readable() returns the input untouched when parsing failed.
        if (readable.equals(raw.trim())) {
            return raw.trim();
        }
        // "5 Oct 2026, 10:45 PM" -> "5 Oct"
        int comma = readable.indexOf(',');
        return comma > 0 ? readable.substring(0, comma).trim() : readable;
    }
}
