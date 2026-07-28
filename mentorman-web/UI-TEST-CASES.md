# MentorMan Web — UI / Functional Test Cases

Scope: the uncommitted working-tree changes (Settings picker modals, chat + settings
document upload, SubtopicWeightsModal rework, sidebar collapse logo, typing label).
Base URL: `http://localhost:5173` (Vite) → FastAPI on `:8000`.

Pass = expected result observed AND no new console error / failed network call.

---

## 1. Sidebar (TopicSidebar / ArchivedTopics)

| ID | Steps | Expected |
|----|-------|----------|
| SB-01 | Load app, sidebar expanded | Full wordmark `/logo-full.svg` renders, no broken-image icon |
| SB-02 | Click collapse chevron | Sidebar narrows; logo swaps to `/logo-mark.svg`, stays inside the rail (no clipping/overflow) |
| SB-03 | While collapsed, click "Archived" entry point, then collapse again | Archived view shows the mark, not the wordmark |
| SB-04 | Collapse, then navigate chat → dashboard → settings | Collapsed state persists across views; nav icons still clickable |
| SB-05 | Collapse with an admin account | Admin nav button is hidden while collapsed (`onNav && !collapsed && isAdmin`), reappears on expand |

## 2. Chat screen

| ID | Steps | Expected |
|----|-------|----------|
| CH-01 | Open a topic | Message history loads; composer enabled; no console errors |
| CH-02 | Type text, press Send | Message posts; typing indicator shows label "Thinking, may check the web for current info…" above the three dots, inside the bubble, not overflowing |
| CH-03 | Send with empty composer | Send button disabled |
| CH-04 | Hover the chart icon in the header | Tooltip reads "Where should you focus?" (was "Subtopic weight breakdown") |
| CH-05 | New/unsaved topic (no topicId) | Attach button is **not** rendered (`canAttach` false); text send still works |
| CH-06 | In a saved topic, click Attach, pick a `.pdf` | AttachmentPreview appears above the textarea with filename + size; Send becomes enabled even with empty text |
| CH-07 | Attach an unsupported file (`.exe`) | File shown with an inline error; it is excluded from send; Send stays disabled if it is the only file |
| CH-08 | Attach a file >max size | Size error shown, file not sendable |
| CH-09 | Attach valid file + type a note, press Send | Attachments clear, note clears, upload flow starts; a system line "Uploading 1 document: x.pdf" appears in the timeline |
| CH-10 | Remove a staged file via its × | Row disappears; Send re-disables when no valid files and no text |
| CH-11 | Toggle "skip review" then send | Payload carries `skipReview: true` (verify in Network tab on `POST /api/documents/upload`) |
| CH-12 | Send a chat message while an upload is polling | Chat stays fully usable — composer not blocked, upload indicator keeps polling |

## 3. Document upload flow (chat + settings)

| ID | Steps | Expected |
|----|-------|----------|
| DU-01 | Submit an upload | Phase `uploading` → spinner + "Uploading files..."; then `polling` with stage label; `role="status"` announced |
| DU-02 | Job completes with proposals | DocumentProposalCard renders per-proposal field, reason, source filename; Accept / Dismiss / Accept all present |
| DU-03 | Click Accept on one proposal | Row flips to accepted immediately (optimistic); `POST /api/profile/pending-changes/{field}/accept` fires |
| DU-04 | Force that endpoint to fail (offline) | Row reverts to pending — no silently-lost state |
| DU-05 | Click Accept all | All pending rows flip; one request per proposal; any failure reverts only that row |
| DU-06 | Job completes with zero proposals | `no_proposals` informational card, with Close |
| DU-07 | Job fails | `failed` card with Retry upload + Retry analysis; retry-analysis returns the card to polling |
| DU-08 | Kill the backend, then upload | `network_error` card with the message and retry; after 3 consecutive failures retry is suppressed |
| DU-09 | Close the card | Flow resets to idle, nothing left rendered in the timeline |
| DU-10 | Upload from **Settings → Memory** composer | Same flow renders inside the settings panel, not the chat panel |

## 4. Settings → Memory tab

| ID | Steps | Expected |
|----|-------|----------|
| ST-01 | Open Settings with pending changes present | "Suggested updates" group renders **collapsed**, with the count badge and a chevron; body hidden |
| ST-02 | Click the header | Expands to show sub-text + rows; `aria-expanded` flips; icon becomes × |
| ST-03 | Accept / Dismiss a suggestion | Row resolves, badge count decrements |
| ST-04 | Profile with `profile_status = 'skipped'` | "Complete Your Profile" card shows with a × in the corner; text is not covered by the × |
| ST-05 | Click the × | Card disappears; switch tabs and return — stays dismissed; reload page — stays dismissed (sessionStorage); new browser session — reappears |
| ST-06 | Private/incognito with storage blocked | No crash — dismiss still works for the session |

### 4a. Context modal

| ID | Steps | Expected |
|----|-------|----------|
| CX-01 | Click the Context value | Modal opens, focused; current context row has a check + accent styling |
| CX-02 | Pick a different preset | Saves immediately; trigger button label updates to the new preset's label |
| CX-03 | Type a custom context, press Enter / Add | Custom value becomes active and appears as an extra row above the 5 presets |
| CX-04 | Force `PATCH /api/profile` to fail | Selection reverts and "Save failed — try again" shows |
| CX-05 | Press Escape, and separately click the backdrop | Both close the modal; clicking inside does not |
| CX-06 | Enter 60+ chars in the custom field | Capped at 60 (`maxLength`) |

### 4b. Situations modal

| ID | Steps | Expected |
|----|-------|----------|
| SI-01 | Click the Situation value ("Not set" when empty) | Modal opens; header shows "N entries" with correct singular/plural |
| SI-02 | Add a situation | It is prepended, becomes active (filled dot), saves; the Settings trigger shows its text |
| SI-03 | Add a duplicate of an existing entry | No duplicate row — the existing one moves to top and becomes active |
| SI-04 | Click a non-active row | It becomes active; only one dot filled at a time |
| SI-05 | Hover a row and click × | Row removed; if it was active, the first remaining entry becomes active; removing the last one leaves active `null` and the trigger reads "Not set" |
| SI-06 | Type into search | List filters case-insensitively; no matches shows "No matches."; empty list shows "No situations yet." |
| SI-07 | Reopen the modal | Search box and add box are cleared |
| SI-08 | Add a 120-char entry | Capped at 120; long text wraps inside the row without breaking layout |
| SI-09 | Add a 21st entry | Oldest entry is dropped, new one kept (cap 20) |
| SI-10 | Keyboard only: Tab through a row | Remove button must be reachable **and visible** when focused — see defect UI-04 |

### 4c. Focus areas modal

| ID | Steps | Expected |
|----|-------|----------|
| FA-01 | Click the Topics value | Modal opens; trigger reads "N areas" / "1 area" / "Not set" correctly |
| FA-02 | Add a focus area | Appended to the list, saved, trigger count increments |
| FA-03 | Add an existing value again | Moves to the end, no duplicate |
| FA-04 | Remove an area | Removed and saved; no "active" dot concept in this modal |
| FA-05 | Search / Escape / backdrop | Same behaviour as Situations |
| FA-06 | With 20 areas already, add a 21st | **Currently fails — see defect UI-02** |

### 4d. Memory composer

| ID | Steps | Expected |
|----|-------|----------|
| MC-01 | Type text, press Enter | Sent as a natural-language memory edit; result line appears |
| MC-02 | Attach a doc with no text, press Send | Document upload submitted (not a memory edit); attachments and text cleared |
| MC-03 | Attach a doc **and** type text, press Send | Upload submitted with the text as `message`; text is not also sent as a memory edit |
| MC-04 | Empty composer, no attachments | Send disabled |
| MC-05 | While a memory edit is in flight | Input, attach and send all disabled |

## 5. "Where should you focus?" modal (SubtopicWeightsModal)

| ID | Steps | Expected |
|----|-------|----------|
| SW-01 | Open from the chat header chart icon | Title "Where should you focus?", subtitle "for {topic}"; setup phase |
| SW-02 | Profile with focus areas | Up to 2 "YOUR FOCUS" cards (near-duplicates collapsed), plus context card, plus "Just revising", plus "Something else"; the "may only partly overlap" note shows |
| SW-03 | Profile with `learning_context = self_directed` | No context card |
| SW-04 | Profile with no focus areas | No focus cards and no overlap note |
| SW-05 | Nothing selected | "Start preparing →" disabled with the hint "Pick one to continue" |
| SW-06 | Arrow keys inside the radiogroup | Selection moves and focus follows, wrapping at both ends; `aria-checked` tracks |
| SW-07 | Select "Something else" | Textarea appears and autofocuses; Start stays disabled until non-blank text |
| SW-08 | Start with a goal card | `POST /api/topic/{id}/subtopic-weights` sends `goalIntent` and **no** `workEvidence`; loading text "Figuring out where to focus…" |
| SW-09 | Start with custom evidence | Request sends `workEvidence`, no `goalIntent` |
| SW-10 | Result renders | Rows sorted descending; bar widths match the percentages; values sum to ~100.0% |
| SW-11 | Backend returns `needsPairwise` | Equal split shown instead of a blocking ranking step |
| SW-12 | Click Edit → drag the slider | Label cycles Very focused → Focused → Balanced → Flatter → Very even; bars reshape live; row order does **not** reshuffle |
| SW-13 | Click Reset in edit mode | Slider returns to 1 / "Balanced"; Reset disables at default |
| SW-14 | Click "Reorder manually" | Rank list appears with up/down buttons; first row's up and last row's down are disabled |
| SW-15 | Reorder, click "Apply order" | Re-queries with the full round-robin pairwise list; new weights render |
| SW-16 | Rank-mode hint copy | **Currently misleading — see defect UI-03** |
| SW-17 | Click "Start over" | Back to setup, evidence text and selection cleared |
| SW-18 | Backend 500 / network drop | Error phase with the message and a Back button |
| SW-19 | Escape / backdrop click | Closes; reopening starts fresh at setup |
| SW-20 | Topic with many subtopics (15+) | Dialog scrolls within `max-height: 80vh`; header stays legible; no page-level horizontal scroll |

## 6. Regression sweep (unchanged screens)

| ID | Screen | Expected |
|----|--------|----------|
| RG-01 | Onboarding (no profile) | Auto-routes to onboarding; finishing creates a topic and lands in chat |
| RG-02 | Deferred onboarding from Settings | Opens full-screen; Abandon returns to Settings |
| RG-03 | Dashboard | Renders with profile; "start topic" opens a fresh chat |
| RG-04 | Admin users (admin only) | Table renders; non-admins never see the entry point |
| RG-05 | Archived topics | List loads; selecting one opens it in chat and returns the sidebar to Topics |
| RG-06 | Narrow viewport (1024px, 768px) | Modals stay within `calc(100vw - 32px)`; settings rows and composer do not overflow horizontally |
