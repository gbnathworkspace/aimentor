import { describe, expect, it } from 'vitest';
import { youtubeIds } from './ui';

describe('youtubeIds', () => {
  it('finds ids in every common link shape, deduped', () => {
    expect(youtubeIds('https://youtu.be/2tPQaOZPpUw?si=n8dlu52p1nnIHOTJ')).toEqual(['2tPQaOZPpUw']);
    expect(youtubeIds('see https://www.youtube.com/watch?v=aircAruvnKk&t=30s and https://youtube.com/shorts/aircAruvnKk')).toEqual(['aircAruvnKk']);
    expect(youtubeIds('https://m.youtube.com/watch?feature=share&v=kCc8FmEb1nY')).toEqual(['kCc8FmEb1nY']);
  });
  it('ignores non-video links', () => {
    expect(youtubeIds('https://youtube.com/@3blue1brown https://example.com/watch?v=aircAruvnKk')).toEqual([]);
  });
});
