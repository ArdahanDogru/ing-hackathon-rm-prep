// Check marks kept per run in local storage (browser only, not in the card).
import { useEffect, useState } from "react";

function load(key: string): boolean[] {
  try {
    const v = JSON.parse(localStorage.getItem(key) ?? "[]");
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

/** [checks, toggle(i)] for the list stored under `key`. */
export function useChecks(key: string): [boolean[], (i: number) => void] {
  const [checks, setChecks] = useState<boolean[]>(() => load(key));
  useEffect(() => setChecks(load(key)), [key]);
  const toggle = (i: number) =>
    setChecks((c) => {
      const next = [...c];
      next[i] = !next[i];
      try {
        localStorage.setItem(key, JSON.stringify(next));
      } catch {
        // storage blocked: the checks stay for this page only
      }
      return next;
    });
  return [checks, toggle];
}
