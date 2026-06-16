# ── Stage 1: Build React/Vite frontend ──────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /build

COPY mentorman-web/package*.json ./
RUN npm ci --prefer-offline

COPY mentorman-web/ .

# Baked into the SPA bundle at build time (non-secret, public value)
ARG VITE_CLERK_PUBLISHABLE_KEY
ENV VITE_CLERK_PUBLISHABLE_KEY=$VITE_CLERK_PUBLISHABLE_KEY
# Same-origin in prod — no cross-origin base URL needed
ENV VITE_API_BASE=""

RUN npm run build

# ── Stage 2: FastAPI backend ─────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

COPY unified-backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY unified-backend/ .

# Serve the built SPA from an explicit, stable path
COPY --from=frontend-builder /build/dist /spa
ENV SPA_DIST_DIR=/spa

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import httpx; r = httpx.get('http://localhost:8000/health'); assert r.status_code == 200"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
