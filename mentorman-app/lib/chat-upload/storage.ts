/**
 * Storage backend abstraction for file uploads.
 *
 * Switch between local disk and S3 via STORAGE_BACKEND env var:
 *   STORAGE_BACKEND=local  — writes to LOCAL_UPLOADS_DIR on disk (default)
 *   STORAGE_BACKEND=s3     — uploads to S3_BUCKET_NAME
 *
 * The returned storage key is stored in MongoDB and passed to the ingestion
 * pipeline, which reads the file using the same key.
 */

import path from 'path'
import fs from 'fs/promises'
import { uploadToS3 } from './s3'

interface StorageBackend {
  upload(
    userId: string,
    jobId: string,
    filename: string,
    buffer: Buffer,
    contentType: string
  ): Promise<string>
}

class LocalBackend implements StorageBackend {
  private readonly baseDir: string

  constructor() {
    // Default to an 'uploads' folder one level above the Next.js app root,
    // so it's accessible to both Next.js and the ingestion pipeline.
    // Override with LOCAL_UPLOADS_DIR for an explicit absolute path.
    this.baseDir =
      process.env.LOCAL_UPLOADS_DIR ??
      path.join(process.cwd(), '..', 'uploads')
  }

  async upload(
    userId: string,
    jobId: string,
    filename: string,
    buffer: Buffer
  ): Promise<string> {
    const dir = path.join(this.baseDir, userId, jobId)
    await fs.mkdir(dir, { recursive: true })
    const absPath = path.join(dir, filename)
    await fs.writeFile(absPath, buffer)
    // Store the absolute path — the ingestion pipeline reads it directly.
    return absPath
  }
}

class S3Backend implements StorageBackend {
  async upload(
    userId: string,
    jobId: string,
    filename: string,
    buffer: Buffer,
    contentType: string
  ): Promise<string> {
    return uploadToS3(userId, jobId, filename, buffer, contentType)
  }
}

let _backend: StorageBackend | null = null

export function getStorageBackend(): StorageBackend {
  if (!_backend) {
    _backend =
      process.env.STORAGE_BACKEND === 's3' ? new S3Backend() : new LocalBackend()
  }
  return _backend
}
