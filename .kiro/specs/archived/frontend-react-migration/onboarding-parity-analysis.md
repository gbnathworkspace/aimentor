# Onboarding Parity Analysis — Previous (Next.js) vs Now (React + FastAPI)

Investigates reported symptoms: **no suggestion chips** and **same response for every answer** during onboarding.

## Strategy diff

| Aspect | Previous (Next.js BFF) | Now (React SPA → FastAPI) |
|---|---|---|
| Endpoint | `POST /api/onboarding/chat` (Next route) | `POST /api/onboarding/chat` (FastAPI router) |
| Model | `claude-haiku-4-5-20251001`, `max_tokens: 350` | was `claude-sonnet-4-20250514` (**404**) → **fixed** to `claude-haiku-4-5-20251001` |
| System prompt | inline `SYSTEM`, interpolates `${TODAY}` for deadline; asks for `suggestions` + `onboarding_complete` blocks | `app/prompts/onboarding.md` — same block contract, but **static** (no today's date) |
| Response key | `{ text, complete, profile, suggestions }` | was `{ text, complete, profileData, suggestions }` (**wrong key**) → **fixed** to `profile` |
| Block parsing | `stripBlock` (indexOf) | `parse_onboarding_response` (regex) — same fenced markers |

## Bugs found and fixed (root causes of the original breakage)

1. **Model 404** — onboarding called a model not available on this account → 500, no reply. Fixed to the Haiku id the Next route uses.
2. **`profile` vs `profileData`** — the frozen UI reads `profile`; FastAPI returned `profileData`. A *key rename*, not a casing diff, so the casing adapter couldn't bridge it → `complete && profile` never fired → onboarding never completed. Fixed by renaming the backend field to `profile`.

## Empirical verification (live, 2-turn conversation against the running backend)

```
TURN1 text: "Hey there! Welcome to MentorMan! ... what's something you're looking to learn?"
TURN1 suggestions: ['Learn a programming language', 'Prepare for tech interviews', ...]   ← present
TURN2 text: "Awesome! ... FAANG DSA interviews in 3 months ... Where are you starting from?"
TURN2 suggestions: ["I'm a beginner ...", "I'm intermediate ...", "I'm advanced ..."]      ← present
same text? False     ← responses DO vary
```

**Conclusion:** the backend returns varied responses **with** suggestions. The fetch shim was unit-checked against this exact shape — `withBothCasings` preserves the `suggestions` array and `text`, and `{ suggestions: chips }` destructures to 3 chips. The verbatim component renders chips on `!busy && suggestions.length > 0`.

So backend ✅, shim ✅, component ✅ — all verified. A remaining "no suggestions / same response" in the browser is therefore a **client runtime/cache issue**, most likely a **stale cached bundle** (the served `index.html` is unhashed; the browser may reference an older JS chunk from before the fixes).

## Next step (needs the browser — cannot self-drive per project policy)

1. Hard-refresh `http://localhost:8000` (Ctrl+Shift+R) or open in a private window.
2. If still failing, capture the **Network** response for `POST /api/onboarding/chat` and any **Console** errors — that will show whether the browser is getting `text`+`suggestions` (cache) or erroring (runtime).

## Residual parity gaps (not the cause, but worth aligning)

- Deadline is captured as free text; the Next prompt interpolated `${TODAY}` to emit `YYYY-MM-DD`. The FastAPI `onboarding.md` is static → deadlines may be relative ("3 months") rather than dates.
- `max_tokens` 1024 vs Next's 350 (cosmetic).
