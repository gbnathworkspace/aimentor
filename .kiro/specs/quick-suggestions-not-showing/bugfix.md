# Bugfix Requirements Document

## Introduction

The regular mentor chat UI (`ChatPanel` in `chat.tsx`) is missing quick suggestion chips above the composer input. This is existing functionality — the onboarding flow (`Onboarding` in `screens.tsx`) already renders suggestion chips returned from the API above its composer. In the regular chat, no suggestions are fetched, stored, or rendered, so users see only the bare text input with no quick-reply shortcuts.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the mentor sends a message in the regular chat UI THEN the system does not display quick suggestion chips above the composer input area

1.2 WHEN the `/api/mentor` endpoint returns suggestion chips alongside the reply text THEN the system ignores the `suggestions` field and no chips are rendered

1.3 WHEN the user is viewing the regular chat UI (`ChatPanel`) THEN the system shows only the text area composer with no suggestion chips, even when context-appropriate suggestions are available

### Expected Behavior (Correct)

2.1 WHEN the mentor sends a message in the regular chat UI THEN the system SHALL display the quick suggestion chips returned by the API above the composer input area

2.2 WHEN the `/api/mentor` endpoint returns a `suggestions` array alongside the reply text THEN the system SHALL render each suggestion as a clickable chip above the textarea

2.3 WHEN the user clicks a suggestion chip in the regular chat UI THEN the system SHALL send that suggestion text as the user's next message and clear the chips

2.4 WHEN the user starts typing in the composer THEN the system SHALL clear the displayed suggestion chips (consistent with the onboarding behavior)

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the user sends a message manually by typing and pressing Enter or clicking the send button THEN the system SHALL CONTINUE TO send the typed message correctly

3.2 WHEN the composer is in evaluation mode THEN the system SHALL CONTINUE TO show the evaluation-mode flag banner and graded-answer behavior without interference from suggestions

3.3 WHEN the onboarding flow displays suggestion chips THEN the system SHALL CONTINUE TO function exactly as before, unaffected by changes to the regular chat UI

3.4 WHEN the mentor API returns no `suggestions` field or an empty array THEN the system SHALL CONTINUE TO render the composer without suggestion chips (no empty chip area visible)

3.5 WHEN the assistant is busy generating a reply THEN the system SHALL CONTINUE TO not display suggestion chips during the loading/typing state (consistent with onboarding behavior)
