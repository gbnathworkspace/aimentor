import mongoose from 'mongoose'

// ─── MongoDB connection singleton ─────────────────────────────────────────────
// Next.js runs in a serverless context — connections must be cached across
// hot reloads in dev and across invocations in prod.
// Pattern: store connection promise on the global object.

declare global {
  // eslint-disable-next-line no-var
  var _mongooseConn: Promise<typeof mongoose> | undefined
}

if (!process.env.MONGODB_URI) {
  throw new Error('MONGODB_URI is not set in environment variables')
}

const MONGODB_URI = process.env.MONGODB_URI

async function connectDB(): Promise<typeof mongoose> {
  if (global._mongooseConn) {
    return global._mongooseConn
  }

  global._mongooseConn = mongoose.connect(MONGODB_URI, {
    bufferCommands: false,
  })

  return global._mongooseConn
}

export default connectDB
