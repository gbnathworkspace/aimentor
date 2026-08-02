import { describe, it, expect } from 'vitest';
import { detectTopic } from './detectTopic';
import type { TopicListItem } from './types';

const topic = (title: string, subject?: string): TopicListItem => ({
  topicId: title,
  title,
  status: 'active',
  lastActiveAt: new Date(),
  mode: null,
  messagePreview: '',
  subject: subject ?? null,
});

const TOPICS = [
  topic('React'),
  topic('AWS Lambda', 'AWS'),
  topic('Physics'),
  topic('hello, quick sanity check'),
];

describe('detectTopic', () => {
  it('matches a topic named in the message', () => {
    expect(detectTopic('explain react hooks to me', TOPICS)?.title).toBe('React');
  });

  it('matches on the subject as well as the title', () => {
    expect(detectTopic('how does aws billing work', TOPICS)?.title).toBe('AWS Lambda');
  });

  it('returns null when nothing overlaps', () => {
    expect(detectTopic('teach me about sourdough starters', TOPICS)).toBeNull();
  });

  it('prefers the tighter match over a long noisy title', () => {
    expect(detectTopic('quick physics check', TOPICS)?.title).toBe('Physics');
  });

  it('ignores stopwords and short words', () => {
    expect(detectTopic('what is a new topic for me', TOPICS)).toBeNull();
  });
});
