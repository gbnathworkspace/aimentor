// ─── Next.js instrumentation ──────────────────────────────────────────────────
// This file runs once when the Next.js server starts (Node.js runtime only).
// Use it to validate config and establish infrastructure connections at boot
// time — so failures surface in the server logs before any user request fires.
//
// Docs: https://nextjs.org/docs/app/building-your-application/optimizing/instrumentation

export async function register() {
  if (process.env.NEXT_RUNTIME !== 'nodejs') return

  // Windows DNS Client (svchost) refuses SRV queries from Node.js.
  // Override before any module does a mongodb+srv:// lookup.
  // Windows: Node.js uses 127.0.0.1 (Windows DNS Client) which refuses SRV queries.
  // dns.setServers() patches the global resolver but c-ares on Windows 24 still
  // routes the first call through the old server. Directly replace dns.promises.resolveSrv
  // with a custom Resolver pointed at 8.8.8.8 — used by the MongoDB driver for SRV lookup.
  const dns = await import('dns')
  const util = await import('util')
  const srvResolver = new dns.Resolver()
  srvResolver.setServers(['8.8.8.8', '8.8.4.4'])
  ;(dns.promises as Record<string, unknown>).resolveSrv =
    util.promisify(srvResolver.resolveSrv.bind(srvResolver))
  ;(dns.promises as Record<string, unknown>).resolveTxt =
    util.promisify(srvResolver.resolveTxt.bind(srvResolver))

  // 1. Validate all required env vars — throws with a clear message if missing
  const { env } = await import('@/lib/env')
  void env // importing triggers the Zod parse; if it throws, server won't start

  // 2. Establish MongoDB connection eagerly — crash here, not at the first user request
  const connectDB = (await import('@/lib/db/mongoose')).default
  try {
    await connectDB()
    console.log('✅ MongoDB connected')
  } catch (err) {
    // Log clearly and rethrow — server startup should fail loud, not silently
    console.error('❌ MongoDB connection failed at startup:', err)
    throw err
  }
}
