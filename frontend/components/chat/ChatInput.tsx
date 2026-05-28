"use client"
import { useState, useRef, KeyboardEvent } from "react"
import { SendHorizonal } from "lucide-react"

interface Props {
  onSend: (message: string) => void
  disabled?: boolean
}

export default function ChatInput({ onSend, disabled }: Props) {
  const [value, setValue] = useState("")
  const ref = useRef<HTMLTextAreaElement>(null)

  function submit() {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue("")
    if (ref.current) ref.current.style.height = "auto"
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="flex items-end gap-2 p-4 border-t border-white/10 bg-black/30">
      <textarea
        ref={ref}
        value={value}
        onChange={(e) => {
          setValue(e.target.value)
          e.target.style.height = "auto"
          e.target.style.height = `${e.target.scrollHeight}px`
        }}
        onKeyDown={onKey}
        disabled={disabled}
        placeholder="Ask your mentor..."
        rows={1}
        className="flex-1 resize-none bg-white/10 text-white placeholder-white/30 rounded-xl px-4 py-3 text-sm outline-none focus:ring-1 focus:ring-white/20 max-h-40 overflow-y-auto"
      />
      <button
        onClick={submit}
        disabled={disabled || !value.trim()}
        className="p-3 rounded-xl bg-white text-black disabled:opacity-30 hover:bg-white/90 transition"
      >
        <SendHorizonal size={16} />
      </button>
    </div>
  )
}
