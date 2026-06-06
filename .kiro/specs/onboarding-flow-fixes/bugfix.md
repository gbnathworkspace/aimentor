# Bugfix Requirements Document

## Introduction

After the AI mentor finishes collecting the user's goal, deadline, skill level, and availability during onboarding, the app attempts to save the profile to the server via `/api/onboarding/complete`. This call fails — either due to an authentication issue, a database error, or a network problem — and the user sees the message "I couldn't save your profile — please check your connection and try again." Because the save fails, `setDone(true)` is never reached, the "Setup complete" card never renders, and the user is permanently stuck on the onboarding screen with no way to proceed into the app.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the AI completes onboarding data collection AND the `/api/onboarding/complete` POST request fails with a non-2xx response THEN the system shows an error message in the chat thread and the "Setup complete" card never appears

1.2 WHEN the AI completes onboarding data collection AND the `/api/onboarding/complete` POST request throws a network error THEN the system shows an error message in the chat thread and the user is stuck on the onboarding screen indefinitely

1.3 WHEN the user is stuck on the onboarding screen after a failed save THEN the system provides no way to retry the save without refreshing the page and repeating the entire conversation

### Expected Behavior (Correct)

2.1 WHEN the AI completes onboarding data collection AND the `/api/onboarding/complete` POST request fails THEN the system SHALL display an inline retry option so the user can attempt to save again without restarting the conversation

2.2 WHEN the `/api/onboarding/complete` POST request succeeds THEN the system SHALL transition to the "Setup complete" card and the user SHALL be able to click "Start your first session"

2.3 WHEN the `/api/onboarding/complete` POST request returns a 5xx server error THEN the system SHALL log the error server-side and return a meaningful error response body so the client can present an actionable message

### Unchanged Behavior (Regression Prevention)

3.1 WHEN onboarding data collection is still in progress (profile not yet complete) THEN the system SHALL CONTINUE TO display the conversational chat interface and accept user replies

3.2 WHEN the `/api/onboarding/complete` POST request succeeds on the first try THEN the system SHALL CONTINUE TO show the "Setup complete" card after a ~400ms delay

3.3 WHEN the user is already onboarded (profile exists) and loads the app THEN the system SHALL CONTINUE TO route directly to the chat screen, bypassing onboarding entirely

3.4 WHEN the onboarding conversation is ongoing and the user types a message THEN the system SHALL CONTINUE TO send the message to the AI and display the response correctly
