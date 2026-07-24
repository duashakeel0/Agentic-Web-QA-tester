import type { TestRunResult } from "../../types/testRun";

const API_BASE = "http://localhost:8000/api";

export async function fetchMockRun(): Promise<TestRunResult> {
  const response = await fetch(`${API_BASE}/mock-run`);
  if (!response.ok) {
    throw new Error(`Backend returned ${response.status}`);
  }
  return response.json();
}
