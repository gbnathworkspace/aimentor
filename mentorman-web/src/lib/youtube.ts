// Pasted YouTube links render as a thumbnail card in chat.
const YOUTUBE_URL =
  /https?:\/\/(?:www\.|m\.)?(?:youtube\.com\/(?:watch\?(?:[^\s&]*&)*v=|shorts\/|embed\/|live\/)|youtu\.be\/)([A-Za-z0-9_-]{11})[^\s]*/g;

export interface YouTubeLink {
  id: string;
  url: string;
}

/** YouTube links found in a message, de-duplicated by video id. */
export function findYouTubeLinks(text: string): YouTubeLink[] {
  const seen = new Set<string>();
  const links: YouTubeLink[] = [];
  for (const match of text.matchAll(YOUTUBE_URL)) {
    if (seen.has(match[1])) continue;
    seen.add(match[1]);
    links.push({ id: match[1], url: match[0] });
  }
  return links;
}

/** The message with its YouTube links removed (the cards replace them). */
export function stripYouTubeLinks(text: string): string {
  return text.replace(YOUTUBE_URL, '').replace(/[ \t]+\n/g, '\n').trim();
}

export const youTubeThumbnail = (id: string) => `https://i.ytimg.com/vi/${id}/hqdefault.jpg`;
