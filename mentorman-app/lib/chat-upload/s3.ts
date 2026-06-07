/**
 * S3 upload utility for session file uploads.
 *
 * Uses the AWS SDK to store uploaded files in the configured S3 bucket.
 * S3 keys follow the pattern: uploads/{userId}/{jobId}/{filename}
 */

import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3'

let s3Client: S3Client | null = null

function getS3Client(): S3Client {
  if (!s3Client) {
    s3Client = new S3Client({
      region: process.env.AWS_REGION ?? 'us-east-1',
      credentials: process.env.AWS_ACCESS_KEY_ID
        ? {
            accessKeyId: process.env.AWS_ACCESS_KEY_ID,
            secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY ?? '',
          }
        : undefined,
    })
  }
  return s3Client
}

/**
 * Constructs the S3 key for an uploaded file.
 */
export function constructS3Key(userId: string, jobId: string, filename: string): string {
  return `uploads/${userId}/${jobId}/${filename}`
}

/**
 * Uploads a file buffer to S3 and returns the S3 key.
 *
 * @throws Error if the upload fails.
 */
export async function uploadToS3(
  userId: string,
  jobId: string,
  filename: string,
  fileBuffer: Buffer,
  contentType: string
): Promise<string> {
  const bucket = process.env.S3_BUCKET_NAME
  if (!bucket) {
    throw new Error('S3_BUCKET_NAME environment variable is not configured')
  }

  const s3Key = constructS3Key(userId, jobId, filename)
  const client = getS3Client()

  await client.send(
    new PutObjectCommand({
      Bucket: bucket,
      Key: s3Key,
      Body: fileBuffer,
      ContentType: contentType,
    })
  )

  return s3Key
}
