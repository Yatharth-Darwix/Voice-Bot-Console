import { useMemo, useState } from 'react'

interface DirectCallPageProps {
  buildApiUrl: (path: string) => string
  onBack: () => void
  onOpenMain: () => void
  onOpenMissionControl: () => void
}

const PRESET_TRIGGER_NUMBERS = {
  first: '+918435527927',
  second: '+919871729818',
} as const

type TriggerNumberMode = 'preset_first' | 'preset_second' | 'custom'

export function DirectCallPage({ buildApiUrl, onBack, onOpenMain, onOpenMissionControl }: DirectCallPageProps) {
  const [triggerNumberMode, setTriggerNumberMode] = useState<TriggerNumberMode>('preset_first')
  const [customPhoneNumber, setCustomPhoneNumber] = useState('')
  const [firstMessage, setFirstMessage] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<string>('Ready to trigger a call.')
  const [error, setError] = useState<string | null>(null)

  const selectedPhoneNumber = useMemo(() => {
    if (triggerNumberMode === 'preset_first') {
      return PRESET_TRIGGER_NUMBERS.first
    }
    if (triggerNumberMode === 'preset_second') {
      return PRESET_TRIGGER_NUMBERS.second
    }
    return customPhoneNumber.trim()
  }, [customPhoneNumber, triggerNumberMode])

  const canSubmit = useMemo(
    () => selectedPhoneNumber.length > 0 && !submitting,
    [selectedPhoneNumber, submitting],
  )

  const firstMessageActive = firstMessage.trim().length > 0
  const systemPromptActive = systemPrompt.trim().length > 0

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    setResult('Triggering call…')

    try {
      const response = await fetch(buildApiUrl('/api/direct-assistant-call'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          phone_number: selectedPhoneNumber,
          first_message: firstMessage,
          system_prompt: systemPrompt,
        }),
      })

      const text = await response.text()
      if (!response.ok) {
        throw new Error(text || `Request failed with ${response.status}`)
      }

      setResult(text)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to trigger the call')
      setResult('Call request failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="app-shell trigger-shell">
      <header className="topbar">
        <div className="topbar-title">
          <h1>Trigger Lab</h1>
          <p>Rapid outbound test workspace for direct assistant call experiments.</p>
        </div>
        <div className="topbar-actions">
          <button type="button" className="btn ghost" onClick={onOpenMain}>
            Home Hub
          </button>
          <button type="button" className="btn ghost" onClick={onOpenMissionControl}>
            Mission Control
          </button>
          <button type="button" className="btn ghost" onClick={onBack}>
            Back to Mission Control
          </button>
        </div>
      </header>

      <section className="panel trigger-hero">
        <div>
          <p className="mission-kicker">Rapid Outbound Experimentation</p>
          <h2>Ship call tests in seconds with controlled overrides</h2>
          <p>
            Pick your target line, optionally tweak first-message and system behavior, then launch a direct assistant call through
            the control API.
          </p>
        </div>
      </section>

      <main className="trigger-lab-grid">
        <section className="panel trigger-form-panel">
          <div className="panel-head">
            <h2>Launch Direct Call</h2>
            <p>Adjust dial target and optional prompt overrides while using the backend-configured assistant.</p>
          </div>

          <form onSubmit={submit} className="grid">
            <label>
              <span>Trigger Number</span>
              <select
                value={triggerNumberMode}
                onChange={(event) => setTriggerNumberMode(event.target.value as TriggerNumberMode)}
              >
                <option value="preset_first">1 {PRESET_TRIGGER_NUMBERS.first}</option>
                <option value="preset_second">2 {PRESET_TRIGGER_NUMBERS.second}</option>
                <option value="custom">Use another number</option>
              </select>
            </label>

            {triggerNumberMode === 'custom' ? (
              <label>
                <span>Custom Number</span>
                <input
                  required
                  value={customPhoneNumber}
                  onChange={(event) => setCustomPhoneNumber(event.target.value)}
                  placeholder="+919876543210"
                />
              </label>
            ) : null}

            <label>
              <span>First Message</span>
              <textarea
                rows={4}
                value={firstMessage}
                onChange={(event) => setFirstMessage(event.target.value)}
                placeholder="Leave blank to keep the current assistant first message"
              />
            </label>

            <label>
              <span>Main System Prompt</span>
              <textarea
                rows={14}
                value={systemPrompt}
                onChange={(event) => setSystemPrompt(event.target.value)}
                placeholder="Leave blank to keep the current assistant system prompt"
              />
            </label>

            <div className="actions">
              <button type="submit" className="btn primary" disabled={!canSubmit}>
                {submitting ? 'Triggering…' : 'Trigger Call'}
              </button>
              <button type="button" className="btn ghost" onClick={onBack}>
                Cancel
              </button>
            </div>
          </form>
        </section>

        <section className="panel trigger-side-panel">
          <div className="panel-head">
            <h2>Run Summary</h2>
            <p>Review current launch configuration before dispatch.</p>
          </div>
          <div className="mission-meta-grid">
            <article>
              <h3>Dial Target</h3>
              <p>{selectedPhoneNumber || 'Not selected'}</p>
            </article>
            <article>
              <h3>First Message</h3>
              <p>{firstMessageActive ? 'Override enabled' : 'Default assistant greeting'}</p>
            </article>
            <article>
              <h3>System Prompt</h3>
              <p>{systemPromptActive ? 'Override enabled' : 'Default assistant prompt'}</p>
            </article>
            <article>
              <h3>Submit State</h3>
              <p>{submitting ? 'Running' : canSubmit ? 'Ready' : 'Blocked'}</p>
            </article>
          </div>

          <div className="trigger-notes">
            <h3>Operator Notes</h3>
            <ul>
              <li>Use preset numbers for repeatable benchmark tests.</li>
              <li>Add first-message overrides for greeting A/B checks.</li>
              <li>Use system prompt override for scenario drills only.</li>
            </ul>
          </div>
        </section>

        <section className="panel trigger-output-panel">
          <div className="panel-head">
            <h2>Execution Output</h2>
            <p>Latest control-plane response from <code>/api/direct-assistant-call</code>.</p>
          </div>

          {error ? <p className="error">{error}</p> : null}
          <pre className="prompt-box">{result}</pre>
        </section>
      </main>
    </div>
  )
}