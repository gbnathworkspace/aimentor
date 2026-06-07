import dns from 'dns'
import util from 'util'

// Windows DNS Client (svchost) refuses SRV queries from Node.js.
// Override before any module does a mongodb+srv:// lookup.
// dns.setServers() patches the global resolver but c-ares on Windows 24 still
// routes the first call through the old server. Directly replace dns.promises.resolveSrv
// with a custom Resolver pointed at 8.8.8.8 — used by the MongoDB driver for SRV lookup.
const srvResolver = new dns.Resolver()
srvResolver.setServers(['8.8.8.8', '8.8.4.4'])
;(dns.promises as Record<string, unknown>).resolveSrv =
  util.promisify(srvResolver.resolveSrv.bind(srvResolver))
;(dns.promises as Record<string, unknown>).resolveTxt =
  util.promisify(srvResolver.resolveTxt.bind(srvResolver))

export async function initNodeRuntime() {
  // 1. Validate all required env vars — throws with a clear message if missing
  const { env } = await import('@/lib/env')
  void env

  // 2. Establish MongoDB connection eagerly — crash here, not at the first user request
  const connectDB = (await import('@/lib/db/mongoose')).default
  try {
    await connectDB()
    console.log('✅ MongoDB connected')
  } catch (err) {
    console.error('❌ MongoDB connection failed at startup:', err)
    throw err
  }
}
