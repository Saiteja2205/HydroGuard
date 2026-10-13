package com.aistudio.hydroguard.wxqpzx;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import com.aistudio.hydroguard.wxqpzx.data.config.IssueWorkflow;

import org.junit.Before;
import org.junit.Test;

import java.util.Arrays;
import java.util.List;

/**
 * The Hostel Operations screen builds its buttons from {@link IssueWorkflow}.
 *
 * <p>These assertions mirror {@code hydroguard-backend/tests/test_issue_workflow.py} so a change
 * to either side that lets the UI offer a transition the backend would reject with 409 fails the
 * build. The lifecycle an administrator must be able to drive is Open → Acknowledged →
 * In progress → Waiting → Resolved → Reopened.</p>
 */
public class IssueWorkflowTest {

    @Before
    public void resetWorkflow() {
        IssueWorkflow.reset();
    }

    @Test
    public void submittedReportsPresentAsOpen() {
        assertEquals("Open", IssueWorkflow.statusLabel("SUBMITTED"));
        assertEquals("Acknowledged", IssueWorkflow.statusLabel("ACKNOWLEDGED"));
        assertEquals("In progress", IssueWorkflow.statusLabel("IN_PROGRESS"));
        assertEquals("Waiting", IssueWorkflow.statusLabel("WAITING"));
        assertEquals("Resolved", IssueWorkflow.statusLabel("RESOLVED"));
        assertEquals("Reopened", IssueWorkflow.statusLabel("REOPENED"));
        assertEquals(IssueWorkflow.OPEN, "SUBMITTED");
    }

    @Test
    public void aNewReportCanOnlyBeAcknowledgedStartedOrParked() {
        assertEquals(Arrays.asList("ACKNOWLEDGED", "IN_PROGRESS", "WAITING"),
                IssueWorkflow.nextStatuses("SUBMITTED"));
    }

    @Test
    public void inProgressOffersResolveBeforeWaiting() {
        assertEquals(Arrays.asList("RESOLVED", "WAITING"), IssueWorkflow.nextStatuses("IN_PROGRESS"));
    }

    @Test
    public void aWaitingIssueCanBeResumedOrResolved() {
        List<String> next = IssueWorkflow.nextStatuses("WAITING");
        assertTrue(next.contains("IN_PROGRESS"));
        assertTrue(next.contains("RESOLVED"));
        assertEquals("Resume work", IssueWorkflow.actionLabel("WAITING", "IN_PROGRESS"));
    }

    @Test
    public void resolvedIssuesCanBeClosedOrReopened() {
        assertEquals(Arrays.asList("CLOSED", "REOPENED"), IssueWorkflow.nextStatuses("RESOLVED"));
        assertTrue(IssueWorkflow.isReopenable("RESOLVED"));
        assertTrue(IssueWorkflow.isReopenable("CLOSED"));
        assertFalse(IssueWorkflow.isReopenable("IN_PROGRESS"));
        assertFalse(IssueWorkflow.isReopenable("SUBMITTED"));
    }

    @Test
    public void impossibleMovesAreRefused() {
        assertFalse(IssueWorkflow.canTransition("SUBMITTED", "RESOLVED"));
        assertFalse(IssueWorkflow.canTransition("SUBMITTED", "CLOSED"));
        assertFalse(IssueWorkflow.canTransition("IN_PROGRESS", "CLOSED"));
        assertFalse(IssueWorkflow.canTransition("RESOLVED", "IN_PROGRESS"));
        assertTrue(IssueWorkflow.canTransition("SUBMITTED", "ACKNOWLEDGED"));
        assertTrue(IssueWorkflow.canTransition("IN_PROGRESS", "RESOLVED"));
    }

    @Test
    public void resolvingIsTheOnlyStepThatNeedsASummary() {
        assertTrue(IssueWorkflow.requiresResolution("RESOLVED"));
        assertFalse(IssueWorkflow.requiresResolution("WAITING"));
        assertFalse(IssueWorkflow.requiresResolution("ACKNOWLEDGED"));
        assertFalse(IssueWorkflow.requiresAssignee("IN_PROGRESS"));
        assertTrue(IssueWorkflow.requiresAssignee("ASSIGNED"));
    }

    @Test
    public void actionLabelsAreHumanReadable() {
        assertEquals("Acknowledge", IssueWorkflow.actionLabel("SUBMITTED", "ACKNOWLEDGED"));
        assertEquals("Start work", IssueWorkflow.actionLabel("ACKNOWLEDGED", "IN_PROGRESS"));
        assertEquals("Mark waiting", IssueWorkflow.actionLabel("IN_PROGRESS", "WAITING"));
        assertEquals("Resolve", IssueWorkflow.actionLabel("IN_PROGRESS", "RESOLVED"));
        assertEquals("Close", IssueWorkflow.actionLabel("RESOLVED", "CLOSED"));
        assertEquals("Reopen", IssueWorkflow.actionLabel("RESOLVED", "REOPENED"));
    }

    @Test
    public void everyTargetIsItselfAKnownStatus() {
        List<String> known = Arrays.asList(
                "SUBMITTED", "ACKNOWLEDGED", "ASSIGNED", "IN_PROGRESS",
                "WAITING", "RESOLVED", "CLOSED", "REOPENED");
        for (String from : known) {
            for (String to : IssueWorkflow.nextStatuses(from)) {
                assertTrue(from + " must not point at unknown status " + to, known.contains(to));
            }
        }
    }

    @Test
    public void aMissingOrMalformedServerPayloadNeverBlanksTheWorkflow() {
        int before = IssueWorkflow.nextStatuses("SUBMITTED").size();
        IssueWorkflow.applyServerJson(null);
        IssueWorkflow.applyServerJson("");
        IssueWorkflow.applyServerJson("   ");
        IssueWorkflow.applyServerJson("null");
        IssueWorkflow.applyServerJson("{not valid json");
        assertEquals(before, IssueWorkflow.nextStatuses("SUBMITTED").size());
        assertEquals("Open", IssueWorkflow.statusLabel("SUBMITTED"));
        assertEquals(3, IssueWorkflow.nextStatuses("SUBMITTED").size());
    }
}
