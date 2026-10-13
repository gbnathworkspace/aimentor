# Design — Move production from EC2 to Fly.io

## Why

EC2 t2.micro + Elastic IP runs 24/7 (~$13/mo) for an app that is only opened for
interview demos and occasional personal use.

## Requirements

1. Near-$0 when idle.
2. Instant (<1s) first load when an interviewer opens the link.
3. `mentorman.co.in` keeps working (Google OAuth redirect stays valid).
4. Demo flow works end to end: login, mentor chat, topics, skill graph.

## Decision: Fly.io Machines with `auto_stop_machines = "suspend"`

The machine is suspended after a few minutes of no traffic, with its memory
saved to a snapshot. The next request restores it in ~0.3–1s, already warm.

| Option | Idle cost | First load | Rejected because |
|---|---|---|---|
| EC2 stop/start | ~$4.5/mo | site down unless started | dead link when the interviewer opens it later |
| Cloud Run | ~$0 | 3–8s | CPU throttled after response → post-turn hook, compaction, logout checkpoint stall |
| Oracle Always Free | $0 | instant | signup/capacity friction, idle reclamation, two firewalls |
| **Fly suspend** | **<$1/mo** | **<1s** | — |

Fly gives a real VM with full CPU while awake, so the `asyncio.create_task`
post-response work (`mentor_agent.py`, `session_compactor.py`,
`session_save_handler.py`, `auth/router.py`) keeps working unchanged.

## Accepted trade-offs

- Uploads stay on S3 (`mentorman-uploads-prod`) via a scoped IAM user's keys as Fly secrets (no instance role on Fly). Cost ~$0.
- First wake after a deploy or host migration is a ~5s cold start, not a snapshot restore.
- Single machine (`--ha=false`), no staging.
- Domain stays proxied by Cloudflare (CNAME → mentorman.fly.dev, `_acme-challenge` CNAME for the Fly cert, SSL Full strict).
- MongoDB Atlas network access opened to `0.0.0.0/0` (Fly egress IPs aren't fixed); the URI password still gates access.

## fly.toml (repo root)

```toml
app = "mentorman"
primary_region = "sin"

[build]
  dockerfile = "unified-backend/Dockerfile"

[env]
  FRONTEND_URL = "https://mentorman.co.in"
  OAUTH_REDIRECT_URI = "https://mentorman.co.in/api/auth/oauth/callback"
  STORAGE_BACKEND = "s3"
  S3_BUCKET_NAME = "mentorman-uploads-prod"
  S3_REGION = "ap-south-1"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = "suspend"
  auto_start_machines = true
  min_machines_running = 0

  [[http_service.checks]]
    path = "/health"
    interval = "30s"
    timeout = "5s"

[[vm]]
  cpu_kind = "shared"
  cpus = 1
  memory = "1gb"
```

## Parking lot
