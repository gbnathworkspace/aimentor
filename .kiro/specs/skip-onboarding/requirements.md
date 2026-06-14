# Requirements Document

## Introduction

This feature adds the ability for users to skip the onboarding flow in MentorMan and proceed directly to the mentor chat interface. Currently, the conversational onboarding (which collects goal, deadline, availability, and seeds the skill graph) is mandatory with no bypass option. Some users prefer to explore the app immediately and provide profile details later. This feature introduces a visible skip mechanism, handles default profile creation for skipped users, ensures the mentor can function gracefully without a full profile, and provides a path to complete onboarding later.

## Glossary

- **Onboarding_Flow**: The conversational 4-phase setup process that collects goal, deadline, current level, and availability from the user and bootstraps the Core Profile and Skill Graph
- **Skip_Button**: A visible UI control on the onboarding screen that allows the user to bypass the remaining onboarding steps
- **Core_Profile**: The MongoDB Layer 1 document storing goal, deadline, and availability for a user (always injected into LLM context)
- **Skill_Graph**: The MongoDB Layer 2 collection of per-topic proficiency nodes seeded during onboarding or evaluation
- **Default_Profile**: A minimal Core Profile created with placeholder values when a user skips onboarding
- **Profile_Status**: A field indicating whether onboarding was completed fully, partially, or skipped entirely
- **Onboarding_Banner**: A persistent UI prompt shown to users who skipped onboarding, encouraging them to complete their profile
- **Chat_Interface**: The main mentor chat view at the `/session/[id]` route where users interact with the AI mentor
- **Settings_Page**: The `/settings` route where users can view and modify their profile, including completing skipped onboarding

## Requirements

### Requirement 1: Skip Button Visibility

**User Story:** As a new user, I want to see a clear option to skip onboarding, so that I can start using the mentor chat immediately without completing setup.

#### Acceptance Criteria

1. WHILE the Onboarding_Flow is active, THE Skip_Button SHALL remain visible and enabled on the onboarding screen across all onboarding phases (Goal & Timeline, Current State, File Upload, and Availability)
2. THE Skip_Button SHALL display the label "Skip" using a text-only or outline button style with font size no larger than the primary action elements, so that it is visually subordinate to the main conversation flow
3. THE Skip_Button SHALL be positioned within the top navigation bar of the onboarding screen, in the same container as the progress indicator
4. WHILE the Onboarding_Flow is active AND the user has not yet sent any message, THE Skip_Button SHALL be enabled and responsive to click and keyboard activation
5. THE Skip_Button SHALL be keyboard-focusable and expose an accessible name of "Skip" to assistive technologies

### Requirement 2: Skip Action and Redirect

**User Story:** As a new user, I want to be redirected to the mentor chat after skipping onboarding, so that I can start exploring the app right away.

#### Acceptance Criteria

1. WHEN the user activates the Skip_Button, THE Onboarding_Flow SHALL display a confirmation prompt asking the user to confirm they want to skip setup, presenting exactly two actions: a confirm option and a cancel option
2. WHILE the confirmation prompt is displayed, THE Onboarding_Flow SHALL prevent interaction with the onboarding conversation beneath the prompt
3. WHEN the user confirms the skip action, THE Onboarding_Flow SHALL redirect the user to the Chat_Interface within 1 second
4. IF the redirect to the Chat_Interface fails due to session creation error or network unavailability, THEN THE Onboarding_Flow SHALL display an error message indicating the redirect failed and allow the user to retry or return to onboarding
5. WHEN the user cancels the skip confirmation, THE Onboarding_Flow SHALL dismiss the confirmation prompt and return the user to the onboarding conversation at the same point they left off, with all previously displayed messages and input preserved
6. WHEN the user confirms the skip action, THE Onboarding_Flow SHALL terminate the current onboarding conversation without sending further messages to the LLM

### Requirement 3: Default Profile Creation

**User Story:** As the system, I want to create a minimal profile for users who skip onboarding, so that the application has valid data structures to operate with.

#### Acceptance Criteria

1. WHEN the user confirms the skip action, THE System SHALL create a Default_Profile with the Profile_Status set to "skipped" and persist it to the database before redirecting the user to the Chat_Interface
2. WHEN the System creates a Default_Profile, THE Default_Profile SHALL contain a goal value of "exploring" as a placeholder
3. WHEN the System creates a Default_Profile, THE Default_Profile SHALL contain a daily_availability value of "1 hour" as a placeholder
4. WHEN the System creates a Default_Profile, THE Default_Profile SHALL set the deadline field to null
5. WHEN the user skips onboarding, THE System SHALL NOT create any Skill_Graph documents, leaving the Skill_Graph collection with zero nodes for that user until the first evaluation or manual profile completion
6. IF the Default_Profile creation fails due to a database error, THEN THE System SHALL display an error message indicating that setup could not be completed and SHALL NOT redirect the user away from the Onboarding_Flow

### Requirement 4: Graceful Mentor Degradation

**User Story:** As a user who skipped onboarding, I want the mentor to still function and be helpful, so that I can have a useful conversation even without a full profile.

#### Acceptance Criteria

1. WHILE the Profile_Status is "skipped", THE Chat_Interface SHALL allow the user to send messages up to 2000 characters and receive LLM-generated responses with the same streaming behavior and response latency as a fully onboarded user
2. WHILE the Skill_Graph is empty, THE Chat_Interface SHALL assemble LLM context using only the system prompt and the conversation window (last 6 turns), omitting the Skill Graph and Episodic Memory layers entirely
3. WHILE the Profile_Status is "skipped", THE System SHALL include a system prompt addendum instructing the LLM that the user has not completed onboarding, that no goal or skill data is available, and that all advice must remain topic-general without referencing specific deadlines, skill gaps, or personalized study plans
4. IF the LLM context assembly encounters a missing Core_Profile field (goal, targetDate, or availability), THEN THE System SHALL omit that field from the assembled context and proceed with the LLM call using only the fields that are present
5. IF all Core_Profile fields (goal, targetDate, and availability) are missing, THEN THE System SHALL assemble context using only the system prompt with the skipped-onboarding addendum and the conversation window, without failing or returning an error to the user

### Requirement 5: Onboarding Completion Later

**User Story:** As a user who skipped onboarding, I want to complete my profile setup later, so that I can get personalized mentoring when I am ready.

#### Acceptance Criteria

1. WHILE the Profile_Status is "skipped", THE Settings_Page SHALL display a "Complete Setup" section with a call-to-action button labeled "Complete Setup"
2. WHEN the user activates the "Complete Setup" action from the Settings_Page, THE System SHALL navigate the user to the Onboarding_Flow
3. WHEN the user completes the deferred Onboarding_Flow, THE System SHALL update the Profile_Status from "skipped" to "complete" and bootstrap the Skill_Graph
4. WHEN the user completes the deferred Onboarding_Flow, THE System SHALL redirect the user back to the Chat_Interface within 1 second
5. IF the user abandons the deferred Onboarding_Flow without completing it, THEN THE Profile_Status SHALL remain "skipped" and the user SHALL be returned to the Settings_Page
6. WHEN the Profile_Status changes to "complete", THE Settings_Page SHALL no longer display the "Complete Setup" section

### Requirement 6: Onboarding Reminder Banner

**User Story:** As a user who skipped onboarding, I want to be gently reminded to complete my profile, so that I understand the value of personalized mentoring.

#### Acceptance Criteria

1. WHILE the Profile_Status is "skipped", THE Onboarding_Banner SHALL be displayed at the top of the Chat_Interface above the message area, without overlapping or obscuring chat messages or input controls
2. THE Onboarding_Banner SHALL contain a message of no more than 120 characters explaining that completing setup enables personalized mentoring, a link labeled "Complete Setup" that navigates to the Onboarding_Flow, and a visible dismiss button
3. WHEN the user activates the dismiss button on the Onboarding_Banner, THE System SHALL hide the banner for the remainder of the current browser session, where the banner remains hidden across page refreshes until the browser session ends (all tabs for the application are closed)
4. WHEN the user activates the "Complete Setup" link in the Onboarding_Banner, THE System SHALL navigate the user to the Onboarding_Flow
5. IF the Profile_Status changes to "complete", THEN THE Onboarding_Banner SHALL be removed from the Chat_Interface on the next page load or navigation event without requiring a full browser session restart

### Requirement 7: Partial Onboarding Preservation

**User Story:** As a user who provided some information before skipping, I want my partial responses to be preserved, so that I do not have to repeat information when I complete setup later.

#### Acceptance Criteria

1. WHEN the user skips onboarding after providing partial responses (goal, deadline, current level, or availability), THE System SHALL store any profile fields already extracted by the onboarding LLM in the Default_Profile document
2. WHEN the user returns to complete onboarding later, THE Onboarding_Flow SHALL skip phases whose corresponding fields are already present in the Default_Profile and begin from the first incomplete phase
3. IF the user provided a goal before skipping, THEN THE Default_Profile SHALL use the user-provided goal instead of the "exploring" placeholder
4. IF the user provided a deadline before skipping, THEN THE Default_Profile SHALL store the user-provided deadline instead of null
5. IF the user provided availability before skipping, THEN THE Default_Profile SHALL use the user-provided availability instead of the "1 hour" placeholder
