import { Message } from "@/lib/types"

export default function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user"
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
          isUser
            ? "bg-white text-black rounded-br-sm"
            : "bg-white/10 text-white/90 rounded-bl-sm"
        }`}
      >
        {message.content}
      </div>
    </div>
  )
}
