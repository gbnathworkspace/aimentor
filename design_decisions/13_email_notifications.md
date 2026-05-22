# Email Notifications

## Decision
Out-of-session alerts delivered via email using Gmail SMTP (Nodemailer).
One email per day max. Single user — no unsubscribe needed for v1.

## Trigger flow

```
Daily cron produces alert
  │
  ▼
Check email_preferences.enabled
  │
  ├── false → skip
  └── true
        │
        ▼
      Check last_email_sent
        │
        ├── sent in last 24hrs → skip (prevent spam)
        └── not sent
              │
              ▼
            Send via Gmail SMTP (Nodemailer)
            Update last_email_sent
```

## Email format

```
From:    mentor@aimentor.app
Subject: [specific, not generic — see subject lines below]

Hey [name],

[one paragraph: what the alert is about, specific numbers]

Today's suggested session:
  [concrete recommendation with estimated time]

[Start Session →]  ← CTA button

──────────────────
[one line pace summary]

– Your AI Mentor

[Unsubscribe]
```

## Subject lines by alert type

```
Inactivity        "You haven't studied in 3 days"
Pace deviation    "You're falling behind this week"
Gap spike         "Your graphs score dropped — let's fix it"
Deadline warning  "8 weeks to your goal — here's where you stand"
Goal KB update    "New topic added to 20 LPA prep"
Positive nudge    "You closed the arrays gap this week"
```

## User document fields

```json
{
  "email": "user@gmail.com",
  "email_preferences": {
    "enabled": true,
    "frequency": "daily",
    "snooze_until": null
  },
  "last_email_sent": "2026-05-21T08:00:00"
}
```

## Unsubscribe
Single user in v1 — no unsubscribe link needed.
Add when app opens to multiple users.

## Email service
Gmail SMTP via Nodemailer — free, no account setup beyond Gmail.
500 emails/day limit — irrelevant for single user.
Migrate to Resend when app opens to multiple users.
