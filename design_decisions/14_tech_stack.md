# Tech Stack

## Final Stack

```
Layer              Tech                      Notes
──────────────────────────────────────────────────────────────────
Frontend           Next.js (App Router)      Chat UI, streaming
UI Library         shadcn/ui                 Composable, own the code
Auth               Self-hosted (JWT + OAuth)  FastAPI + React
Backend            FastAPI (Python)          Ingestion + LLM orchestration
LLM (main)         Claude Sonnet 4.6         Reasoning + responses
LLM (lightweight)  Claude Haiku 4.5          Intent check, titles, drift
Embeddings         Voyage AI voyage-4-lite   200M free tokens, better quality than OpenAI
Database           MongoDB Atlas             Structured + vector (one DB)
Email              Gmail SMTP (Nodemailer)   Free, single user v1
Cron               AWS Lambda + EventBridge  Daily alert trigger, permanently free
File processing    PyMuPDF + pandas          PDF extraction + CSV parsing
Hosting (FE)       EC2 (nginx + PM2)         Existing t2.micro, port 3001
Hosting (BE)       Railway                   Chat API (Node.js), handles LLM streaming
Secrets (prod)     AWS SSM Parameter Store   SecureString, default KMS key, free
DNS / SSL          Cloudflare (free)         Proxies mentorman.co.in → EC2, handles HTTPS
```

---

## Key Decisions

### One DB for structured + vector (MongoDB Atlas)
Atlas Vector Search handles Layer 3 (episodic memory) inside the
same database as Layer 1 and Layer 2. No dedicated Vector DB needed.

Single collection query can filter by metadata and search by vector simultaneously:
```json
{
  "$vectorSearch": {
    "index": "session_embedding_index",
    "path": "embedding",
    "queryVector": [...],
    "numCandidates": 50,
    "limit": 5,
    "filter": { "topic_category": "DSA" }
  }
}
```

Tradeoff: retrieval quality slightly below dedicated Pinecone at scale.
At this scale (one user's sessions) the difference is negligible.
Migrate to Pinecone only if retrieval quality becomes a measurable problem.

### Two Claude models
Sonnet 4.6 for all main reasoning — context assembly, responses, session summaries,
skill graph updates, onboarding, evaluation loop.

Haiku 4.5 for lightweight fast calls where quality doesn't need to be high:
- Intent check ("does this message need past context? yes/no")
- Session title generation
- Drift detection check
- Alert null check in daily cron

Keeps cost low without compromising response quality.

### Voyage AI over OpenAI for embeddings
Same price ($0.02/1M tokens), better retrieval quality, and no extra account.
Already in Anthropic ecosystem. voyage-4-lite is more than sufficient for
session summaries and doubts at this scale.

### EC2 over Vercel for frontend
- Already paying for t2.micro — no extra cost
- Vercel has per-request billing with no hard cap — bill shock risk on attacks
- EC2 is flat rate — traffic spikes don't change the bill
- nginx + PM2 on EC2 is more resume-worthy than Vercel deployment
- Port 3001 used (port 3000 is taken by seiyul.in on same instance)

### MongoDB auth via IAM Role (no credentials on EC2)
EC2 has an IAM role attached. That role ARN is added to MongoDB Atlas as an
AWS IAM user. EC2 connects to MongoDB without any username/password or URI
in SSM — the role proves identity automatically.

Lambda will use a separate IAM role added to Atlas the same way (TBD when
Lambda functions are built).

Local dev uses a password-based Atlas user (gopi-dev) with URI stored in .env only.

### FastAPI over Next.js API routes
Python is the right language for the ingestion pipeline:
- PyMuPDF for PDF extraction
- pandas for CSV parsing
- LangChain / direct Anthropic SDK for LLM orchestration
- Cleaner separation of concerns as complexity grows

Next.js handles the UI and thin session management layer.
FastAPI handles all heavy lifting.

### Self-hosted auth
Custom JWT + refresh token system built on FastAPI.
Handles email/password, OTP, Google OAuth, and GitHub OAuth.
Replaced Clerk to eliminate proxy issues and reduce external dependencies.

---

## Session Document Schema (MongoDB)

Structured fields + embedding vector in one document:
```json
{
  "session_id": "abc123",
  "user_id": "gopinath",
  "topic": "graphs",
  "topic_category": "DSA",
  "type": "topic_session",
  "date": "2026-05-22",
  "title": "BFS/DFS revision",
  "summary": "User revised BFS and DFS. Strong on cycle detection.
              Struggled with negative weight cycles.",
  "embedding": [0.023, -0.041, 0.019, "...1536 dimensions"],
  "skill_update": {
    "current_level": "medium",
    "weak_areas": ["negative weight cycles"],
    "strong_areas": ["BFS", "DFS"]
  }
}
```

---

## MongoDB Collections

```
users              Core profile (Layer 1) + email preferences
skill_graph        Per-topic nodes (Layer 2), one doc per user per topic
sessions           Session transcripts + summaries + embeddings (Layer 3)
alerts             Generated alerts, delivery status
goal_kb            Goal Knowledge Base, required levels per goal per topic
```

---

## EC2 Setup

```
Instance       t2.micro (existing, Amazon Linux 2023)
nginx          1.28.0 — running, enabled on boot
Node.js        v20.20.2
PM2            7.0.1 — registered as systemd service
Port           3001 (3000 is taken by seiyul.in)
nginx config   /etc/nginx/conf.d/mentorman.conf
```

nginx config for mentorman:
```nginx
server {
    listen 80;
    server_name mentorman.co.in www.mentorman.co.in;

    location / {
        proxy_pass http://localhost:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

---

## Free Tier / Cost Summary

```
MongoDB Atlas M0     512MB storage, shared cluster — permanently free
Voyage AI            200M tokens/month — permanently free
AWS Lambda           1M requests/month — permanently free
AWS SSM              Standard parameters — permanently free
Clerk                10,000 MAU — removed, replaced with self-hosted auth
Gmail SMTP           500 emails/day — free
Railway              $5/month credit — chat API
EC2 t2.micro         ~$8-10/month — already paying, no extra cost
Cloudflare           Free plan — DNS + SSL
Anthropic            Pay per use — only real variable cost
```

---

## What to migrate in v2

```
MongoDB Atlas Vector Search → Pinecone        if retrieval quality degrades at scale
Railway Cron               → dedicated queue  if alert volume grows (BullMQ / Celery)
Gmail SMTP                 → Resend           when app opens to multiple users
```
