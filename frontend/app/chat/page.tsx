import { auth } from "@clerk/nextjs/server"
import { redirect } from "next/navigation"
import { startSession } from "@/lib/api"

export default async function ChatPage() {
  const { userId } = await auth()
  if (!userId) redirect("/sign-in")

  const { session_id } = await startSession(userId)
  redirect(`/chat/${session_id}`)
}
