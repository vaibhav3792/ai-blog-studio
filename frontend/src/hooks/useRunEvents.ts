import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { RunEvent } from "../lib/types";

/** Subscribes to the server-sent events of one generation run. */
export function useRunEvents(blogId: number | null): RunEvent[] {
  const [events, setEvents] = useState<RunEvent[]>([]);

  useEffect(() => {
    setEvents([]);
    if (blogId == null) return;
    const source = new EventSource(api.eventsUrl(blogId));
    // The server replays every event on each (re)connect, so start from a clean list.
    source.onopen = () => setEvents([]);
    source.onmessage = (msg) => {
      const event = JSON.parse(msg.data) as RunEvent;
      setEvents((prev) => [...prev, event]);
      if (event.type === "done" || event.type === "error") source.close();
    };
    return () => source.close();
  }, [blogId]);

  return events;
}
