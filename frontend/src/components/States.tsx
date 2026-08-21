export function LoadingState({ label = "Loading intelligence…" }: { label?: string }) {
  return (
    <div className="state-panel" role="status">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="state-panel state-panel--error" role="alert">
      <strong>Data could not be loaded</strong>
      <span>{message}</span>
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return <div className="state-panel state-panel--empty">{message}</div>;
}
