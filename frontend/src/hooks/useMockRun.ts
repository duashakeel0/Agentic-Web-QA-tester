import { useEffect, useState } from "react";
import { fetchMockRun } from "../data/services/testRunService";
import type { TestRunResult } from "../types/testRun";

export function useMockRun() {
  const [result, setResult] = useState<TestRunResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchMockRun()
      .then(setResult)
      .catch((err: Error) => setError(err.message));
  }, []);

  return { result, error };
}
