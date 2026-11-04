# Requirements: MCQ Quiz ("Quiz me")

## Introduction

"Quiz me" used to produce free-form questions: open-ended prose, generic
quick-reply cards, a different shape every time, nothing graded. This feature
makes every quiz question a fixed-template MCQ, rendered inline by a minimal
on-brand card, graded in code, delivered **one question at a time** with room
to discuss a question before moving on. Question style is grounded in a web
search of how MCQs on the topic are commonly written.

## Decisions (brainstorm with Gopinath, 2026-11-04)

| # | Topic | Decision |
|---|-------|----------|
| 1 | Grading | **Code grades.** The model puts the correct option id in the block; the app compares instantly. Answer visible in the payload — accepted. |
| 2 | Delivery | **One question per turn.** Answer → instant result → discuss it in chat, or click **Next question** above the composer. |
| 3 | Placement | **Inline in the chat thread** — the card is a mentor message; discussion scrolls below it. |
| 4 | Feedback | **Instant reveal** — tapping an option locks it in and shows right/wrong + explanation. No Submit step. |
| 5 | Setup | **Zero setup** — 5 questions; mentor picks subtopics/difficulty from history. Free-text overrides ("quiz me on DI, 10 questions") still honored. |
| 6 | Question style | **Researched per topic.** Before Q1, the mentor web-searches how MCQs on this topic are commonly written and adopts that style (see Req 5). |
| 7 | Quality rule | **Wrong answers = real mistakes.** Every distractor is tied to a named misconception people actually have; a wrong pick tells the mentor *what* was misunderstood. |
| 8 | Card look | **Minimal, on-brand** — same visual language as the existing mentor question card (`onb-card`, yellow accent). Header is just `2 / 5`. No subtopic chip, no difficulty dots. |
| 9 | Options layout | **Vertical list**, one option per row, full text. |
| 10 | Progress | **`2 / 5` text only.** |
| 11 | End of quiz | Summary card with **score + per-subtopic bars**, **review of wrong answers** (your pick vs correct + why), and a **"Teach me what I missed"** button. |
| 12 | "I don't know" | Always offered; counts as not-correct. |
| 13 | Bad block | Malformed/off-template block is dropped (plain text shown) — never a broken card. |

Explicitly **not** chosen (raised, declined): select-then-Submit, focused full-panel quiz
mode, segmented/running-score progress, 2×2 grid, second-model quality check,
adaptive difficulty, spaced repetition of missed questions, setup picker.

## Requirement 1: Fixed MCQ template

1. Every quiz question SHALL be emitted as exactly one ```` ```json quiz ```` block:
   ```json
   {
     "q": 2, "of": 5,
     "subtopic": "async/await",
     "stem": "One direct question, one central idea.",
     "code": "optional C# snippet, ≤ 10 lines",
     "options": [{"id": "A", "text": "..."}, {"id": "B", "text": "..."}, {"id": "C", "text": "..."}, {"id": "D", "text": "..."}],
     "answer": "B",
     "why": "1-2 sentences: why the correct answer is correct.",
     "misconceptions": {"A": "the mistake behind A", "C": "...", "D": "..."}
   }
   ```
   `subtopic` is kept for scoring/summary only — not shown on the card.
2. Item-writing rules (Haladyna et al. 2002): stem phrased as a question; no NOT/EXCEPT;
   no "all/none of the above" or "A and D"; no giveaway words (always/never); options of
   similar length; correct letter varies; no repeated subtopic within a quiz unless the
   learner asked for one topic.
3. `misconceptions` SHALL have an entry for **every** wrong option (Decision 7). Missing → block invalid.
4. Backend validates (4 options A–D, `answer` ∈ ids, non-empty `stem`/`why`, misconception per wrong
   option, `1 ≤ q ≤ of`). Invalid → dropped (Decision 13).
5. The block is stripped from visible text, never streamed raw, persisted on the assistant message as `quiz`.
6. Prose outside the block: at most one short line. No mentor chatter ("Good — this confirms…").

## Requirement 2: Quiz card (minimal, inline, instant)

1. Rendered inline as the mentor's message, in the existing `onb-card` style: spark icon, `q / of`,
   stem, optional code block, options A–D as a vertical list, an **I don't know** link.
2. Tapping an option immediately (no LLM call) locks the card, marks the pick ✓/✗ with an icon (not
   colour alone), highlights the correct option, and shows `why` plus the misconception for a wrong pick.
3. Exactly one answer per card; read-only afterwards.
4. The pick is persisted (`quiz.picked`) — survives reload; visible to the mentor in later turns.

## Requirement 3: One-by-one flow with discussion

1. After the current question is answered, a **Next question** bar appears above the composer.
2. The user MAY type instead (e.g. "why not C?"); the mentor discusses that question and SHALL NOT emit a
   new quiz block. The bar stays available.
3. **Next question** sends a message that makes the mentor emit question `q+1`.
4. On the last question the bar reads **Finish quiz** → the run is scored **in code** (per-subtopic %
   correct), written to the skill graph via `record_diagnostic_verdict`, and the summary card is shown (Req 6).
5. While a quiz is in progress, turns run in DIAGNOSTIC mode regardless of the tactic selector, and the
   verdict tool is NOT offered to the model (offered, it records a score instead of asking/answering).
6. The bar is hidden while a reply streams and while the current question is unanswered.

## Requirement 4: Mentor context

1. In LLM history, an assistant message with a `quiz` is rendered as the question, options, correct
   answer, and the learner's pick + the misconception behind it (or "not answered yet").

## Requirement 5: Researched question style (Decision 6)

1. On the quiz's start turn, the mentor SHALL run a web search for how MCQs on this topic/subtopics are
   commonly written (e.g. "C# async await multiple choice questions"), before emitting Q1.
2. From the results it SHALL derive a short **style brief** (2-4 lines: question types typically used,
   e.g. predict-the-output / fill-the-missing-line / spot-the-bug / scenario; snippet size; typical traps).
3. The brief SHALL be persisted on the Q1 quiz (`quiz.styleBrief`) and re-supplied on every later turn of
   that quiz, so the search runs **once per quiz**, not per question.
4. If the search fails or returns nothing useful, the mentor proceeds with the Req 1.2 rules alone.
5. The search is invisible to the user apart from the existing tool-activity indicator.

## Requirement 6: End-of-quiz summary card (Decision 11)

1. Shown as the Finish turn's mentor message, rendered as a card:
   - score `3 / 5`;
   - one bar per subtopic with its % correct;
   - **Review**: each missed question — stem, your pick, correct answer, the misconception behind your pick;
   - **Teach me what I missed** button → sends a message starting a lesson on the weakest subtopic.
2. Score and per-subtopic numbers come from code (Req 3.4), not the model. The model contributes at most
   one line of commentary.

## Out of scope

- Hiding the answer from the client (Decision 1).
- Everything listed under "Explicitly not chosen".
