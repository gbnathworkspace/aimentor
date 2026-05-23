# API Keys & Accounts Required

Everything needed before implementation starts.

---

## 1. Anthropic
- Create account at console.anthropic.com
- Generate API key
- Used for: Claude Sonnet 4.6 (main LLM) + Claude Haiku 4.5 (lightweight calls)

## 2. Voyage AI
- Create account at dash.voyageai.com
- Generate API key
- Used for: voyage-4-lite (embeddings only, not for chat)
- Permanently free up to 200M tokens — effectively free at this scale

## 3. MongoDB Atlas
- Create account at mongodb.com/atlas
- Create a free cluster (M0 tier — permanently free, not just free tier)
- Whitelist IP (or allow all: 0.0.0.0/0 for dev)
- Create a database user
- Get the connection string

## 4. Clerk
- Create account at clerk.com
- Create a new application (name it mentorman)
- Enable Email + Google OAuth sign-in
- Get:
  - Publishable key (NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY)
  - Secret key (CLERK_SECRET_KEY)

## 5. Gmail SMTP
- Use an existing Google account
- Enable 2-Factor Authentication (required)
- Go to: Google Account → Security → 2-Step Verification → App Passwords
- Generate an App Password for "Mail"
- Save the 16-character password
- Used for: Nodemailer SMTP (not your regular Gmail login password)
- Switch to Resend later if app goes public (professional sender address)

## 6. AWS (existing account)
- Already set up — no new account needed
- Services used:
  - EC2 (existing t2.micro) — hosts Next.js frontend via nginx
  - Lambda — background jobs (alerts, ingestion pipeline)
  - SSM Parameter Store — stores all production secrets (permanently free)
- nginx config: mentorman.co.in → port 3001 (port 3000 is taken by seiyul.in)

## 7. Cloudflare (free)
- Create account at cloudflare.com
- Add domain mentorman.co.in
- Point DNS A record to EC2 IP
- Enable proxy (orange cloud) — handles SSL for free
- SSL mode: Flexible
- Also set up Email Routing: your@gmail.com receives mail at *@mentorman.co.in

## 8. Railway
- Create account at railway.app
- Connect GitHub account
- No key needed — deployment is done via GitHub integration
- Used for: Chat API backend (Node.js server handling LLM streaming)

---

## Environment Variables Summary

Local dev uses .env — production secrets go into AWS SSM Parameter Store.

```
# Anthropic
ANTHROPIC_API_KEY=

# Voyage AI
VOYAGE_API_KEY=

# MongoDB
MONGODB_URI=

# Clerk
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=
CLERK_SECRET_KEY=

# Gmail SMTP
GMAIL_USER=
GMAIL_APP_PASSWORD=
```
