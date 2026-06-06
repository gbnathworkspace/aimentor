import { NextResponse } from 'next/server'
import connectDB from '@/lib/db/mongoose'
import mongoose from 'mongoose'

// ─── Health check endpoint ────────────────────────────────────────────────────
// GET /api/health
//
// Returns the status of all critical infrastructure dependencies.
// Designed to be polled by uptime monitors (e.g. UptimeRobot, Vercel Cron)
// so infra failures are caught by monitoring, not by users hitting onboarding.
//
// Response shape:
//   200 { status: "ok",      db: "connected", uptime: 123 }
//   503 { status: "degraded", db: "error: ...", uptime: 123 }

export async function GET() {
  const uptime = Math.floor(process.uptime())
  const checks: Record<string, string> = {}
  let healthy = true

  // ── MongoDB ──────────────────────────────────────────────────────────────────
  try {
    await connectDB()
    // readyState: 0=disconnected 1=connected 2=connecting 3=disconnecting
    const state = mongoose.connection.readyState
    if (state === 1) {
      checks.db = 'connected'
    } else {
      checks.db = `unexpected readyState: ${state}`
      healthy = false
    }
  } catch (err) {
    checks.db = `error: ${err instanceof Error ? err.message : String(err)}`
    healthy = false
  }

  const status = healthy ? 'ok' : 'degraded'
  const httpStatus = healthy ? 200 : 503

  return NextResponse.json({ status, ...checks, uptime }, { status: httpStatus })
}
