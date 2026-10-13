package com.aistudio.hydroguard.wxqpzx.data.api;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/**
 * The client half of the photograph reference rule.
 *
 * <p>These assertions deliberately mirror the server's own
 * {@code STORAGE_KEY_PATTERN} in {@code app/core/storage.py}. If the two ever
 * drift apart the app would either refuse photos the server accepted or try to
 * fetch references the server will reject, so both sides are pinned here.</p>
 */
public class LostFoundPhotosTest {
    private static final String KEY = "0123456789abcdef0123456789abcdef";

    @Test
    public void acceptsEveryReferenceTheUploadEndpointIssues() {
        for (String extension : new String[]{"jpg", "png", "webp", "gif"}) {
            String reference = LostFoundPhotos.REFERENCE_PREFIX + KEY + "." + extension;
            assertTrue(reference, LostFoundPhotos.isServerPhotoReference(reference));
            assertEquals(KEY + "." + extension, LostFoundPhotos.keyOf(reference));
        }
    }

    @Test
    public void extractsOnlyTheKeyAndNeverTheWholeReference() {
        String reference = LostFoundPhotos.REFERENCE_PREFIX + KEY + ".jpg";
        assertEquals(KEY + ".jpg", LostFoundPhotos.keyOf(reference));
        assertFalse(LostFoundPhotos.keyOf(reference).startsWith("/"));
    }

    @Test
    public void rejectsAnythingTheServerDidNotIssue() {
        String[] rejected = {
                null,
                "",
                "https://cdn.example.com/photo.jpg",
                "http://10.0.2.2:8000" + LostFoundPhotos.REFERENCE_PREFIX + KEY + ".jpg",
                "/api/v1/hostel/notices",
                LostFoundPhotos.REFERENCE_PREFIX,
                // Traversal, wrong key shape, wrong extension, wrong case.
                LostFoundPhotos.REFERENCE_PREFIX + "../../data/hydroguard.db",
                LostFoundPhotos.REFERENCE_PREFIX + "hydroguard.db",
                LostFoundPhotos.REFERENCE_PREFIX + "not-a-uuid.jpg",
                LostFoundPhotos.REFERENCE_PREFIX + KEY + ".exe",
                LostFoundPhotos.REFERENCE_PREFIX + "0123456789ABCDEF0123456789ABCDEF.jpg",
                LostFoundPhotos.REFERENCE_PREFIX + KEY.substring(0, 31) + ".jpg",
                LostFoundPhotos.REFERENCE_PREFIX + KEY + ".jpg/../../other.jpg",
        };
        for (String reference : rejected) {
            assertFalse(String.valueOf(reference), LostFoundPhotos.isServerPhotoReference(reference));
            assertNull(String.valueOf(reference), LostFoundPhotos.keyOf(reference));
        }
    }
}
