# Alerts and Proactive Nudges

## Decision
Two types: in-session nudges (inline, LLM-driven) and out-of-session
alerts (daily cron, email delivery).

## In-session nudges
No extra infrastructure. LLM handles inline during conversation.

```
Drift detection:
  "you've moved away from graphs — want to get back on track?"

Pace check at session end:
  "at this pace DP won't be covered before your deadline"

Episodic recall:
  "you were confused about this before — let me approach it differently"
```

## Out-of-session alerts — daily cron

```
Cron fires at 8am (user's timezone)
  │
  ▼
Fetch L1 + L2 from MongoDB
  │
  ▼
LLM prompt:
  "Here is the user's goal, deadline, skill graph,
   and last activity dates. Is there anything worth
   flagging today? If yes, produce one concise alert.
   If no, return null."
  │
  ├── null → do nothing
  └── alert produced → check last_email_sent
                          │
                          ├── sent in last 24hrs → skip
                          └── not sent → send email
```

One LLM call per user per day.

## Alert types

```
Type               Trigger                          Frequency
──────────────────────────────────────────────────────────────
Inactivity         no session in N days             once
Pace deviation     behind weekly target             weekly
Gap spike          eval score dropped               on event
Deadline warning   X weeks left                    at 8w,4w,2w,1w
Goal KB update     new topic added to goal          on event
Positive nudge     gap closed / milestone hit       on event
```

## Pace reasoning (LLM does this from L1 + L2)

```
Available hours = daily_availability × weeks_left
Required hours  = sum of estimated hours to close each gap
Actual hours    = logged from recent sessions

If actual < required by meaningful margin → alert fires
```

## Alert fatigue prevention

```
1. Max one alert per day
2. Only fire if something newly crossed a threshold
3. Include positive alerts — not just warnings
4. Snooze: user can snooze an alert type for N days
```

## Delivery
Email via Resend (see email_notifications.md).
In-app alert surfaces on next session open regardless.

## v2: event-driven alerts
For v1, daily cron is sufficient.
v2 should move to event-driven for precision:
- last_studied crosses N days threshold
- eval score drops below previous level
- deadline proximity hits a new threshold
- Goal KB refreshed with new topics
