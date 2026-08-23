import { useState } from "react";

/**
 * Like useState, but the value survives navigating away and back (sessionStorage-backed).
 * Clears when the tab closes, so stale agent output never lingers across browser sessions.
 */
export function useSessionState<T>(key: string, initial: T): [T, (value: T) => void] {
  const [state, setState] = useState<T>(() => {
    try {
      const stored = window.sessionStorage.getItem(key);
      if (stored !== null) return JSON.parse(stored) as T;
    } catch {
      // Malformed or blocked storage; fall through to the initial value.
    }
    return initial;
  });

  const setPersisted = (value: T) => {
    setState(value);
    try {
      if (value === null || value === undefined) {
        window.sessionStorage.removeItem(key);
      } else {
        window.sessionStorage.setItem(key, JSON.stringify(value));
      }
    } catch {
      // Storage may be unavailable (private browsing, disabled storage); state still works in-memory.
    }
  };

  return [state, setPersisted];
}
