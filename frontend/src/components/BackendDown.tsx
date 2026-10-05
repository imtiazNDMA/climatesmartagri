export function BackendDown({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="backend-down" role="alert">
      <h1>The portal can't reach its data service</h1>
      <p>Start it from the project folder, then try again:</p>
      <pre>npm run dev</pre>
      <button type="button" onClick={onRetry}>
        Try again
      </button>
    </div>
  )
}
