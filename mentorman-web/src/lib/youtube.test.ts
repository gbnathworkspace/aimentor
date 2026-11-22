import { describe, expect, it } from 'vitest';
import { findYouTubeLinks, stripYouTubeLinks } from './youtube';

describe('youtube links', () => {
  it('finds the common link forms', () => {
    for (const url of [
      'https://youtu.be/2tPQaOZPpUw?si=n8dlu52p1nnIHOTJ',
      'https://www.youtube.com/watch?v=2tPQaOZPpUw',
      'https://youtube.com/watch?feature=share&v=2tPQaOZPpUw&t=30',
      'https://www.youtube.com/shorts/2tPQaOZPpUw',
    ]) {
      expect(findYouTubeLinks(`look ${url} ok`).map(l => l.id)).toEqual(['2tPQaOZPpUw']);
    }
  });

  it('ignores other links and de-duplicates', () => {
    expect(findYouTubeLinks('https://example.com/watch?v=2tPQaOZPpUw')).toEqual([]);
    expect(findYouTubeLinks('https://youtu.be/2tPQaOZPpUw https://youtu.be/2tPQaOZPpUw')).toHaveLength(1);
  });

  it('strips links and keeps the rest', () => {
    expect(stripYouTubeLinks('https://youtu.be/2tPQaOZPpUw')).toBe('');
    expect(stripYouTubeLinks('summarise https://youtu.be/2tPQaOZPpUw please')).toBe('summarise  please');
  });
});
