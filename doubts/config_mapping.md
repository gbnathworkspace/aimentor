# Config & Secrets Mapping

| Config | .env Key | SSM Parameter | Source |
|--------|----------|---------------|--------|
| Anthropic API key | `ANTHROPIC_API_KEY` | `/claude-proxy/anthropic-api-key` | console.anthropic.com |
| Voyage AI API key | `VOYAGE_API_KEY` | `voyageapikey` | dash.voyageai.com |
| MongoDB URI | `MONGODB_URI` | — (EC2 uses IAM role, Lambda TBD) | MongoDB Atlas |
| Clerk publishable key | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | `/mentorman/clerk-publishable-key` | dashboard.clerk.com |
| Clerk secret key | `CLERK_SECRET_KEY` | `/mentorman/clerk-secret-key` | dashboard.clerk.com |
| Gmail address | `GMAIL_USER` | `/mentorman/gmail-user` | your Google account |
| Gmail app password | `GMAIL_APP_PASSWORD` | `/mentorman/gmail-app-password` | myaccount.google.com → App Passwords |
