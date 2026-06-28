'use client';

/**
 * useSessionPersistence — custom hook encapsulating all session persistence
 * logic for the ChatPanel.
 *
 * Responsibilities:
 * 1. Create sessions via POST /api/sessions with retry (once after 2s)
 * 2. Persist messages via POST /api/sessions/{id}/messages with retry + localStorage fallback
 * 3. Auto-checkpoint every 6 messages via POST /api/sessions/{id}/checkpoint
 * 4. End session via PATCH /api/sessions/{id} with loading state and 30s timeout
 * 5. beforeunload handler for crash recovery (checkpoint + localStorage fallback)
 * 6. Recover orphaned messages from localStorage on mount
 * 7. Expose sessionId, isEnding, error state
 *
 * Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
 */

import { useState, useRef, useCallback, useEffect } from 'react';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface Message {
  role: 'user' | 'mentor';
  content: string;
  timestamp: string;
}

export interface SessionEndResult {
  session_id: string;
  title: string;
  summary: string;
  skill_update: any | null;
  level_from?: string | null;  // level before this session (issue #16)
  level_to?: string | null;    // graded level after this session
  status: 'ended';
}

export interface UseSessionPersistence {
  sessionId: string | null;
  isEnding: boolean;
  error: string | null;
  createSession(mode: string, topic: string): Promise<string | null>;
  persistMessages(userMsg: Message, mentorMsg: Message): Promise<void>;
  endSession(sessionId?: string): Promise<SessionEndResult | null>;
  recoverOrphanedMessages(): Promise<void>;
  retryCreateSession(): Promise<string | null>;
}

// ─── Constants ────────────────────────────────────────────────────────────────

/** localStorage key for the active session ID */
const LS_ACTIVE_SESSION_KEY = 'mentorman_active_session';

/** localStorage key prefix for orphaned messages */
const LS_MESSAGES_PREFIX = 'mentorman_session_messages_';

/** Number of messages between auto-checkpoints */
const CHECKPOINT_INTERVAL = 6;

/** Timeout for the end-session call (30 seconds) */
const END_SESSION_TIMEOUT_MS = 30_000;

/** Timeout for the beforeunload checkpoint (2 seconds) */
const BEFOREUNLOAD_TIMEOUT_MS = 2_000;

/** Delay before retrying session creation (2 seconds) */
const CREATE_RETRY_DELAY_MS = 2_000;

/** Delay before retrying message persistence (1 second) */
const MESSAGE_RETRY_DELAY_MS = 1_000;

// ─── Helpers ──────────────────────────────────────────────────────────────────

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function getOrphanedMessagesKey(sessionId: string): string {
  return `${LS_MESSAGES_PREFIX}${sessionId}`;
}

function storeOrphanedMessages(sessionId: string, messages: Message[]): void {
  try {
    const key = getOrphanedMessagesKey(sessionId);
    const existing = localStorage.getItem(key);
    const current: Message[] = existing ? JSON.parse(existing) : [];
    // Merge without duplicates (by timestamp + role)
    const seen = new Set(current.map((m) => `${m.timestamp}|${m.role}`));
    const merged = [...current];
    for (const msg of messages) {
      const id = `${msg.timestamp}|${msg.role}`;
      if (!seen.has(id)) {
        merged.push(msg);
        seen.add(id);
      }
    }
    localStorage.setItem(key, JSON.stringify(merged));
  } catch {
    // localStorage not available — silent fail
  }
}

function getStoredOrphanedMessages(sessionId: string): Message[] {
  try {
    const raw = localStorage.getItem(getOrphanedMessagesKey(sessionId));
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function clearOrphanedMessages(sessionId: string): void {
  try {
    localStorage.removeItem(getOrphanedMessagesKey(sessionId));
  } catch {
    // silent
  }
}

function storeActiveSession(sessionId: string): void {
  try {
    localStorage.setItem(LS_ACTIVE_SESSION_KEY, sessionId);
  } catch {
    // silent
  }
}

function getStoredActiveSession(): string | null {
  try {
    return localStorage.getItem(LS_ACTIVE_SESSION_KEY);
  } catch {
    return null;
  }
}

function clearActiveSession(): void {
  try {
    localStorage.removeItem(LS_ACTIVE_SESSION_KEY);
  } catch {
    // silent
  }
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useSessionPersistence(): UseSessionPersistence {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isEnding, setIsEnding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Track message count for auto-checkpoint
  const messageCountRef = useRef(0);
  // Track all messages sent since last successful checkpoint (for beforeunload fallback)
  const messagesSinceCheckpointRef = useRef<Message[]>([]);
  // Track all session messages (for checkpoint full-array writes)
  const allMessagesRef = useRef<Message[]>([]);
  // Retry state for createSession
  const lastModeRef = useRef<string>('');
  const lastTopicRef = useRef<string>('');
  // Session ID ref (for closures that can't rely on stale state)
  const sessionIdRef = useRef<string | null>(null);

  // Keep sessionIdRef in sync with state
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  // ─── createSession ────────────────────────────────────────────────────

  const createSession = useCallback(async (mode: string, topic: string): Promise<string | null> => {
    lastModeRef.current = mode;
    lastTopicRef.current = topic;
    setError(null);

    const attempt = async (): Promise<string | null> => {
      try {
        const res = await fetch('/api/sessions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode, topic }),
        });
        if (!res.ok) return null;
        const data = await res.json();
        const id = data.session_id ?? data.sessionId ?? null;
        return id;
      } catch {
        return null;
      }
    };

    // First attempt
    let id = await attempt();
    if (id) {
      setSessionId(id);
      storeActiveSession(id);
      return id;
    }

    // Retry once after 2s
    await delay(CREATE_RETRY_DELAY_MS);
    id = await attempt();
    if (id) {
      setSessionId(id);
      storeActiveSession(id);
      return id;
    }

    // Both attempts failed — show error, disable input
    setError('Session could not be started. Please retry.');
    return null;
  }, []);

  // ─── retryCreateSession ───────────────────────────────────────────────

  const retryCreateSession = useCallback(async (): Promise<string | null> => {
    return createSession(lastModeRef.current, lastTopicRef.current);
  }, [createSession]);

  // ─── persistMessages ──────────────────────────────────────────────────

  const persistMessages = useCallback(async (userMsg: Message, mentorMsg: Message): Promise<void> => {
    const sid = sessionIdRef.current;
    if (!sid) return;

    const messages = [userMsg, mentorMsg];

    // Track for checkpoint
    allMessagesRef.current = [...allMessagesRef.current, ...messages];
    messagesSinceCheckpointRef.current = [...messagesSinceCheckpointRef.current, ...messages];
    messageCountRef.current += 2;

    const attempt = async (): Promise<boolean> => {
      try {
        const res = await fetch(`/api/sessions/${sid}/messages`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ messages }),
        });
        return res.ok;
      } catch {
        return false;
      }
    };

    // First attempt
    let ok = await attempt();
    if (!ok) {
      // Retry once after 1s
      await delay(MESSAGE_RETRY_DELAY_MS);
      ok = await attempt();
    }

    if (!ok) {
      // Queue to localStorage on failure (Req 8.3, 8.7)
      storeOrphanedMessages(sid, messages);
    }

    // Auto-checkpoint every 6 messages (Req 3.1)
    if (messageCountRef.current > 0 && messageCountRef.current % CHECKPOINT_INTERVAL === 0) {
      await doCheckpoint(sid);
    }
  }, []);

  // ─── doCheckpoint ─────────────────────────────────────────────────────

  const doCheckpoint = useCallback(async (sid: string): Promise<boolean> => {
    const attempt = async (): Promise<boolean> => {
      try {
        const res = await fetch(`/api/sessions/${sid}/checkpoint`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ messages: allMessagesRef.current }),
        });
        return res.ok;
      } catch {
        return false;
      }
    };

    let ok = await attempt();
    if (!ok) {
      // Retry once after 1s
      await delay(MESSAGE_RETRY_DELAY_MS);
      ok = await attempt();
    }

    if (ok) {
      // Clear the since-checkpoint buffer on success
      messagesSinceCheckpointRef.current = [];
    } else {
      // Store in localStorage on failure (Req 3.2)
      storeOrphanedMessages(sid, messagesSinceCheckpointRef.current);
    }

    return ok;
  }, []);

  // ─── endSession ───────────────────────────────────────────────────────

  const endSession = useCallback(async (overrideSessionId?: string): Promise<SessionEndResult | null> => {
    const sid = overrideSessionId || sessionIdRef.current;
    if (!sid) return null;

    setIsEnding(true);
    setError(null);

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), END_SESSION_TIMEOUT_MS);

      const res = await fetch(`/api/sessions/${sid}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'ending' }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!res.ok) {
        setError('Failed to end session. Please try again.');
        return null;
      }

      const result: SessionEndResult = await res.json();

      // Clear state on success (Req 8.5)
      setSessionId(null);
      clearActiveSession();
      clearOrphanedMessages(sid);
      messageCountRef.current = 0;
      messagesSinceCheckpointRef.current = [];
      allMessagesRef.current = [];

      return result;
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        setError('Session processing timed out. You can retry ending the session.');
      } else {
        setError('Failed to end session. Please try again.');
      }
      return null;
    } finally {
      setIsEnding(false);
    }
  }, []);

  // ─── recoverOrphanedMessages ──────────────────────────────────────────

  const recoverOrphanedMessages = useCallback(async (): Promise<void> => {
    // Check if there's a previous active session with orphaned messages
    const previousSessionId = getStoredActiveSession();
    if (!previousSessionId) return;

    const orphaned = getStoredOrphanedMessages(previousSessionId);
    if (orphaned.length === 0) {
      // No orphaned messages, clean up the stale active session key
      clearActiveSession();
      return;
    }

    try {
      const res = await fetch(`/api/sessions/${previousSessionId}/recover`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: orphaned }),
      });

      if (res.ok) {
        // Only clear localStorage after 2xx (Req 8.7, 3.7)
        clearOrphanedMessages(previousSessionId);
        clearActiveSession();
      }
      // If not ok, keep the orphaned messages in localStorage for next attempt
    } catch {
      // Network error — keep localStorage intact for next recovery attempt
    }
  }, []);

  // ─── beforeunload handler ─────────────────────────────────────────────

  useEffect(() => {
    const handleBeforeUnload = () => {
      const sid = sessionIdRef.current;
      if (!sid) return;

      const unsaved = messagesSinceCheckpointRef.current;
      if (unsaved.length === 0) return;

      // Attempt a synchronous beacon-style checkpoint (Req 3.3)
      // Use sendBeacon for best-effort delivery within the beforeunload budget
      const payload = JSON.stringify({ messages: allMessagesRef.current });
      const url = `/api/sessions/${sid}/checkpoint`;

      const sent = navigator.sendBeacon(
        url,
        new Blob([payload], { type: 'application/json' })
      );

      if (!sent) {
        // Fallback: store in localStorage (Req 3.4)
        storeOrphanedMessages(sid, unsaved);
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, []);

  return {
    sessionId,
    isEnding,
    error,
    createSession,
    persistMessages,
    endSession,
    recoverOrphanedMessages,
    retryCreateSession,
  };
}
