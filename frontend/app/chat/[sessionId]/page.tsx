import { auth } from "@clerk/nextjs/server"
import { redirect } from "next/navigation"
import ChatInterface from "@/components/chat/ChatInterface"

export default async function SessionPage({ params }: { params: { sessionId: string } }) {
  const { userId } = await auth()
  if (!userId) redirect("/sign-in")

  return (
    <div className="h-full">
      <ChatInterface sessionId={params.sessionId} userId={userId} />
    </div>
  )
}
