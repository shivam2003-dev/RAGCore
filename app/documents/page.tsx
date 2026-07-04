import { Suspense } from "react";
import { DocumentsClient } from "@/components/documents-client";
import { Card } from "@/components/ui";

export default function DocumentsPage() {
  return (
    <Suspense
      fallback={
        <Card className="p-6">
          <p className="text-[13.5px] font-semibold text-ink-700">Loading documents...</p>
        </Card>
      }
    >
      <DocumentsClient />
    </Suspense>
  );
}
