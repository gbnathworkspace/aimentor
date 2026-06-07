// ─── ImmediateContext Assembly Types ──────────────────────────────────────────
// Types specific to the ImmediateContext integration in context assembly.
// These extend the base AssembledContext contract with session-upload awareness.

export interface ImmediateContextBlock {
  filename: string
  uploadTimestamp: string   // ISO date string of when the file was uploaded
  content: string           // extracted text or CSV summary
  accompanyingMessage: string
}

/**
 * Raw document shape returned from the ImmediateContext MongoDB collection.
 */
export interface ImmediateContextDoc {
  sessionId: string
  userId: string
  jobId: string
  filename: string
  fileType: 'resume' | 'leetcode'
  content: string
  tokenCount: number
  accompanyingMessage: string
  active: boolean
  createdAt: Date
  updatedAt: Date
}
