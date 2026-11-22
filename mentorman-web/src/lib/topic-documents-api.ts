/**
 * API client for /api/topic/{topicId}/document(s) — documents held as
 * persistent context for one topic (unified-backend/app/routers/topics.py).
 */

export interface TopicDocument {
  filename: string;
  chunkCount: number;
  uploadedAt: string | null;
}

export async function listTopicDocuments(topicId: string): Promise<TopicDocument[]> {
  const res = await fetch(`/api/topic/${topicId}/documents`, { cache: 'no-store' });
  if (!res.ok) return [];
  const data = await res.json();
  return data.documents ?? [];
}

export interface UploadTopicDocumentsResult {
  accepted: number;
  errors: Array<{ filename: string; error: string }>;
}

export async function uploadTopicDocuments(
  topicId: string,
  files: File[]
): Promise<UploadTopicDocumentsResult> {
  const form = new FormData();
  files.forEach(f => form.append('files', f));
  const res = await fetch(`/api/topic/${topicId}/document`, { method: 'POST', body: form });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail?.message || 'Upload failed');
  }
  return res.json();
}

export async function deleteTopicDocument(topicId: string, filename: string): Promise<void> {
  await fetch(`/api/topic/${topicId}/documents/${encodeURIComponent(filename)}`, {
    method: 'DELETE',
  });
}

/** A YouTube video added to the topic (unified-backend/app/routers/videos.py). */
export interface TopicVideo {
  video_id: string;
  url: string;
  title: string | null;
  status: 'queued' | 'fetching' | 'embedding' | 'summarizing' | 'completed' | 'failed';
  sparse?: boolean;
  error?: string | null;
}

export async function listTopicVideos(topicId: string): Promise<TopicVideo[]> {
  const res = await fetch(`/api/topic/${topicId}/videos`, { cache: 'no-store' });
  if (!res.ok) return [];
  const data = await res.json();
  return data.videos ?? [];
}

export async function deleteTopicVideo(videoId: string): Promise<void> {
  await fetch(`/api/videos/${encodeURIComponent(videoId)}`, { method: 'DELETE' });
}
