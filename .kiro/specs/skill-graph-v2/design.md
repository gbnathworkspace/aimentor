# Skill Graph v2 — Evidence-Based Mastery Tracking

**Status:** Proposed
**Closes:** #3 (gap never recomputed), #9 (numeric mastery score)
**Owner:** Gopinath

---

## 1. Problem

The current skill graph produces one LLM verdict per session and throws away everything
that made it useful.

| Defect | Where | Consequence |
|---|---|---|
| `required_level = "intermediate"` hardcoded | `onboarding_bootstrap.py:~240` | `gap` is a pure function of `current_level`. Carries zero information. |
| LLM's 0–100 `gap` discarded | `skill_graph_repo.py:36` | Precise signal exists, is stored on the session, never reaches the graph. |
| `compute_gap()` re-buckets to 4 strings | `skill_graph_repo.py:48` | Real integer diff collapsed into `"none"/"small"/"medium"/"large"`. |
| Topics are flat, no edges | `skill_graph` collection | It is not a graph. Cannot infer prereqs, cannot compute a study frontier. |
| Every session writes an update | `apply_update()` | A session with no evidence still moves the level. Drift on noise. |
| No history, no confidence | schema | Cannot show a trajectory. Cannot distinguish 1 observation from 20. |
| Level assignment is unverifiable | `_build_combined_prompt` | Cannot unit-test "Haiku picks a level from a transcript". |

**Root cause:** the LLM is asked to do both judgment *and* aggregation. It should only
do judgment.

---

## 2. Target design

```
Session transcript
      │
      ▼  [1 Haiku call — the ONLY LLM step]
 Observations  ──────────────►  observations collection (append-only)
      │
      ▼  [pure arithmetic — zero LLM]
 Elo update
      │
      ▼
 skill_graph.sub_skills[*].mastery ∈ [0,1]
```

Three principles:

1. **The LLM reports what happened. Arithmetic decides what it means.**
2. **Observations are append-only.** They are the audit log and the replay tape.
3. **Silence is not evidence.** No observation → no update.

---

## 3. Schema

### 3.1 New collection: `topic_taxonomy`

Cached per topic, **not** per user. Decompose once, reuse for every user.

```json
{
  "topic": "React",
  "source": "curated" | "llm",
  "generated_at": "2026-07-14T...",
  "sub_skills": {
    "effects_lifecycle": {
      "name": "useEffect & cleanup",
      "target": 0.85,
      "difficulty": 0.7,
      "prereqs": ["component_state"],
      "probe": "This fetch fires twice in dev and leaks on unmount. Fix both."
    }
  }
}
```

`difficulty` lives here, **not** in the observation. See §5.3.

### 3.2 New collection: `observations` (append-only)

```json
{
  "_id": "...",
  "user_id": "...",
  "session_id": "...",
  "topic": "React",
  "sub_skill": "effects_lifecycle",
  "outcome": "correct" | "partial" | "incorrect" | "avoided",
  "hints_given": 1,
  "evidence": "\"it runs once\" — said with no dep array present",
  "source": "transcript" | "probe" | "objective",
  "created_at": "..."
}
```

Never updated. Never deleted. Indexed on `(user_id, sub_skill, created_at)`.

### 3.3 Rewritten: `skill_graph`

```json
{
  "user_id": "...",
  "topic": "React",
  "sub_skills": {
    "effects_lifecycle": {
      "mastery": 0.51,
      "n_obs": 6,
      "confidence": 0.86,
      "last_probed": "2026-07-14T...",
      "weak_areas": ["cleanup functions", "dependency arrays"],
      "history": [
        {"t": "2026-06-02T...", "mastery": 0.60},
        {"t": "2026-07-14T...", "mastery": 0.51}
      ]
    }
  }
}
```

**Deleted fields:** `current_level`, `required_level`, `gap`.
`target` and `prereqs` are not duplicated here — they live in `topic_taxonomy`.

---

## 4. Phase 1 — Decomposition

### 4.1 Curated taxonomy (head)

Hand-write `TOPIC_TAXONOMY` for the top ~10 topics that appear across the existing
`GOAL_KNOWLEDGE_BASE`. Deterministic, testable, zero cost.

**The atomicity test** — every sub-skill must pass:

> Can I write one question whose answer tells me, unambiguously, whether the
> student has this sub-skill?

- ✗ "Algorithms" — not atomic
- ✗ "Hooks" — a bundle
- ✓ "Identifying the DP state variable"
- ✓ "useEffect & cleanup"

**Decompose by concept, not API surface:**

| ✗ API-shaped | ✓ Concept-shaped |
|---|---|
| "useEffect" | "Knows why a missing dep array causes a stale closure" |
| "useMemo" | "Can identify when referential equality breaks memoization" |
| "Context API" | "Can decide when context beats prop drilling, and name the re-render cost" |

### 4.2 LLM decomposition (tail, cached)

```python
def get_sub_skills(topic: str) -> dict:
    if topic in TOPIC_TAXONOMY:                 # 1. curated
        return TOPIC_TAXONOMY[topic]

    cached = taxonomy_repo.find_one({"topic": topic})
    if cached:                                   # 2. cache hit
        return cached["sub_skills"]

    sub_skills = _decompose_via_llm(topic)       # 3. generate
    sub_skills = _validate_taxonomy(sub_skills)  #    validate
    taxonomy_repo.insert({"topic": topic, "sub_skills": sub_skills,
                          "source": "llm", "generated_at": now()})
    return sub_skills
```

Mirrors the existing `_lookup_goal_in_kb → _generate_topics_via_llm` fallback,
one level down.

### 4.3 Taxonomy validation (not optional)

The LLM will return cycles and orphan prereqs. Guard with Kahn's algorithm:

```python
def _validate_taxonomy(sub_skills: dict) -> dict:
    ids = set(sub_skills)

    for s in sub_skills.values():                        # drop orphan prereqs
        s["prereqs"] = [p for p in s["prereqs"] if p in ids]

    indeg = {k: len(v["prereqs"]) for k, v in sub_skills.items()}
    queue = [k for k, d in indeg.items() if d == 0]
    seen  = 0
    while queue:
        n = queue.pop()
        seen += 1
        for k, v in sub_skills.items():
            if n in v["prereqs"]:
                indeg[k] -= 1
                if indeg[k] == 0:
                    queue.append(k)

    if seen != len(sub_skills):
        raise ValueError("cycle in prereq graph")
    return sub_skills
```

---

## 5. Phase 2 — Observation extraction

### 5.1 Prompt

```
Read this transcript. Extract every moment where the student demonstrated
(or failed to demonstrate) one of these sub-skills:

{sub_skill_list_with_descriptions}

For each moment output:
  sub_skill:    which one (from the list; skip if none apply)
  outcome:      correct | partial | incorrect | avoided
  hints_given:  how many hints preceded the correct answer (0 if unaided)
  evidence:     the specific quote or behavior, one sentence

Rules:
- One observation per moment. A session may yield 0 or 15.
- "avoided" = changed the subject or said "I don't know". That is evidence too,
  weaker than "incorrect".
- Do NOT infer skill level. Do NOT summarize. Report only what is in the transcript.
- If the transcript shows nothing about a sub-skill, produce no row for it.
  Silence is not evidence.
- `evidence` MUST contain a phrase traceable to the transcript.

Return a JSON array. An empty array is a valid answer.
```

**Note what is absent:** no `level`, no `gap`, no `mastery`, no `difficulty`.

### 5.2 Observation validation

```python
def _validate_observations(obs_list, transcript, sub_skills):
    out = []
    for o in obs_list:
        if o["sub_skill"] not in sub_skills:
            continue                                  # hallucinated sub-skill
        if not _traceable(o["evidence"], transcript):
            continue                                  # hallucinated evidence
        out.append(o)

    # Cap 2 per sub_skill per session — an extractor returning 8 rows for one
    # sub-skill is re-reading the same exchange, not finding 8 events.
    by_skill = defaultdict(list)
    for o in out:
        by_skill[o["sub_skill"]].append(o)
    return [o for rows in by_skill.values() for o in rows[-2:]]
```

The quote-traceability check is the single highest-value guard. Hallucinated
evidence is the main vector for garbage entering the pipeline.

### 5.3 Why `difficulty` is NOT extracted

Asking one call to judge both outcome and difficulty correlates them — a model that
thinks the student did badly inflates the difficulty to explain it. Pre-assign
`difficulty` in the taxonomy (§3.1) and look it up:

```python
difficulty = sub_skills[obs.sub_skill]["difficulty"]
```

**Difficulty scale:**

| | Means |
|---|---|
| 0.2 | definition recall; given in any tutorial |
| 0.4 | standard textbook application |
| 0.6 | needs a non-obvious step, or a choice between approaches |
| 0.8 | edge cases, trade-offs, "why not the other approach" |
| 1.0 | novel constraint, no pattern to match |

---

## 6. Phase 3 — The update (zero LLM)

### 6.1 Elo

```python
OUTCOME_VALUE = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0, "avoided": 0.15}

def elo_update(mastery: float, difficulty: float, outcome: float, n_obs: int) -> float:
    expected = 1 / (1 + math.exp(-(mastery - difficulty) * 4))
    K        = 0.4 / (1 + n_obs * 0.15)
    return max(0.0, min(1.0, mastery + K * (outcome - expected)))
```

### 6.2 The full path

```python
def on_session_end(user_id, topic, transcript):
    sub_skills = get_sub_skills(topic)

    # ── LLM: once ──────────────────────────────────────────
    observations = extract_observations(transcript, sub_skills)      # Haiku
    observations = _validate_observations(observations, transcript, sub_skills)
    obs_repo.insert_many(observations)                               # append-only

    # ── Arithmetic: zero LLM ───────────────────────────────
    for obs in observations:
        node       = skill_graph_repo.get(user_id, topic, obs.sub_skill)
        difficulty = sub_skills[obs.sub_skill]["difficulty"]

        value = OUTCOME_VALUE[obs.outcome] * (0.85 ** obs.hints_given)
        node.mastery = elo_update(node.mastery, difficulty, value, node.n_obs)

        node.n_obs      += 1
        node.confidence  = 1 - 1 / (1 + node.n_obs)
        node.last_probed = now()
        node.history.append({"t": now(), "mastery": node.mastery})

        skill_graph_repo.save(node)
```

Nine lines replace `_build_combined_prompt` + Haiku call + JSON parse + Pydantic
validate + `compute_gap`.

### 6.3 Worked example

`effects_lifecycle`, prior `mastery=0.60`, `n_obs=5`. Observation: `incorrect`,
`hints_given=1`, taxonomy `difficulty=0.7`.

```
value    = 0.0 * 0.85^1                            = 0.00
expected = 1 / (1 + e^(-(0.60-0.70)*4))            = 0.40
K        = 0.4 / (1 + 5*0.15)                      = 0.229
mastery  = 0.60 + 0.229 * (0.00 - 0.40)            = 0.51
```

Same observation but `correct`:

```
value    = 1.0 * 0.85^1                            = 0.85
mastery  = 0.60 + 0.229 * (0.85 - 0.40)            = 0.70
```

### 6.4 Decay — applied on read, not write

```python
def effective_mastery(node, now):
    days      = (now - node.last_probed).days
    half_life = 30 * (1 + node.mastery * 2)      # stronger skills decay slower
    return node.mastery * (0.5 ** (days / half_life))
```

A 0.80 untouched for 60 days reads as ~0.63 and the Planner surfaces it for review.

---

## 7. Phase 4 — Planner: the frontier

The payoff of having edges. **Do not** pick the biggest gap — pick the biggest gap
whose prerequisites are already met.

```python
MASTERED = 0.65

def frontier(user_id, topic):
    sub_skills = get_sub_skills(topic)
    nodes      = skill_graph_repo.get_all(user_id, topic)

    return sorted(
        (sid for sid, spec in sub_skills.items()
         if all(nodes[p].mastery >= MASTERED for p in spec["prereqs"])
         and nodes[sid].mastery < spec["target"]),
        key=lambda sid: sub_skills[sid]["target"] - nodes[sid].mastery,
        reverse=True,
    )
```

**Why it matters** — React example:

- `render_performance` mastery 0.44, target 0.75 → biggest gap
- but its prereq `effects_lifecycle` is 0.42 → **blocked**
- `effects_lifecycle` prereq `component_state` is 0.74 ✓ → **on frontier**

So the next session teaches `useEffect`, not `memo`. Teaching memo to someone who
doesn't understand effect dependencies produces another partial-with-2-hints and
you learn nothing.

**Second selection mode — probe for uncertainty.** When `confidence < 0.5`, the
right move is to *measure*, not teach. Give the Teacher a directive:

> "Probe `effects_lifecycle` (mastery 0.42, confidence 0.4). Ask a difficulty-0.7
> question. Do not lead."

---

## 8. Phase 5 — Prompt injection (replaces the L2 block)

`prompts/mentor_v1.md` currently gets:

```
## Current Topic: {{topic}}
- Required Level: {{required_level}}
- Current Level: {{current_level}}
- Gap: {{gap}}
```

Replace with:

```
## Current Topic: React
Focus this session: useEffect & cleanup (mastery 0.42, 4 observations)
Blocked downstream: re-render control — do not teach until effects are solid

Strong: reconciliation & keys (0.71), useState (0.74)
Weak:   useEffect & cleanup (0.42), state architecture (0.44)
Stale:  props & composition — not probed in 47 days, review

Known weak areas in useEffect: dependency arrays, cleanup functions
```

Roughly the same token budget, vastly more actionable. The mentor now knows what to
teach, what *not* to teach, and what to review.

---

## 9. Phase 6 — Visualization

| View | Question it answers | Source |
|---|---|---|
| Radar (current vs target polygon) | Where am I strong/weak across this topic? | `mastery` + `target` |
| Bars with confidence bands | How solid is each estimate? | `mastery` + `confidence` |
| Trajectory line | Am I improving? | `history` |
| Prereq DAG, colored by mastery | What should I study next? | `prereqs` + `frontier()` |
| Heatmap (sub-skill × session) | Am I decaying? Plateaued? | `history` + `last_probed` |

The DAG is the highest-value view — it's the only one that answers "what next" and
it falls straight out of the graph structure.

---

## 10. Migration

No backfill of real mastery is possible — the evidence was never stored. Seed and
move on.

```python
LEVEL_SEED = {"beginner": 0.25, "intermediate": 0.50,
              "advanced": 0.75, "expert": 0.90}

def migrate(user_id):
    for old in skill_graph_repo.get_legacy(user_id):
        for sid in get_sub_skills(old.topic):
            new_repo.upsert(user_id, old.topic, sid, {
                "mastery":     LEVEL_SEED.get(old.current_level, 0.25),
                "n_obs":       0,          # ← seeded, not observed
                "confidence":  0.0,        # ← be honest: we know nothing
                "last_probed": None,
                "history":     [],
            })
```

`confidence = 0.0` is the honest value. It also means `K = 0.4` (max learning rate),
so the first real observation moves mastery hard and the seed washes out fast.

---

## 11. Build order

| # | Task | Depends on | Est |
|---|---|---|---|
| 1 | `TOPIC_TAXONOMY` for top 10 topics | — | 1 day |
| 2 | `topic_taxonomy` collection + `get_sub_skills()` + Kahn validator | 1 | 0.5 day |
| 3 | `observations` collection (append-only, indexed) | — | 0.5 day |
| 4 | `extract_observations()` — new Haiku prompt + traceability guard | 3 | 1 day |
| 5 | `elo_update()` + `apply_observation()` — pure, unit-tested | 3 | 0.5 day |
| 6 | Rewrite `skill_graph` schema + migration script | 2, 5 | 1 day |
| 7 | Delete `compute_gap`, `_build_combined_prompt`, `required_level` | 6 | 0.5 day |
| 8 | `frontier()` + Planner integration | 6 | 1 day |
| 9 | New L2 prompt block | 8 | 0.5 day |
| 10 | `effective_mastery()` decay on read | 6 | 0.5 day |
| 11 | Radar + DAG + trajectory views | 6 | 2 days |

**Ship 1–7 first.** That closes #3 and #9 and is independently valuable. 8–11 are
the payoff.

---

## 12. Tests

Everything below Phase 3 is pure and testable — which was impossible before.

```python
def test_hard_correct_moves_more_than_easy_correct():
    hard = elo_update(0.30, difficulty=0.8, outcome=1.0, n_obs=3)
    easy = elo_update(0.30, difficulty=0.2, outcome=1.0, n_obs=3)
    assert hard - 0.30 > easy - 0.30

def test_hints_discount_credit():
    unaided = OUTCOME_VALUE["correct"] * 0.85 ** 0
    hinted  = OUTCOME_VALUE["correct"] * 0.85 ** 3
    assert hinted == pytest.approx(0.614, abs=0.01)

def test_mastery_stabilizes_with_evidence():
    veteran = elo_update(0.70, 0.6, 0.0, n_obs=30)   # one bad answer
    novice  = elo_update(0.70, 0.6, 0.0, n_obs=1)
    assert abs(0.70 - veteran) < abs(0.70 - novice)  # one bad day ≠ collapse

def test_empty_session_produces_no_update():
    obs = extract_observations(transcript="user asked about pricing", sub_skills=SS)
    assert obs == []

def test_cycle_in_taxonomy_raises():
    with pytest.raises(ValueError):
        _validate_taxonomy({"a": {"prereqs": ["b"]}, "b": {"prereqs": ["a"]}})

def test_blocked_subskill_not_on_frontier():
    # render_performance has unmet prereq effects_lifecycle
    assert "render_performance" not in frontier(user_id, "React")
```

---

## 13. What this unlocks

**Replayability.** Observations are append-only and the update is a pure function.
Change `K` from 0.4 to 0.3, replay every observation for every user, recompute all
mastery. No LLM calls, no cost, seconds not hours. **You can tune the system.**
Today you cannot — the verdict is baked in at write time and the evidence is gone.

**Testability.** `elo_update` is a pure function of four floats. You cannot unit-test
"Haiku picks a level from a transcript".

**Cost.** One Haiku call per session, down from one per skill update. Taxonomy calls
are cached per topic, so they trend to zero.

**Honesty.** A mastery of 0.42 with `n_obs=1` renders with a wide confidence band.
A mastery of 0.42 with `n_obs=20` renders tight. The current system reports both
as "intermediate" with identical visual weight — which is the biggest lie in the
product.

---

## 14. The one-sentence version

`_build_combined_prompt` asks Haiku *"what level is this person?"* — a question with
no verifiable answer.

Replace it with *"what did this person demonstrate, and where in the transcript?"* —
a question with a checkable one, and let arithmetic do the rest.
