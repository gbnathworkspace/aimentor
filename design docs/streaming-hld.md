# Streaming Architecture — High-Level Design

> **Status:** Design / pre-implementation  
> **Scope:** Claude API streaming → Next.js route → SSE → React client hook  
> **Blocks:** Main Chat (Screen 2), Evaluation Mode (Screen 6)

---

## Problem Statement

The chat UI streams Claude's response token-by-token — the user sees the mentor's reply appearing in real time, not waiting for the full response. Beyond plain text tokens, the stream also needs to carry structured side-channel events: nudges (when the user drifts off-topic) and skill graph updates (when an evaluation verdict updates a topic node).

The architecture must handle all three cleanly without coupling the UI to the server's internal representation.

---

## Decision: SSE over WebSockets

| | SSE | WebSockets |
|---|---|---|
| Direction | Server → client only | Bidirectional |
| Protocol | HTTP/1.1 + HTTP/2 | WS upgrade |
| Next.js support | Native (ReadableStream) | Requires separate WS server |
| Reconnection | Built-in (browser handles it) | Manual |
| Fit for chat | ✅ Perfect — responses flow one way | Overkill for this use case |

The chat input (user → server) is a standard POST. The response (server → client) is an SSE stream. No bidirectional channel is needed — SSE is the right tool.

---

## SSE Event Types

The `StreamParser` emits four typed events. The client `useStream()` hook handles each:

```typescript
type StreamEvent =
  | { type: 'token';        data: { text: string } }
  | { type: 'nudge';        data: { message: string; pinTopic: string } }
  | { type: 'skill_update'; data: { topic: string; newLevel: string; gap: number } }
  | { type: 'done';         data: { sessionId: string } }
  | { type: 'error';        data: { message: string; retryable: boolean } }
```

`token` — Appended character by character to the current message bubble. This is the main streaming event.

`nudge` — Emitted when `SessionService` detects the conversation has drifted off the session topic. The client renders an inline nudge card below the current mentor bubble (matches Screen 2 wireframe exactly).

`skill_update` — Emitted after an evaluation verdict. Triggers a MongoDB write server-side and tells the client to invalidate its skill graph cache so the gap bar updates live.

`done` — Stream is complete. Client closes the EventSource, triggers `SessionSaveHandler` (session persistence + episodic embedding).

`error` — Failure mid-stream. If `retryable: true`, the client shows a "Retry" button. If `false`, it shows a permanent error state.

---

## Components

### `POST /api/chat/stream`
The Next.js App Router route that handles the chat request.

```typescript
export async function POST(req: Request) {
  // 1. verify JWT — reject if invalid
  const { userId } = await requireAuth()

  // 2. assemble context
  const input = await req.json()  // { sessionId, message, topic }
  const context = await assembler.assemble({ userId, ...input })

  // 3. call Claude with streaming
  const stream = await anthropic.messages.stream({
    model: 'claude-opus-4-6',
    system: context.systemPrompt,
    messages: buildMessages(context),
    max_tokens: 1024,
  })

  // 4. return SSE response
  const sseStream = StreamParser.toSSE(stream, { userId, sessionId: input.sessionId })
  return new Response(sseStream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
    }
  })
}
```

### `StreamParser`
Consumes the Anthropic SDK stream and emits typed SSE events.

```typescript
class StreamParser {
  static toSSE(stream: AnthropicStream, ctx: StreamContext): ReadableStream {
    return new ReadableStream({
      async start(controller) {
        for await (const chunk of stream) {
          if (chunk.type === 'content_block_delta') {
            controller.enqueue(sseEvent('token', { text: chunk.delta.text }))
          }
          if (chunk.type === 'content_block_stop') {
            // check accumulated text for nudge signals
            const nudge = NudgeDetector.check(accumulated, ctx.currentTopic)
            if (nudge) {
              controller.enqueue(sseEvent('nudge', nudge))
              await NudgeHandler.log(ctx.sessionId, nudge)
            }
          }
          if (chunk.type === 'tool_use' && chunk.name === 'update_skill_graph') {
            const update = SkillGraphSchema.parse(chunk.input)
            await SkillGraphHandler.write(ctx.userId, update)
            controller.enqueue(sseEvent('skill_update', update))
          }
          if (chunk.type === 'message_stop') {
            controller.enqueue(sseEvent('done', { sessionId: ctx.sessionId }))
            controller.close()
          }
        }
      }
    })
  }
}
```

Key point: `StreamParser` is the only place that knows about the Anthropic SDK's event shape. Everything downstream works with typed `StreamEvent` objects.

### `useStream()` — React client hook

```typescript
function useStream() {
  const [messages, setMessages] = useState<Message[]>([])
  const [status, setStatus] = useState<'idle' | 'streaming' | 'done' | 'error'>('idle')

  async function send(content: string) {
    setStatus('streaming')
    const es = new EventSource(`/api/chat/stream?...`)  // or fetch + ReadableStream

    es.addEventListener('token', (e) => {
      const { text } = JSON.parse(e.data)
      // append token to last message in state
      setMessages(prev => appendToken(prev, text))
    })

    es.addEventListener('nudge', (e) => {
      const nudge = JSON.parse(e.data)
      setMessages(prev => appendNudge(prev, nudge))
    })

    es.addEventListener('skill_update', (e) => {
      // invalidate skill graph query cache
      queryClient.invalidateQueries(['skillGraph'])
    })

    es.addEventListener('done', () => {
      setStatus('done')
      es.close()
    })

    es.addEventListener('error', (e) => {
      const { retryable } = JSON.parse(e.data)
      setStatus('error')
      es.close()
    })
  }

  return { messages, status, send }
}
```

The hook never knows about MongoDB, Anthropic, or context assembly — it only handles the five event types.

---

## Side Effects (post-stream)

Side effects run **after** the stream closes, triggered by the `done` event server-side. They must never block or delay the stream itself.

```
done event emitted
    ↓ (fire and forget, non-blocking)
SessionSaveHandler
  ├── persist full message list to MongoDB
  ├── generate session summary (separate Claude call — short, not streamed)
  └── write session embedding to Vector DB (via IngestionService)
```

If `SessionSaveHandler` fails, the stream already completed successfully from the user's perspective. Log the failure, retry in background. Never surface this to the user mid-session.

---

## Nudge Detection

`NudgeDetector` runs on the accumulated response text at `content_block_stop` (end of each content block, not each token — too expensive per token).

```typescript
class NudgeDetector {
  static check(text: string, currentTopic: string): NudgeSignal | null {
    // heuristic: if mentor's response introduces a new topic not in currentTopic
    // and it constitutes >30% of the response, flag it
    // This is a lightweight string check — not a Claude call
  }
}
```

If this heuristic proves too noisy, replace with a small classification call (Claude Haiku, not Opus) — the interface doesn't change.

---

## Evaluation Mode Differences

Screen 6 (Evaluation) uses the same streaming infrastructure with two differences:

1. The system prompt is the evaluation-mode versioned prompt (selected by `SessionService` based on detected mode)
2. After each answer, the `StreamParser` looks for a `tool_use` block named `submit_verdict` instead of `update_skill_graph`. The verdict updates the eval score in local state (not MongoDB) until the session ends, then writes the final score.

No separate route, no separate hook — just different prompt + different tool name.

---

## Error Handling

| Failure | Behaviour |
|---|---|
| JWT invalid | 401 before stream opens — client redirects to login |
| Context assembly fails | 500 before stream opens — client shows error state |
| Claude API error mid-stream | Emit `error` event with `retryable: true`, close stream |
| Claude API timeout | Emit `error` event with `retryable: true` after 30s |
| `skill_update` Zod parse fails | Log + skip the update — do not emit event, stream continues |
| `SessionSaveHandler` fails | Retry 3× in background, alert if all fail — user never sees this |

---

## File Structure

```
src/
  lib/
    streaming/
      parser.ts             ← StreamParser
      nudge-detector.ts     ← NudgeDetector
      nudge-handler.ts      ← NudgeHandler (logs to MongoDB)
      skill-graph-handler.ts← SkillGraphHandler (writes update)
      session-save-handler.ts
      types.ts              ← StreamEvent type definitions
  hooks/
    use-stream.ts           ← useStream() client hook
  app/
    api/
      chat/
        stream/
          route.ts          ← POST /api/chat/stream
```

---

## Open Questions

- [ ] EventSource vs fetch + ReadableStream — EventSource has built-in reconnection but can't send headers (needed for auth). Use `fetch` with a `ReadableStream` reader instead and pass the JWT in the Authorization header.
- [ ] Token budget — `max_tokens: 1024` is a starting point. Evaluation mode may need more for deep answers. Make this configurable per mode in the prompt config.
- [ ] Nudge detection threshold — the 30% heuristic is a guess. Instrument nudge events from day one and tune based on false positive rate.
- [ ] Session summary generation — the post-stream summary call is a separate Claude call. Should it be Haiku (fast, cheap) or Opus (better quality)? Start with Haiku.
