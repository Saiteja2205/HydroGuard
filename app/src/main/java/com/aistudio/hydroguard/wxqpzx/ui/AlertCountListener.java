package com.aistudio.hydroguard.wxqpzx.ui;

/**
 * Reports the number of alert records the server most recently returned for the selected node, so
 * the navy top application bar can show an alerts badge that reflects real data.
 *
 * <p>Implemented by the activity that hosts the bar. The count is never estimated: it is the size
 * of the list the API actually produced, and it is cleared when a later fetch fails, because
 * continuing to display a figure the app can no longer substantiate would be inventing a
 * measurement.</p>
 */
public interface AlertCountListener {

    /**
     * @param count alert records from the most recent successful fetch, or {@code 0} when the
     *              fetch failed or returned no records
     */
    void onAlertCountChanged(int count);
}
