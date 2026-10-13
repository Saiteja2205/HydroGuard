package com.aistudio.hydroguard.wxqpzx.data.api;

import java.util.regex.Pattern;

/**
 * Recognises photograph references that this backend issued itself.
 *
 * <p>The rule mirrors the server's own {@code STORAGE_KEY_PATTERN} in
 * {@code app/core/storage.py}: a reference is only usable when it is exactly
 * the upload endpoint's path plus a 32-character lowercase hex UUID and a known
 * image extension. Anything else — an {@code http://} URL, a traversal, a
 * client-invented path — is refused before it reaches the network, so a
 * malformed {@code image_url} can never be fetched or displayed.</p>
 */
public final class LostFoundPhotos {
    public static final String REFERENCE_PREFIX = "/api/v1/hostel/lost-found/photos/";

    private static final Pattern STORAGE_KEY =
            Pattern.compile("^[0-9a-f]{32}\\.(?:jpg|png|webp|gif)$");

    private LostFoundPhotos() {
    }

    /** True when {@code imageUrl} is a reference this server could serve. */
    public static boolean isServerPhotoReference(String imageUrl) {
        if (imageUrl == null || !imageUrl.startsWith(REFERENCE_PREFIX)) return false;
        return STORAGE_KEY.matcher(imageUrl.substring(REFERENCE_PREFIX.length())).matches();
    }

    /**
     * The storage key to request, or {@code null} when {@code imageUrl} is not
     * a reference this server issued.
     */
    public static String keyOf(String imageUrl) {
        if (!isServerPhotoReference(imageUrl)) return null;
        return imageUrl.substring(REFERENCE_PREFIX.length());
    }
}
