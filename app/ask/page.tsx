import { Suspense } from "react";
import { AskClient } from "@/components/ask-client";
import { Card } from "@/components/ui";

export default function AskPage() {
  return (
    <Suspense
      fallback={
        <Card className="p-6">
          <p className="text-[13.5px] font-semibold text-ink-700">Loading Ask CVUM...</p>
        </Card>
      }
    >
      <AskClient />
    </Suspense>
  );
}
