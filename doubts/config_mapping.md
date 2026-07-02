# Config & Secrets Mapping

| Config | .env Key | SSM Parameter | Source |
|--------|----------|---------------|--------|
| Anthropic API key | `ANTHROPIC_API_KEY` | `/claude-proxy/anthropic-api-key` | console.anthropic.com |
| Voyage AI API key | `VOYAGE_API_KEY` | `voyageapikey` | dash.voyageai.com |
| MongoDB URI | `MONGODB_URI` | — (EC2 uses IAM role, Lambda TBD) | MongoDB Atlas |
| JWT Secret | `JWT_SECRET` | `/mentorman/jwt-secret` | Generated (openssl rand -hex 32) |
| Google OAuth Client ID | `GOOGLE_CLIENT_ID` | `/mentorman/google-client-id` | console.cloud.google.com |
| Google OAuth Client Secret | `GOOGLE_CLIENT_SECRET` | `/mentorman/google-client-secret` | console.cloud.google.com |
| GitHub OAuth Client ID | `GITHUB_CLIENT_ID` | `/mentorman/github-client-id` | github.com/settings/developers |
| GitHub OAuth Client Secret | `GITHUB_CLIENT_SECRET` | `/mentorman/github-client-secret` | github.com/settings/developers |
| Gmail address | `GMAIL_USER` | `/mentorman/gmail-user` | your Google account |
| Gmail app password | `GMAIL_APP_PASSWORD` | `/mentorman/gmail-app-password` | myaccount.google.com → App Passwords |
