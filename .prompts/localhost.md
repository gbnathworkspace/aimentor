Start both the backend and frontend locally, each in its own background process, then confirm both are up.

- Backend — FastAPI on :8000
  cd unified-backend && .venv/Scripts/uvicorn app.main:app --reload --port 8000
- Frontend — Vite SPA on :5173
  cd mentorman-web && npm run dev

Run each in the background (don't block on either), then check:
- http://localhost:8000/docs responds
- http://localhost:5173 responds

Report the two URLs once both are confirmed up.

Then open the frontend in Chrome:
  start chrome "http://localhost:5173"

