# API Keys & Accounts Required

Everything needed before implementation starts.

---

## 1. Anthropic
- Create account at console.anthropic.com
- Generate API key
- Used for: Claude Sonnet 4.6 (main LLM) + Claude Haiku 4.5 (lightweight calls)

## 2. OpenAI
- Create account at platform.openai.com
- Generate API key
- Used for: text-embedding-3-small (embeddings only, not for chat)

## 3. MongoDB Atlas
- Create account at mongodb.com/atlas
- Create a free cluster (M0 tier)
- Whitelist IP (or allow all: 0.0.0.0/0 for dev)
- Create a database user
- Get the connection string

## 4. Clerk
- Create account at clerk.com
- Create a new application (name it Guru)
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

## 6. Vercel
- Create account at vercel.com
- Connect GitHub account
- No key needed — deployment is done via GitHub integration

## 7. Railway
- Create account at railway.app
- Connect GitHub account
- No key needed — deployment is done via GitHub integration

---

## Environment Variables Summary

Once all accounts are set up, these go into .env:

```
# Anthropic
ANTHROPIC_API_KEY=

# OpenAI
OPENAI_API_KEY=

# MongoDB
MONGODB_URI=

# Clerk
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=
CLERK_SECRET_KEY=

# Gmail SMTP
GMAIL_USER=
GMAIL_APP_PASSWORD=
```
