import { useCallback, useState } from "react";

type QueuedStep = { projectId: string; direction: "advance" | "reverse" };

const QUEUE_KEY = "weftmark_step_queue";

function loadQueue(): QueuedStep[] {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_KEY) ?? "[]");
  } catch {
    return [];
  }
}

export function useStepQueue() {
  const [pending, setPending] = useState(() => loadQueue().length);

  const enqueue = useCallback((projectId: string, direction: "advance" | "reverse") => {
    const q = loadQueue();
    q.push({ projectId, direction });
    localStorage.setItem(QUEUE_KEY, JSON.stringify(q));
    setPending(q.length);
  }, []);

  const drainAll = useCallback(
    async (flush: (projectId: string, direction: "advance" | "reverse") => Promise<void>) => {
      let q = loadQueue();
      while (q.length > 0) {
        const [step, ...rest] = q;
        try {
          await flush(step.projectId, step.direction);
        } catch {
          // Optimistic update already applied — drop on failure rather than blocking the queue
        }
        localStorage.setItem(QUEUE_KEY, JSON.stringify(rest));
        setPending(rest.length);
        q = rest;
      }
    },
    []
  );

  return { enqueue, pending, drainAll };
}
