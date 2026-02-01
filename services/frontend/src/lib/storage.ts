const KEY_API_BASE_URL = "sec_scanner_api_base_url";
const KEY_API_KEY = "sec_scanner_api_key";
const KEY_THEME = "sec_scanner_theme";
const KEY_ONBOARDING = "sec_scanner_onboarding_completed";

export function getTheme(): "light" | "dark" | null {
  try {
    const v = localStorage.getItem(KEY_THEME);
    if (v === "light" || v === "dark") return v;
    return null;
  } catch {
    return null;
  }
}

export function setTheme(v: "light" | "dark") {
  localStorage.setItem(KEY_THEME, v);
  document.documentElement.setAttribute("data-theme", v);
}

export function getApiBaseUrl(defaultValue: string): string {
  try {
    const v = localStorage.getItem(KEY_API_BASE_URL);
    return v && v.trim() ? v.trim().replace(/\/+$/, "") : defaultValue;
  } catch {
    return defaultValue;
  }
}

export function setApiBaseUrl(v: string) {
  localStorage.setItem(KEY_API_BASE_URL, String(v || "").trim().replace(/\/+$/, ""));
}

export function getApiKey(): string | null {
  try {
    const v = localStorage.getItem(KEY_API_KEY);
    return v && v.trim() ? v.trim() : null;
  } catch {
    return null;
  }
}

export function setApiKey(v: string) {
  const clean = String(v || "").trim();
  if (!clean) {
    localStorage.removeItem(KEY_API_KEY);
    return;
  }
  localStorage.setItem(KEY_API_KEY, clean);
}

export function hasCompletedOnboarding(): boolean {
  try {
    return localStorage.getItem(KEY_ONBOARDING) === "true";
  } catch {
    return false;
  }
}

export function markOnboardingComplete(): void {
  try {
    localStorage.setItem(KEY_ONBOARDING, "true");
  } catch {
    // Ignore storage errors
  }
}

export function resetOnboarding(): void {
  try {
    localStorage.removeItem(KEY_ONBOARDING);
  } catch {
    // Ignore storage errors
  }
}

