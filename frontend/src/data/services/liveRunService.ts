export function getLiveRunSocketUrl(): string {
  return import.meta.env.VITE_WS_URL ?? "ws://localhost:8000/ws/run";
}
