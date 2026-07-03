'use client';

import React, { useEffect, useState } from 'react';
import { Icon } from './icons';

/** Strip markdown so it isn't read aloud literally ("asterisk asterisk..."). */
function plainText(text: string): string {
  return text.replace(/\*\*([^*]+)\*\*/g, '$1').replace(/`([^`]+)`/g, '$1');
}

// Quality tiers, most natural-sounding first. Browsers/OSes expose a mix of
// local robotic voices and (if installed) far better neural/cloud ones under
// the same speechSynthesis API — the default voice Chrome picks is rarely
// the best one available, so we rank and pick instead of taking voice[0].
const QUALITY_HINTS = ['natural', 'neural', 'premium', 'enhanced', 'online', 'google'];

let cachedVoice: SpeechSynthesisVoice | null | undefined; // undefined = not resolved yet

function scoreVoice(v: SpeechSynthesisVoice): number {
  const name = v.name.toLowerCase();
  let score = 0;
  const hintIdx = QUALITY_HINTS.findIndex(h => name.includes(h));
  if (hintIdx !== -1) score += (QUALITY_HINTS.length - hintIdx) * 10;
  if (v.lang.toLowerCase().startsWith('en')) score += 5;
  if (v.lang.toLowerCase() === 'en-us') score += 2;
  return score;
}

function pickBestVoice(): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis.getVoices();
  if (voices.length === 0) return null;
  return [...voices].sort((a, b) => scoreVoice(b) - scoreVoice(a))[0];
}

/** Resolves the best available voice once and caches it. Voice lists load
 *  async in most browsers, so this waits for `voiceschanged` if needed. */
function getBestVoice(): Promise<SpeechSynthesisVoice | null> {
  if (cachedVoice !== undefined) return Promise.resolve(cachedVoice);
  const immediate = pickBestVoice();
  if (immediate) {
    cachedVoice = immediate;
    return Promise.resolve(immediate);
  }
  return new Promise(resolve => {
    const onVoicesChanged = () => {
      window.speechSynthesis.removeEventListener('voiceschanged', onVoicesChanged);
      cachedVoice = pickBestVoice();
      resolve(cachedVoice);
    };
    window.speechSynthesis.addEventListener('voiceschanged', onVoicesChanged);
  });
}

/** Read-aloud toggle using the browser's built-in speech synthesis — no API
 *  calls, no new dependency. Renders nothing if the browser doesn't support it. */
export function SpeakButton({ text, className = '' }: { text: string; className?: string }) {
  const [speaking, setSpeaking] = useState(false);
  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window;

  // Stop speaking if this bubble unmounts (e.g. navigating away mid-read).
  useEffect(() => {
    if (!supported) return;
    return () => {
      if (speaking) window.speechSynthesis.cancel();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!supported) return null;

  const toggle = async () => {
    if (speaking) {
      window.speechSynthesis.cancel();
      setSpeaking(false);
      return;
    }
    window.speechSynthesis.cancel(); // only one message reads at a time
    const utter = new SpeechSynthesisUtterance(plainText(text));
    const voice = await getBestVoice();
    if (voice) utter.voice = voice;
    utter.rate = 1.02;
    utter.onend = () => setSpeaking(false);
    utter.onerror = () => setSpeaking(false);
    window.speechSynthesis.speak(utter);
    setSpeaking(true);
  };

  return (
    <button
      className={`speak-btn ${speaking ? 'on' : ''} ${className}`}
      onClick={toggle}
      title={speaking ? 'Stop reading' : 'Read aloud'}
      aria-label={speaking ? 'Stop reading message aloud' : 'Read message aloud'}
    >
      <Icon name={speaking ? 'stop' : 'volume'} size={13} />
    </button>
  );
}
