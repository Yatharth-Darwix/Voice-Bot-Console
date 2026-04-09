interface PromptStreamProps {
  phase: string
  promptText: string
  firstMessage: string
  callId: string | null
  sessionStatus: string
  sessionFetchError: string | null
  liveMessages: {
    at: string
    role: string
    text: string
    source: string
    event_type: string
  }[]
}

function roleLabel(role: string): 'Agent' | 'Client' | 'System' {
  const normalized = role.trim().toLowerCase()
  if (['assistant', 'agent', 'bot', 'ai'].includes(normalized)) {
    return 'Agent'
  }
  if (['user', 'client', 'customer', 'caller', 'human'].includes(normalized)) {
    return 'Client'
  }
  return 'System'
}

function roleKind(role: string): 'assistant' | 'user' | 'event' {
  const label = roleLabel(role)
  if (label === 'Agent') {
    return 'assistant'
  }
  if (label === 'Client') {
    return 'user'
  }
  return 'event'
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

export function PromptStream({
  phase,
  promptText,
  firstMessage,
  callId,
  sessionStatus,
  sessionFetchError,
  liveMessages,
}: PromptStreamProps) {
  return (
    <section className="panel stream-panel">
      <div className="panel-head">
        <h2>Realtime Prompt Stream</h2>
        <p>Current phase: <strong>{phase}</strong></p>
      </div>

      <pre className="prompt-box" aria-live="polite">
        {promptText || 'Prompt tokens will appear here as they stream from OpenAI Realtime.'}
      </pre>

      <div className="meta-grid">
        <article>
          <h3>First Message</h3>
          <p>{firstMessage || 'Waiting for greeting generation…'}</p>
        </article>
        <article>
          <h3>Call ID</h3>
          <p>{callId ?? 'Not created yet'}</p>
        </article>
        <article>
          <h3>Session Status</h3>
          <p>{sessionStatus || 'idle'}</p>
        </article>
      </div>

      <h3 className="transcript-heading">Live Call Transcript</h3>
      <ul className="browser-messages">
        {liveMessages.length === 0 ? (
          <li className="muted">
            Waiting for transcript events. Make sure webhook sync is configured and call is in progress.
            {sessionFetchError ? ` Backend fetch detail: ${sessionFetchError}` : ''}
          </li>
        ) : null}
        {liveMessages.map((entry, idx) => (
          <li key={`${entry.at}-${idx}`} data-kind={roleKind(entry.role)}>
            <time>{formatDisplayTime(entry.at)}</time>
            <span>
              <strong>{roleLabel(entry.role)}:</strong> {entry.text}{' '}
              <small className="muted">[{entry.event_type} via {entry.source}]</small>
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
