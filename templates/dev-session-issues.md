# Dev Session Issues Log

| # | Label | Side | Issue |
|---|---|---|---|
| 1 | **Missing deps** | Frontend | `mentorman-web` had no `node_modules` — `vite` not found, needed `npm install` |
| 2 | **Missing env** | Frontend | `mentorman-web` had no `.env` — app threw on startup |
| 3 | **Missing Python packages** | Backend | FastAPI backend missing `tiktoken` / `voyageai` — needed `pip install -r requirements.txt` |
| 4 | **PATH issue** | Backend | `uvicorn` not on PATH — had to use `python -m uvicorn` |
| 5 | **Incomplete backend `.env`** | Backend | Missing `CORS_ORIGINS` — CORS would've silently failed |
| 6 | **Double blank screen** | Frontend | `if (!profileLoaded) return null` caused a second invisible wait after auth loaded |
| 7 | **Missing CSS keyframe** | Frontend | No `@keyframes spin` in global CSS — shell loading spinner would've been broken |
