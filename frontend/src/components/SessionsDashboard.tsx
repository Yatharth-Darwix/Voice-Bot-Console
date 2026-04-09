import { useMemo, useState } from 'react'
import type { SessionDetail, SessionSummary } from '../types'

interface SessionsDashboardProps {
  apiBaseUrl: string
  sessions: SessionSummary[]
  selectedSession: SessionDetail | null
  selectedSessionId: string | null
  loadingSessions: boolean
  loadingDetail: boolean
  error: string | null
  onRefresh: () => Promise<void>
  onSelectSession: (sessionId: string) => Promise<void>
  onBack: () => void
}

function resolveRoleKind(role: string): 'assistant' | 'user' | 'event' {
  const normalized = role.trim().toLowerCase()
  if (['assistant', 'agent', 'bot', 'ai'].includes(normalized)) {
    return 'assistant'
  }
  if (['user', 'client', 'customer', 'human', 'caller'].includes(normalized)) {
    return 'user'
  }
  return 'event'
}

function resolveRoleLabel(kind: 'assistant' | 'user' | 'event'): string {
  if (kind === 'assistant') {
    return 'Agent'
  }
  if (kind === 'user') {
    return 'Client'
  }
  return 'System'
}

function formatDisplayTime(value: string): string {
  const trimmed = value.trim()
  if (!trimmed) {
    return '--:--:--'
  }

  const numeric = Number(trimmed)
  const date = Number.isFinite(numeric)
    ? new Date(numeric > 10_000_000_000 ? numeric : numeric * 1000)
    : new Date(trimmed)

  if (Number.isNaN(date.getTime())) {
    return trimmed
  }

  return date.toLocaleTimeString()
}

export function SessionsDashboard({
  apiBaseUrl,
  sessions,
  selectedSession,
  selectedSessionId,
  loadingSessions,
  loadingDetail,
  error,
  onRefresh,
  onSelectSession,
  onBack,
}: SessionsDashboardProps) {
  const [filter, setFilter] = useState<'all' | 'transcript' | 'status' | 'tool'>('all')
  const filteredMessages = useMemo(() => {
    if (!selectedSession) {
      return []
    }

    const messages = selectedSession.messages
    if (filter === 'all') {
      return messages
    }
    if (filter === 'transcript') {
      return messages.filter((entry) => entry.event_type.includes('transcript'))
    }
    if (filter === 'status') {
      return messages.filter((entry) => entry.event_type.includes('status') || entry.event_type.includes('call-') || entry.event_type === 'hang')
    }
    return messages.filter((entry) => entry.event_type.includes('tool'))
  }, [filter, selectedSession])

  return (
    <div className="sessions-shell">
      <header className="topbar">
        <div className="topbar-title">
          <h1>Session Logs</h1>
          <p>Backend: {apiBaseUrl}</p>
        </div>
      </header>

      <main className="sessions-grid">
        <section className="panel sessions-list-panel">
          <div className="panel-head sessions-head">
            <div>
              <h2>Sessions</h2>
              <p>Track browser and phone sessions by session id and call id.</p>
            </div>
            <div className="sessions-actions">
              <button type="button" className="btn ghost" onClick={onBack}>
                Back to Dashboard
              </button>
              <button type="button" className="btn primary" onClick={() => void onRefresh()} disabled={loadingSessions}>
                {loadingSessions ? 'Refreshing…' : 'Refresh'}
              </button>
            </div>
          </div>

          {error ? <p className="error">{error}</p> : null}

          <ul className="sessions-list">
            {sessions.length === 0 ? <li className="muted">No sessions created yet.</li> : null}
            {sessions.map((session) => (
              <li
                key={session.session_id}
                data-active={selectedSessionId === session.session_id}
                onClick={() => void onSelectSession(session.session_id)}
              >
                <p className="session-id">{session.session_id}</p>
                <p>
                  <strong>{session.mode}</strong> · {session.status}
                </p>
                <p>
                  {session.industry} / {session.use_case}
                </p>
                <p className="muted">Call: {session.call_id ?? 'pending'}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel session-detail-panel">
          <div className="panel-head">
            <h2>Session Detail</h2>
            <p>{loadingDetail ? 'Loading session details…' : 'Transcript and runtime details'}</p>
          </div>

          {!selectedSession ? <p className="muted">Select a session to inspect.</p> : null}

          {selectedSession ? (
            <>
              <div className="session-detail-grid">
                <article>
                  <h3>Session ID</h3>
                  <p>{selectedSession.session_id}</p>
                </article>
                <article>
                  <h3>Mode / Status</h3>
                  <p>
                    {selectedSession.mode} / {selectedSession.status}
                  </p>
                </article>
                <article>
                  <h3>Call ID</h3>
                  <p>{selectedSession.call_id ?? 'pending'}</p>
                </article>
                <article>
                  <h3>Company</h3>
                  <p>{selectedSession.company}</p>
                </article>
              </div>

              {selectedSession.vapi_fetch_error ? <p className="error">{selectedSession.vapi_fetch_error}</p> : null}

              <h3 className="transcript-heading">Transcript / Messages</h3>
              <div className="mode-switch" role="tablist" aria-label="Log filter">
                <button type="button" className={`mode-btn ${filter === 'all' ? 'active' : ''}`} onClick={() => setFilter('all')}>
                  All
                </button>
                <button type="button" className={`mode-btn ${filter === 'transcript' ? 'active' : ''}`} onClick={() => setFilter('transcript')}>
                  Transcript
                </button>
                <button type="button" className={`mode-btn ${filter === 'status' ? 'active' : ''}`} onClick={() => setFilter('status')}>
                  Status
                </button>
                <button type="button" className={`mode-btn ${filter === 'tool' ? 'active' : ''}`} onClick={() => setFilter('tool')}>
                  Tool
                </button>
              </div>
              <ul className="browser-messages">
                {filteredMessages.length === 0 ? <li className="muted">No entries for selected filter.</li> : null}
                {filteredMessages.map((entry, idx) => (
                  <li key={`${entry.at}-${idx}`} data-kind={resolveRoleKind(entry.role)}>
                    <time>{formatDisplayTime(entry.at)}</time>
                    <span>
                      <strong>{resolveRoleLabel(resolveRoleKind(entry.role))}:</strong>{' '}
                      {entry.text}{' '}
                      <small className="muted">[{entry.event_type} via {entry.source}]</small>
                    </span>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </section>
      </main>
    </div>
  )
}
