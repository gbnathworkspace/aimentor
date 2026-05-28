import { auth } from "@clerk/nextjs/server"
import { redirect } from "next/navigation"
import SessionSidebar from "@/components/chat/SessionSidebar"

export default async function ChatLayout({ children }: { children: React.ReactNode }) {
  const { userId } = await auth()
  if (!userId) redirect("/sign-in")

  return (
    <div className="flex h-screen bg-[#0f0f0f]">
      <SessionSidebar userId={userId} />
      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  )
}
