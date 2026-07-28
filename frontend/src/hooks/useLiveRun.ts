import { useCallback, useEffect, useRef, useState } from "react";
import { getLiveRunSocketUrl } from "../data/services/liveRunService";
import type { LiveRunMessage } from "../types/liveRun";

export function useLiveRun() {
  const [log, setLog] = useState<string[]>([]);
  const [result, setResult] = useState<{ url: string; title: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);

  const start = useCallback((url: string) => {
    socketRef.current?.close();

    setLog([]);
    setResult(null);
    setError(null);
    setRunning(true);

    const socket = new WebSocket(getLiveRunSocketUrl());
    socketRef.current = socket;

    socket.onopen = () => socket.send(JSON.stringify({ url }));

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data) as LiveRunMessage;

      if (data.type === "status") {
        setLog((prev) => [...prev, data.message]);
      } else if (data.type === "done") {
        setLog((prev) => [...prev, data.message]);
        setResult({ url: data.url, title: data.title });
        setRunning(false);
        socket.close();
      } else if (data.type === "error") {
        setError(data.message);
        setRunning(false);
        socket.close();
      }
    };

    socket.onerror = () => {
      setError("Could not connect to the backend WebSocket.");
      setRunning(false);
    };

    socket.onclose = () => setRunning(false);
  }, []);

  useEffect(() => {
    return () => {
      socketRef.current?.close();
    };
  }, []);

  return { log, result, error, running, start };
}
