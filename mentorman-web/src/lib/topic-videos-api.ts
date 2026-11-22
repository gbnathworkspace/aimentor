/**
 * API client for YouTube videos added to a topic
 * (unified-backend/app/routers/videos.py).
 */

export type VideoStatus = 'queued' | 'fetching' | 'embedding' | 'summarizing' | 'completed' | 'failed';

export interface TopicVideo {
  video_id: string;
  url: string;
  title?: string | null;
  status: VideoStatus;
  duration_seconds?: number | null;
  chunk_count?: number | null;
  error?: string | null;
}

export const isVideoInProgress = (v: TopicVideo) => v.status !== 'completed' && v.status !== 'failed';

export async function listTopicVideos(topicId: string): Promise<TopicVideo[]> {
  const res = await fetch(`/api/topic/${topicId}/videos`, { cache: 'no-store' });
  if (!res.ok) return [];
  const data = await res.json();
  return data.videos ?? [];
}

export async function deleteTopicVideo(videoId: string): Promise<void> {
  await fetch(`/api/videos/${videoId}`, { method: 'DELETE' });
}
