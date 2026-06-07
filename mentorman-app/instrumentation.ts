// ─── Next.js instrumentation ──────────────────────────────────────────────────
// This file runs once when the Next.js server starts (Node.js runtime only).
// Use it to validate config and establish infrastructure connections at boot
// time — so failures surface in the server logs before any user request fires.
//
// Docs: https://nextjs.org/docs/app/building-your-application/optimizing/instrumentation

export async function register() {
  if (process.env.NEXT_RUNTIME !== 'nodejs') return

  // Delegate all Node.js-only work to a separate module so Turbopack does not
  // attempt to bundle Node built-ins (dns, util) for the Edge runtime, which
  // would crash the compilation worker with repeated "not supported in Edge Runtime" errors.
  const { initNodeRuntime } = await import('./instrumentation.node')
  await initNodeRuntime()
}
