# Session End Flow

## Decision
At session end, one LLM call produces two outputs simultaneously —
a narrative summary for the Vector DB and a structured update for MongoDB.

## The single prompt

```
System: You are a session summarizer. Produce two outputs:

        1. narrative_summary: 3-5 sentences describing what happened,
           what was strong, what was weak. Write it so a future
           semantic search on the topic can find it.

        2. skill_update: JSON with topic, last_studied, current_level,
           gap, weak_areas, strong_areas, mock_score (if any).

        Return both in:
        {
          "narrative_summary": "...",
          "skill_update": { ... }
        }

User: [full session transcript]
```

One call. Two outputs. Each goes to the right store.

## Write flow

```
LLM returns JSON
  │
  ├── narrative_summary
  │       │
  │       ▼
  │   embed with OpenAIEmbeddings (LangChain)
  │       │
  │       ▼
  │   upsert via MongoDBAtlasVectorSearch.add_texts() (LangChain)
  │   (stored with metadata: topic, date, category, type)
  │
  └── skill_update
          │
          ▼
      MongoDB upsert
      find node where topic matches
      merge new signals in
```

## Metadata stored alongside vector

```json
{
  "date": "2026-05-22",
  "type": "mock_test",
  "topic": "AWS",
  "topic_category": "cloud"
}
```

Used for pre-filtering before semantic search.
Prevents "graph databases" (AWS topic) from surfacing when
user asks about "graph algorithms" (DSA topic).

## Partial sessions (no mock score, just doubts)
The LLM handles missing fields gracefully — mock_score is omitted
if the session had no evaluation. MongoDB upsert merges only
the fields that exist, preserving prior signal values.

## Abrupt close handling
See session_management.md for the two-phase checkpoint approach
that prevents summary loss on abrupt tab close.
