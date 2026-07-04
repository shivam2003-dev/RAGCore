import {
  ArrowLeft,
  Sparkles,
  ThumbsUp,
  ThumbsDown,
  Bookmark,
  Share2,
  Send,
  ArrowRight,
  User,
  Info,
} from "lucide-react";
import Link from "next/link";
import { Card, CardLink } from "@/components/ui";
import { ConfluenceIcon, GitHubIcon } from "@/components/brand-icons";

const sources = [
  { title: "Kubernetes Deployment Guide", meta: "Confluence • Updated 2 days ago", score: "94%", icon: ConfluenceIcon },
  { title: "Microservice Template Repo", meta: "GitHub • Updated 5 days ago", score: "92%", icon: GitHubIcon },
  { title: "CI/CD Pipeline Documentation", meta: "Confluence • Updated 1 week ago", score: "90%", icon: ConfluenceIcon },
  { title: "Troubleshooting Guide", meta: "Confluence • Updated 3 weeks ago", score: "87%", icon: ConfluenceIcon },
  { title: "Kubernetes Best Practices", meta: "Confluence • Updated 1 month ago", score: "85%", icon: ConfluenceIcon },
];

const related = [
  "How to rollback a Kubernetes deployment?",
  "How to access production logs?",
  "What are the ingress rules for production?",
  "How to configure health checks?",
  "How to manage secrets in Kubernetes?",
];

const recent = [
  "How to deploy a new microservice?",
  "How to configure monitoring for a service?",
  "How to scale a deployment?",
];

function Code({ children }: { children: string }) {
  return (
    <code className="rounded-md bg-brand-50 px-1.5 py-0.5 font-mono text-[12.5px] text-brand-700">
      {children}
    </code>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-[14.5px] font-semibold text-ink-900">
        {n}. {title}
      </p>
      <ul className="mt-2 space-y-1.5 pl-5">{children}</ul>
    </div>
  );
}

function Li({ children }: { children: React.ReactNode }) {
  return (
    <li className="relative text-[13.5px] leading-relaxed text-ink-700 before:absolute before:-left-4 before:top-[9px] before:h-1 before:w-1 before:rounded-full before:bg-ink-300">
      {children}
    </li>
  );
}

export default function AskPage() {
  return (
    <div className="grid grid-cols-12 gap-6">
      {/* conversation */}
      <div className="col-span-8 animate-rise">
        <div className="flex items-center gap-3">
          <Link href="/" className="text-ink-500 transition hover:text-brand-600" aria-label="Back to home">
            <ArrowLeft size={18} />
          </Link>
          <h1 className="text-[17px] font-bold text-ink-900">
            Ask Kimbal <span className="font-normal text-ink-500">(Powered by RAG)</span>
          </h1>
        </div>

        {/* user message */}
        <div className="mt-5 flex items-start justify-end gap-3">
          <div>
            <div className="rounded-[16px] rounded-tr-[4px] bg-gradient-to-r from-brand-500 to-brand-600 px-5 py-3.5 text-[14px] font-medium text-white shadow-[var(--shadow-pop)]">
              How do I deploy a new microservice on Kubernetes in our production environment?
            </div>
            <p className="mt-1.5 text-right text-[11.5px] text-ink-400">10:24 AM</p>
          </div>
          <span className="mt-1 flex h-9 w-9 items-center justify-center rounded-full bg-brand-50 text-brand-400">
            <User size={16} />
          </span>
        </div>

        {/* answer */}
        <Card className="mt-2 p-6">
          <div className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-brand-50 text-brand-500">
              <Sparkles size={15} />
            </span>
            <p className="text-[14.5px] font-semibold text-ink-900">Kimbal AI</p>
          </div>

          <p className="mt-4 text-[13.5px] leading-relaxed text-ink-700">
            Here&apos;s how you can deploy a new microservice on Kubernetes in our production environment:
          </p>

          <div className="mt-5 space-y-5">
            <Step n={1} title="Prepare the Docker Image">
              <Li>
                Build the Docker image and push it to our private registry (<strong className="font-semibold text-ink-900">harbor.kimbal.io</strong>).
              </Li>
              <Li>
                Follow the <a href="#" className="font-medium text-brand-500 hover:underline">Docker Build Best Practices</a>.
              </Li>
            </Step>

            <Step n={2} title="Create Kubernetes Manifests">
              <Li>
                Use the <a href="#" className="font-medium text-brand-500 hover:underline">service-template repository</a> as a base.
              </Li>
              <Li>
                Update the values in <Code>deployment.yaml</Code>, <Code>service.yaml</Code>, and <Code>configmap.yaml</Code>.
              </Li>
            </Step>

            <Step n={3} title="Run Pre-deployment Checks">
              <Li>Ensure all CI/CD checks pass.</Li>
              <Li>
                Run <Code>{"kubectl diff -f <manifest-path>"}</Code> to preview changes.
              </Li>
            </Step>

            <Step n={4} title="Deploy via CI/CD Pipeline">
              <Li>Create a pull request in the infrastructure-configs repo.</Li>
              <Li>Once approved, the ArgoCD pipeline will automatically sync the changes.</Li>
              <Li>
                Monitor the rollout in <strong className="font-semibold text-ink-900">ArgoCD Dashboard</strong>.
              </Li>
            </Step>

            <Step n={5} title="Validate the Deployment">
              <Li>
                Check pod status: <Code>{"kubectl get pods -n <namespace>"}</Code>
              </Li>
              <Li>
                Verify service health via our internal monitoring (<strong className="font-semibold text-ink-900">Grafana dashboard</strong>).
              </Li>
            </Step>
          </div>

          <div className="mt-5 flex items-start gap-2.5 rounded-[12px] border border-brand-100 bg-brand-50/60 px-4 py-3">
            <Info size={15} className="mt-0.5 shrink-0 text-brand-500" />
            <p className="text-[13px] leading-relaxed text-ink-700">
              <span className="font-semibold text-brand-600">Note:</span> For any issues, check the{" "}
              <a href="#" className="font-medium text-brand-500 hover:underline">Troubleshooting Guide</a> or reach out in{" "}
              <a href="#" className="font-medium text-brand-500 hover:underline">#devops-support</a> on Slack.
            </p>
          </div>

          <div className="mt-5 flex items-center gap-2.5 border-t border-line pt-4">
            {[
              { icon: ThumbsUp, label: "Helpful" },
              { icon: ThumbsDown, label: "Not Helpful" },
              { icon: Bookmark, label: "Save" },
              { icon: Share2, label: "Share" },
            ].map((a) => (
              <button
                key={a.label}
                className="inline-flex items-center gap-2 rounded-[10px] border border-line bg-white px-3.5 py-2 text-[12.5px] font-semibold text-ink-700 transition hover:border-brand-200 hover:text-brand-600"
              >
                <a.icon size={14} />
                {a.label}
              </button>
            ))}
          </div>
        </Card>

        {/* follow-up */}
        <div className="mt-5 flex items-center gap-2 rounded-[16px] border border-line bg-white py-1.5 pl-5 pr-1.5 shadow-[var(--shadow-card)] transition focus-within:border-brand-300 focus-within:ring-4 focus-within:ring-brand-50">
          <input
            placeholder="Ask a follow-up question..."
            className="h-10 min-w-0 flex-1 bg-transparent text-[14px] outline-none placeholder:text-ink-400"
          />
          <button
            aria-label="Send"
            className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-500 text-white shadow-[0_4px_14px_-4px_rgba(91,92,235,0.6)] transition hover:bg-brand-600"
          >
            <Send size={15} />
          </button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2.5">
          {[
            "Where can I find the service template?",
            "How to rollback a deployment?",
            "Kubernetes logging best practices?",
          ].map((s) => (
            <button
              key={s}
              className="rounded-full border border-line bg-white px-3.5 py-1.5 text-[12.5px] font-medium text-ink-700 transition hover:border-brand-200 hover:text-brand-600"
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* right rail */}
      <div className="col-span-4 space-y-5 animate-rise-1">
        <Card className="p-5">
          <div className="flex items-center justify-between">
            <p className="flex items-center gap-2 text-[15px] font-bold text-ink-900">
              Sources
              <span className="rounded-md bg-canvas px-1.5 py-0.5 text-[11.5px] font-semibold text-ink-500">8</span>
            </p>
            <CardLink href="/knowledge-sources">View all</CardLink>
          </div>
          <ul className="mt-4 space-y-4">
            {sources.map((s) => (
              <li key={s.title} className="flex items-start gap-3">
                <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-[9px] border border-line bg-white">
                  <s.icon size={16} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-semibold text-ink-900">{s.title}</p>
                  <p className="text-[11.5px] text-ink-500">{s.meta}</p>
                </div>
                <span className="rounded-md bg-emerald-50 px-1.5 py-0.5 text-[11.5px] font-bold text-emerald-600">
                  {s.score}
                </span>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="p-5">
          <p className="text-[15px] font-bold text-ink-900">Related Questions</p>
          <ul className="mt-2 divide-y divide-line">
            {related.map((q) => (
              <li key={q}>
                <button className="group flex w-full items-center justify-between gap-3 py-2.5 text-left text-[13px] font-medium text-ink-700 transition hover:text-brand-600">
                  {q}
                  <ArrowRight size={14} className="shrink-0 text-brand-400 transition-transform group-hover:translate-x-0.5" />
                </button>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="p-5">
          <p className="text-[15px] font-bold text-ink-900">Your Recent Questions</p>
          <ul className="mt-2 divide-y divide-line">
            {recent.map((q) => (
              <li key={q}>
                <button className="w-full py-2.5 text-left text-[13px] font-medium text-ink-700 transition hover:text-brand-600">
                  {q}
                </button>
              </li>
            ))}
          </ul>
          <div className="mt-2">
            <CardLink href="/saved-answers">View all history</CardLink>
          </div>
        </Card>
      </div>
    </div>
  );
}
