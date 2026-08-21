import { useEffect, useState } from "react";

export interface ApiState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

export function useApi<T>(loader: (signal: AbortSignal) => Promise<T>, keys: unknown[]) {
  const requestKey = JSON.stringify(keys);
  const [state, setState] = useState<ApiState<T> & { completedKey: string | null }>({
    data: null,
    error: null,
    loading: true,
    completedKey: null,
  });

  useEffect(() => {
    const controller = new AbortController();
    loader(controller.signal)
      .then((data) => setState({ data, error: null, loading: false, completedKey: requestKey }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          data: null,
          error: error instanceof Error ? error.message : "Unable to load data.",
          loading: false,
          completedKey: requestKey,
        });
      });
    return () => controller.abort();
    // Keys deliberately control request identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, keys);

  if (state.completedKey !== requestKey) {
    return { data: null, error: null, loading: true };
  }
  return state;
}
