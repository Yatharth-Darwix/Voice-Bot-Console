import type { TimelineEvent } from '../types'

interface StatusPanelProps {
  running: boolean
  error: string | null
  timeline: TimelineEvent[]
  apiBaseUrl: string
  sessionId?: string | null
  onOpenLogs?: () => void
  webhookPublicBaseUrl: string
  onWebhookPublicBaseUrlChange: (value: string) => void
  onSyncWebhook: () => Promise<void>
  webhookSyncing: boolean
  webhookSyncResult: string | null
  webhookSyncError: string | null
}

export function StatusPanel({
  running,
  error,
  timeline,
  apiBaseUrl,
  sessionId,
  onOpenLogs,
  webhookPublicBaseUrl,
  onWebhookPublicBaseUrlChange,
  onSyncWebhook,
  webhookSyncing,
  webhookSyncResult,
  webhookSyncError,
}: StatusPanelProps) {
  return (
    <section className="panel status-panel">
      <div className="panel-head">
        <h2>Control Plane Status</h2>
        <p>Backend: <code>{apiBaseUrl}</code></p>
        {sessionId ? (
          <p>
            Session: <code>{sessionId}</code>
          </p>
        ) : null}
        {onOpenLogs ? (
          <button type="button" className="btn ghost" onClick={onOpenLogs}>
            Open Logbook
          </button>
        ) : null}
      </div>

      <div className="status-pill" data-running={running}>
        <span className="dot" />
        <strong>{running ? 'Active' : 'Idle'}</strong>
      </div>

      <div className="webhook-tools">
        <h3>Webhook Sync</h3>
        <p className="muted">Uses `VAPI_SERVER_PUBLIC_BASE_URL` from backend env if set, else auto-detect ngrok or pasted URL.</p>
        <div className="webhook-controls">
          <input
            value={webhookPublicBaseUrl}
            onChange={(event) => onWebhookPublicBaseUrlChange(event.target.value)}
            placeholder="https://xxxx.ngrok-free.app (optional)"
          />
          <button type="button" className="btn ghost" onClick={() => void onSyncWebhook()} disabled={webhookSyncing}>
            {webhookSyncing ? 'Syncing…' : 'Sync Vapi Webhook'}
          </button>
        </div>
        {webhookSyncResult ? <p className="muted">{webhookSyncResult}</p> : null}
        {webhookSyncError ? <p className="error">{webhookSyncError}</p> : null}
      </div>

      {error ? <p className="error">{error}</p> : null}

      <ul className="timeline">
        {timeline.length === 0 ? <li className="muted">No events yet.</li> : null}
        {timeline.map((event) => (
          <li key={event.id} data-kind={event.kind}>
            <time>{event.at}</time>
            <span>{event.message}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
