"use client";

export type SettingsState = {
  organizationName: string;
  organizationId: string;
  timeZone: string;
  language: string;
  dateFormat: string;
  timeFormat: string;
  theme: "Light" | "Dark" | "System";
  accentColor: string;
  defaultSearchModel: string;
  topK: string;
  chunkSize: string;
  retrievalMode: string;
  rerankerModel: string;
  generationModel: string;
  autoSync: boolean;
  reindexInterval: string;
  incrementalIndexing: boolean;
  answerFeedback: boolean;
  querySuggestions: boolean;
  sourceCitations: boolean;
  analyticsTracking: boolean;
  emailDigest: boolean;
  securityAlerts: boolean;
};

export const defaultSettings: SettingsState = {
  organizationName: "Kimbal",
  organizationId: "kimbal-tech",
  timeZone: "(GMT+05:30) Asia/Kolkata",
  language: "English",
  dateFormat: "DD MMM, YYYY",
  timeFormat: "12-hour (AM/PM)",
  theme: "Light",
  accentColor: "#5b5ceb",
  defaultSearchModel: "text-embedding-3-small",
  topK: "8",
  chunkSize: "400 tokens",
  retrievalMode: "Hybrid (Vector + Keyword)",
  rerankerModel: "None",
  generationModel: "anthropic/claude-haiku-4.5",
  autoSync: true,
  reindexInterval: "Daily",
  incrementalIndexing: true,
  answerFeedback: true,
  querySuggestions: true,
  sourceCitations: true,
  analyticsTracking: true,
  emailDigest: true,
  securityAlerts: true,
};

const SETTINGS_KEY = "kimbal.settings.v1";
export const SETTINGS_EVENT = "kimbal:settings-changed";

export function loadSettings(): SettingsState {
  if (typeof window === "undefined") return defaultSettings;
  const raw = window.localStorage.getItem(SETTINGS_KEY);
  if (!raw) return defaultSettings;
  try {
    return { ...defaultSettings, ...(JSON.parse(raw) as Partial<SettingsState>) };
  } catch {
    window.localStorage.removeItem(SETTINGS_KEY);
    return defaultSettings;
  }
}

export function saveSettings(settings: SettingsState) {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    applySettingsToDocument(settings);
    window.dispatchEvent(new CustomEvent(SETTINGS_EVENT, { detail: settings }));
  }
}

export function applySettingsToDocument(settings: SettingsState) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  const systemDark =
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  const theme =
    settings.theme === "System" ? (systemDark ? "dark" : "light") : settings.theme.toLowerCase();
  root.dataset.theme = theme;
  const accent = normalizeHex(settings.accentColor) ?? defaultSettings.accentColor;
  root.style.setProperty("--color-brand-500", accent);
  root.style.setProperty("--color-brand-600", shadeHex(accent, -0.1));
  root.style.setProperty("--color-brand-400", shadeHex(accent, 0.14));
  root.style.setProperty("--color-brand-300", shadeHex(accent, 0.28));
  root.style.setProperty("--color-brand-100", shadeHex(accent, 0.76));
  root.style.setProperty("--color-brand-50", shadeHex(accent, 0.9));
}

function normalizeHex(value: string): string | null {
  const trimmed = value.trim();
  if (/^#[0-9a-fA-F]{6}$/.test(trimmed)) return trimmed;
  return null;
}

function shadeHex(hex: string, amount: number): string {
  const clean = hex.slice(1);
  const channels = [0, 2, 4].map((start) => parseInt(clean.slice(start, start + 2), 16));
  const next = channels.map((channel) => {
    const target = amount >= 0 ? 255 : 0;
    return Math.round(channel + (target - channel) * Math.abs(amount));
  });
  return `#${next.map((channel) => channel.toString(16).padStart(2, "0")).join("")}`;
}
