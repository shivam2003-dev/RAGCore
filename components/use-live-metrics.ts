"use client";

import { useEffect, useState } from "react";
import { kimbalApi, type ConfluenceStatus, type JiraStatus, type MetricsOverview } from "@/lib/kimbal-api";

export type LiveMetricsState = {
  metrics: MetricsOverview | null;
  confluence: ConfluenceStatus | null;
  jira: JiraStatus | null;
  loading: boolean;
  error: string;
  refresh: () => Promise<void>;
};

export function useLiveMetrics(): LiveMetricsState {
  const [metrics, setMetrics] = useState<MetricsOverview | null>(null);
  const [confluence, setConfluence] = useState<ConfluenceStatus | null>(null);
  const [jira, setJira] = useState<JiraStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      await kimbalApi.ensureSession();
      const [overview, confluenceStatus, jiraStatus] = await Promise.all([
        kimbalApi.metricsOverview(),
        kimbalApi.confluenceStatus().catch(() => null),
        kimbalApi.jiraStatus().catch(() => null),
      ]);
      setMetrics(overview);
      setConfluence(confluenceStatus);
      setJira(jiraStatus);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to load live metrics");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refresh();
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  return { metrics, confluence, jira, loading, error, refresh };
}
