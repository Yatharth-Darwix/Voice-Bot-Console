import type { BrowserTalkMessage } from '../types'

interface BrowserTalkPanelProps {
  connected: boolean
  connecting: boolean
  speaking: boolean
  muted: boolean
  sessionId: string | null
  callId: string | null
  error: string | null
  messages: BrowserTalkMessage[]
  publicKeyConfigured: boolean
}

export function BrowserTalkPanel({
  connected,
  connecting,
  speaking,
  muted,
  sessionId,
  callId,
  error,
  messages,
  publicKeyConfigured,
}: BrowserTalkPanelProps) {
  const statusLabel = connected ? 'Connected' : connecting ? 'Connecting' : 'Idle'

  return (
    <section className="panel stream-panel">
      <div className="panel-head">
        <h2>Browser Talk Session</h2>
        <p>Directly talk to the bot in this dashboard using your microphone.</p>
      </div>

      <div className="browser-status-grid">
        <article>
          <h3>Session</h3>
          <p>{statusLabel}</p>
        </article>
        <article>
          <h3>Assistant Speech</h3>
          <p>{speaking ? 'Speaking' : 'Listening/Idle'}</p>
        </article>
        <article>
          <h3>Mic</h3>
          <p>{muted ? 'Muted' : 'Unmuted'}</p>
        </article>
        <article>
          <h3>Vapi Public Key</h3>
          <p>{publicKeyConfigured ? 'Configured' : 'Missing'}</p>
        </article>
        <article>
          <h3>Session ID</h3>
          <p>{sessionId ?? 'Not created yet'}</p>
        </article>
        <article>
          <h3>Call ID</h3>
          <p>{callId ?? 'Not bound yet'}</p>
        </article>
      </div>

      {error ? <p className="error">{error}</p> : null}

      <ul className="browser-messages">
        {messages.length === 0 ? <li className="muted">No browser-session messages yet.</li> : null}
        {messages.map((msg) => (
          <li key={msg.id} data-kind={msg.kind}>
            <time>{msg.at}</time>
            <span>
              <strong>
                {msg.kind === 'assistant' ? 'Agent' : msg.kind === 'user' ? 'Client' : 'System'}:
              </strong>{' '}
              {msg.text}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
