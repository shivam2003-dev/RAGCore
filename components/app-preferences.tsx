"use client";

import { useEffect } from "react";
import { applySettingsToDocument, loadSettings, SETTINGS_EVENT, type SettingsState } from "@/lib/settings-store";

export function AppPreferences() {
  useEffect(() => {
    applySettingsToDocument(loadSettings());

    function handleSettings(event: Event) {
      const detail = (event as CustomEvent<SettingsState>).detail;
      applySettingsToDocument(detail ?? loadSettings());
    }

    function handleStorage(event: StorageEvent) {
      if (event.key === "kimbal.settings.v1") {
        applySettingsToDocument(loadSettings());
      }
    }

    function handleSystemTheme() {
      applySettingsToDocument(loadSettings());
    }

    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    window.addEventListener(SETTINGS_EVENT, handleSettings);
    window.addEventListener("storage", handleStorage);
    media?.addEventListener("change", handleSystemTheme);
    return () => {
      window.removeEventListener(SETTINGS_EVENT, handleSettings);
      window.removeEventListener("storage", handleStorage);
      media?.removeEventListener("change", handleSystemTheme);
    };
  }, []);

  return null;
}
