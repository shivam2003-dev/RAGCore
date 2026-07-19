"use client";

import { useEffect, useState } from "react";
import {
  cvumApi,
  type ConfluenceStatus,
  type JiraStatus,
  type GitHubStatus,
  type MetricsOverview,
  type SlackStatus,
} from "@/lib/cvum-api";

export type LiveMetricsState = {
  metrics: MetricsOverview | null;
  confluence: ConfluenceStatus | null;
  jira: JiraStatus | null;
  slack: SlackStatus | null;
  github: GitHubStatus | null;
  loading: boolean;
  error: string;
  refresh: (options?: { force?: boolean }) => Promise<void>;
};

export function useLiveMetrics(): LiveMetricsState {
  const [metrics, setMetrics] = useState<MetricsOverview | null>(null);
  const [confluence, setConfluence] = useState<ConfluenceStatus | null>(null);
  const [jira, setJira] = useState<JiraStatus | null>(null);
  const [slack, setSlack] = useState<SlackStatus | null>(null);
  const [github, setGithub] = useState<GitHubStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function refresh(options: { force?: boolean } = {}) {
    setLoading(true);
    setError("");
    try {
      if (options.force) {
        cvumApi.refreshLiveData();
      }
      await cvumApi.ensureSession();
      const [overview, confluenceStatus, jiraStatus, slackStatus, githubStatus] = await Promise.all([
        cvumApi.metricsOverview(),
        cvumApi.confluenceStatus().catch(() => null),
        cvumApi.jiraStatus().catch(() => null),
        cvumApi.slackStatus().catch(() => null),
        cvumApi.githubStatus().catch(() => null),
      ]);
      setMetrics(overview);
      setConfluence(confluenceStatus);
      setJira(jiraStatus);
      setSlack(slackStatus);
      setGithub(githubStatus);
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

  return { metrics, confluence, jira, slack, github, loading, error, refresh };
}
