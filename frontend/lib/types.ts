export interface Message {
  role: "user" | "assistant"
  content: string
  timestamp?: string
}

export interface Session {
  session_id: string
  user_id: string
  title?: string
  topic?: string
  mode: string
  created_at: string
  ended_at?: string
  summary?: string
}

export interface SkillNode {
  topic: string
  current_level: "easy" | "medium" | "hard" | "unknown"
  required_level: "easy" | "medium" | "hard" | "basic"
  gap: string
  last_studied?: string
}

export interface Profile {
  user_id: string
  goal: string
  deadline: string
  overall_level: string
  daily_availability: string
}
