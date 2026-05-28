"use client"
import { useEffect, useState } from "react"
import { useRouter, useParams } from "next/navigation"
import { listSessions, startSession } from "@/lib/api"
import { Session } from "@/lib/types"
import { PlusIcon } from "lucide-react"

export default function SessionSidebar({ userId }: { userId: string }) {
  const [sessions, setSessions] = useState<Session[]>([])
  const router = useRouter()
  const params = useParams()
  const currentId = params?.sessionId as string | undefined

  useEffect(() => {
    listSessions(userId).then(setSessions)
  }, [userId])

  async function handleNew() {
    const { session_id } = await startSession(userId)
    router.push(`/chat/${session_id}`)
  }

  return (
    <aside className="w-64 h-full flex flex-col border-r border-white/10 bg-black/30">
      <div className="p-3 border-b border-white/10">
        <button
          onClick={handleNew}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-white/80 hover:bg-white/10 transition"
        >
          <PlusIcon size={16} />
          New session
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {sessions.map((s) => (
          <button
            key={s.session_id}
            onClick={() => router.push(`/chat/${s.session_id}`)}
            className={`w-full text-left px-3 py-2 rounded-lg text-sm transition truncate ${
              s.session_id === currentId
                ? "bg-white/15 text-white"
                : "text-white/60 hover:bg-white/10 hover:text-white"
            }`}
          >
            {s.title ?? s.topic ?? "Session"}
          </button>
        ))}
      </div>
    </aside>
  )
}
