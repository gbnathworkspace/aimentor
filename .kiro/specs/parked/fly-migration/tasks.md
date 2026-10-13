# Implementation Plan — Move production from EC2 to Fly.io

See `design.md` for the why and the `fly.toml` contents.

## Tasks

- [ ] 1. Fly account + app (console, no commit)
  - [ ] 1.1 Sign up at fly.io, add card; install flyctl (`iwr https://fly.io/install.ps1 -useb | iex`), `fly auth login`
  - [ ] 1.2 `fly apps create mentorman` (or another free name — update `app =` in fly.toml to match)
  - Verified by: `fly apps list` shows the app

- [ ] 2. Add `fly.toml` at repo root (commit)
  - Contents as in `design.md`
  - Verified by: `fly config validate` passes

- [ ] 3. Secrets + Atlas access (console, no commit)
  - [ ] 3.1 Copy values from SSM: `fly secrets set MONGODB_URI=... ANTHROPIC_API_KEY=... VOYAGE_API_KEY=... GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... JWT_SECRET=<from SSM /mentorman/jwt-secret> AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...`
  - [ ] 3.1a IAM user `mentorman-fly` with s3:GetObject/PutObject/DeleteObject on `mentorman-uploads-prod/*` only
  - [ ] 3.2 Atlas → Network Access → allow `0.0.0.0/0`
  - Verified by: `fly secrets list` shows all 8 names

- [ ] 4. First manual deploy (no commit)
  - `fly deploy --ha=false` (Clerk is unused — no build arg)
  - Verified by: `https://mentorman.fly.dev/health` returns 200, SPA loads, `fly status` shows exactly 1 machine

- [ ] 5. Switch CI/CD to Fly (commit)
  - Replace both jobs in `.github/workflows/deploy.yml` with one job: `superfly/flyctl-actions/setup-flyctl` → `flyctl deploy --remote-only --ha=false`
  - Add GitHub secret `FLY_API_TOKEN` (`fly tokens create deploy`)
  - Verified by: push to master → Actions run green → new release in `fly releases`

- [ ] 6. Cut the domain over (console, no commit)
  - [ ] 6.1 `fly ips allocate-v4 --shared`, `fly ips allocate-v6`
  - [ ] 6.2 `fly certs add mentorman.co.in`; in Cloudflare add the `_acme-challenge` CNAME it prints, then point `mentorman.co.in` CNAME → `mentorman.fly.dev` (proxied), SSL mode Full (strict)
  - Verified by: `fly certs show mentorman.co.in` reports issued; Google login + mentor chat + skill graph work on `https://mentorman.co.in`

- [ ] 7. Confirm suspend behaviour
  - Verified by: leave idle ~10 min, `fly status` shows machine `suspended`, then the site loads in <1s

- [ ] 8. Decommission AWS (console, no commit)
  - [ ] 8.1 Terminate the EC2 instance
  - [ ] 8.2 Release the Elastic IP
  - [ ] 8.3 Delete leftover EBS volumes/snapshots
  - [ ] 8.4 Remove `EC2_HOST`, `EC2_SSH_KEY`, `DOCKERHUB_*`, `VITE_CLERK_PUBLISHABLE_KEY` GitHub secrets; delete stale `start.sh`
  - Verified by: next AWS bill shows no EC2/EIP charges
