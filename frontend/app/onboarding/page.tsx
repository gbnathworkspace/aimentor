"use client"
import { useUser } from "@clerk/nextjs"
import { useState } from "react"
import { useRouter } from "next/navigation"
import { saveProfile } from "@/lib/api"

const STEPS = [
  { field: "goal", question: "What are you working towards? (e.g. 20 LPA at a product company)" },
  { field: "deadline", question: "What's your target timeline? (e.g. Aug 2026, 3 months)" },
  { field: "overall_level", question: "Where are you right now? (beginner / intermediate / advanced)" },
  { field: "daily_availability", question: "How many hours a day can you realistically put in?" },
]

export default function OnboardingPage() {
  const { user } = useUser()
  const router = useRouter()
  const [step, setStep] = useState(0)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [input, setInput] = useState("")
  const [saving, setSaving] = useState(false)

  async function handleNext() {
    const current = STEPS[step]
    const updated = { ...answers, [current.field]: input.trim() }
    setAnswers(updated)
    setInput("")

    if (step < STEPS.length - 1) {
      setStep(step + 1)
      return
    }

    setSaving(true)
    await saveProfile({ user_id: user!.id, ...updated })
    router.push("/chat")
  }

  return (
    <div className="min-h-screen bg-[#0f0f0f] flex items-center justify-center p-6">
      <div className="w-full max-w-lg space-y-6">
        <div className="text-xs text-white/30 uppercase tracking-widest">
          Setup {step + 1} / {STEPS.length}
        </div>

        <div className="space-y-3">
          {Object.entries(answers).map(([, v], i) => (
            <div key={i} className="text-white/40 text-sm">{v}</div>
          ))}
          <p className="text-white text-lg">{STEPS[step].question}</p>
        </div>

        <div className="flex gap-2">
          <input
            autoFocus
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && input.trim() && handleNext()}
            className="flex-1 bg-white/10 text-white placeholder-white/30 rounded-xl px-4 py-3 text-sm outline-none focus:ring-1 focus:ring-white/20"
            placeholder="Type your answer..."
          />
          <button
            onClick={handleNext}
            disabled={!input.trim() || saving}
            className="px-5 py-3 rounded-xl bg-white text-black text-sm font-medium disabled:opacity-30 hover:bg-white/90 transition"
          >
            {step < STEPS.length - 1 ? "Next" : saving ? "Saving…" : "Start"}
          </button>
        </div>
      </div>
    </div>
  )
}
