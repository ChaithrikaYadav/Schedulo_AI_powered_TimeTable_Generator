// Custom React hooks for Schedulo frontend
// Import individual hooks: import { useLocalStorage } from "@/hooks/useLocalStorage"

import { useState, useEffect } from "react";

/**
 * Persist a value in localStorage, synced with component state.
 * @example const [apiKey, setApiKey] = useLocalStorage("groq_key", "");
 */
export function useLocalStorage<T>(key: string, defaultValue: T): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const stored = localStorage.getItem(key);
      return stored !== null ? JSON.parse(stored) as T : defaultValue;
    } catch {
      return defaultValue;
    }
  });

  const set = (v: T) => {
    try {
      localStorage.setItem(key, JSON.stringify(v));
    } catch {
      // localStorage unavailable (private mode / quota exceeded) — silently ignore
    }
    setValue(v);
  };

  return [value, set];
}

/**
 * Debounce a value — only updates after `delay` ms of no changes.
 * Useful for search inputs that trigger API calls.
 */
export function useDebounce<T>(value: T, delay = 400): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}
