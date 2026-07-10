import { Suspense } from "react";
import { ChatAskClient } from "@/components/chat-ask-client";

export default function Home() {
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center bg-white text-[13px] text-[#6b7280]">Loading CVUM...</div>}>
      <ChatAskClient />
    </Suspense>
  );
}
