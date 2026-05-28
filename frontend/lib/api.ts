const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export async function startSession(userId: string, topic?: string) {
  const res = await fetch(`${API_URL}/chat/session/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, topic }),
  })
  return res.json()
}

export async function endSession(sessionId: string, userId: string) {
  const res = await fetch(`${API_URL}/chat/session/end`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, user_id: userId }),
  })
  return res.json()
}

export async function listSessions(userId: string) {
  const res = await fetch(`${API_URL}/chat/sessions/${userId}`)
  return res.json()
}

export async function getProfile(userId: string) {
  const res = await fetch(`${API_URL}/profile/${userId}`)
  return res.json()
}

export async function saveProfile(profile: Record<string, string>) {
  const res = await fetch(`${API_URL}/profile/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  })
  return res.json()
}

export function streamMessage(
  sessionId: string,
  userId: string,
  message: string,
  topic: string | undefined,
  onChunk: (chunk: string) => void,
  onDone: () => void,
) {
  fetch(`${API_URL}/chat/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, user_id: userId, message, topic }),
  }).then(async (res) => {
    const reader = res.body?.getReader()
    const decoder = new TextDecoder()
    if (!reader) return

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const text = decoder.decode(value)
      const lines = text.split("\n")
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6)
          if (data === "[DONE]") { onDone(); return }
          onChunk(data)
        }
      }
    }
    onDone()
  })
}
