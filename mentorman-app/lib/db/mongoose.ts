import dns from 'dns'
import mongoose from 'mongoose'
import { env } from '@/lib/env'

// Windows DNS Client (svchost) doesn't forward SRV queries correctly to Node.js,
// causing ECONNREFUSED on mongodb+srv:// lookups. Force a real resolver.
dns.setServers(['8.8.8.8', '8.8.4.4'])

// ─── MongoDB connection singleton ─────────────────────────────────────────────
// Next.js runs in a serverless context — connections must be cached across
// hot reloads in dev and across invocations in prod.
// Pattern: store connection promise on the global object.
//
// MONGODB_URI is validated at module load via lib/env.ts — if it's missing
// the server crashes at boot (instrumentation.ts), not at the first user request.

declare global {
  // eslint-disable-next-line no-var
  var _mongooseConn: Promise<typeof mongoose> | undefined
}

async function connectDB(): Promise<typeof mongoose> {
  if (global._mongooseConn) {
    return global._mongooseConn
  }

  global._mongooseConn = mongoose.connect(env.MONGODB_URI, {
    bufferCommands: false,
    serverSelectionTimeoutMS: 5000, // fail fast — don't hang for 30s
  })

  return global._mongooseConn
}

export default connectDB
