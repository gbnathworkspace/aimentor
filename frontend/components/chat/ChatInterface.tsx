"use client"
import { useEffect, useRef, useState } from "react"
import { Message } from "@/lib/types"
import { streamMessage, endSession } from "@/lib/api"
import MessageBubble from "./MessageBubble"
import ChatInput from "./ChatInput"

interface Props {
  sessionId: string
  userId: string
  initialMessages?: Message[]
}

export default function ChatInterface({ sessionId, userId, initialMessages = [] }: Props) {
  const [messages, setMessages] = useState<Message[]>(initialMessages)
  const [streaming, setStreaming] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  useEffect(() => {
    const handleUnload = () => {
      navigator.sendBeacon(
        `${process.env.NEXT_PUBLIC_API_URL}/chat/session/end`,
        JSON.stringify({ session_id: sessionId, user_id: userId }),
      )
    }
    window.addEventListener("beforeunload", handleUnload)
    return () => window.removeEventListener("beforeunload", handleUnload)
  }, [sessionId, userId])

  function handleSend(text: string) {
    const userMsg: Message = { role: "user", content: text }
    setMessages((prev) => [...prev, userMsg])
    setStreaming(true)

    const assistantMsg: Message = { role: "assistant", content: "" }
    setMessages((prev) => [...prev, assistantMsg])

    streamMessage(
      sessionId,
      userId,
      text,
      undefined,
      (chunk) => {
        setMessages((prev) => {
          const updated = [...prev]
          updated[updated.length - 1] = {
            ...updated[updated.length - 1],
            content: updated[updated.length - 1].content + chunk,
          }
          return updated
        })
      },
      () => setStreaming(false),
    )
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto px-4 py-6">
        {messages.length === 0 && (
          <p className="text-center text-white/30 text-sm mt-20">
            Start by telling your mentor what you want to work on today.
          </p>
        )}
        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} />
        ))}
        <div ref={bottomRef} />
      </div>
      <ChatInput onSend={handleSend} disabled={streaming} />
    </div>
  )
}
