import { useEffect, useMemo, useState } from 'react'
import { BrowserTalkPanel } from './components/BrowserTalkPanel'
import { CallForm } from './components/CallForm'
import { DirectCallPage } from './components/DirectCallPage'
import { MainDashboard } from './components/MainDashboard'
import { PromptStream } from './components/PromptStream'
import { SessionsDashboard } from './components/SessionsDashboard'
import { StatusPanel } from './components/StatusPanel'
import { useBrowserTalk } from './hooks/useBrowserTalk'
import { useCallPipeline } from './hooks/useCallPipeline'
import { useSessionLogs } from './hooks/useSessionLogs'
import type { InteractionMode } from './types'

const LANDING_ALIASES = ['/', '/main', '/main/']
const MISSION_CONTROL_ALIASES = ['/mission-control', '/mission-control/']
const TRIGGER_LAB_ALIASES = ['/trigger-lab', '/trigger-lab/', '/playground', '/playground/']

function App() {
  const [interactionMode, setInteractionMode] = useState<InteractionMode>('phone')
  const [path, setPath] = useState<string>(window.location.pathname)
  const [webhookPublicBaseUrl, setWebhookPublicBaseUrl] = useState('')
  const [webhookSyncing, setWebhookSyncing] = useState(false)
  const [webhookSyncResult, setWebhookSyncResult] = useState<string | null>(null)
  const [webhookSyncError, setWebhookSyncError] = useState<string | null>(null)

  const {
    apiBaseUrl,
    running,
    canStart,
    error,
    phase,
    timeline,
    systemPrompt,
    firstMessage,
    callId,
    sessionId,
    sessionStatus,
    sessionFetchError,
    liveMessages,
    start,
    cancel,
  } = useCallPipeline()

  const {
    connected: browserConnected,
    connecting: browserConnecting,
    speaking: browserSpeaking,
    muted: browserMuted,
    error: browserError,
    messages: browserMessages,
    timeline: browserTimeline,
    publicKeyConfigured,
    start: startBrowserTalk,
    stop: stopBrowserTalk,
    toggleMute: toggleBrowserMute,
    sessionId: browserSessionId,
    callId: browserCallId,
  } = useBrowserTalk()

  const {
    apiBaseUrl: logsApiBase,
    sessions,
    selectedSession,
    selectedSessionId,
    loadingSessions,
    loadingDetail,
    error: logsError,
    refresh,
    selectSession,
  } = useSessionLogs()

  const anyFlowRunning = running || browserConnected || browserConnecting

  const buildApiUrl = (path: string): string => {
    const configured = import.meta.env.VITE_API_BASE_URL ?? ''
    if (!configured) {
      return path
    }
    return `${configured.replace(/\/$/, '')}${path}`
  }

  const syncWebhook = async () => {
    if (webhookSyncing) {
      return
    }

    setWebhookSyncing(true)
    setWebhookSyncResult(null)
    setWebhookSyncError(null)

    try {
      const response = await fetch(buildApiUrl('/api/vapi/configure-webhook'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          public_base_url: webhookPublicBaseUrl.trim() || null,
        }),
      })

      if (!response.ok) {
        const detail = await response.text()
        throw new Error(`API ${response.status}: ${detail}`)
      }

      const payload = (await response.json()) as { webhook_url: string; assistant_id: string }
      setWebhookSyncResult(`Assistant ${payload.assistant_id} now points to ${payload.webhook_url}`)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to sync webhook'
      setWebhookSyncError(message)
    } finally {
      setWebhookSyncing(false)
    }
  }

  useEffect(() => {
    if (interactionMode !== 'phone' && running) {
      void cancel()
    }
  }, [cancel, interactionMode, running])

  const phoneSessionActive = ['created', 'prompt_ready', 'dialing', 'in_progress', 'ready_for_browser_talk'].includes(sessionStatus)
  const statusRunning = interactionMode === 'phone' ? running || phoneSessionActive : browserConnected || browserConnecting
  const statusError = interactionMode === 'phone' ? error : browserError
  const statusTimeline = interactionMode === 'phone' ? timeline : browserTimeline
  const currentSessionId = interactionMode === 'phone' ? sessionId : browserSessionId
  const modeLabel = interactionMode === 'phone' ? 'Phone Pipeline' : 'Browser Voice Studio'

  const canStartBrowser = useMemo(
    () => !browserConnected && !browserConnecting && !running,
    [browserConnected, browserConnecting, running],
  )
  const canStopBrowser = useMemo(
    () => browserConnected || browserConnecting || Boolean(browserSessionId) || browserMessages.length > 0 || browserTimeline.length > 0 || Boolean(browserError),
    [browserConnected, browserConnecting, browserError, browserMessages.length, browserSessionId, browserTimeline.length],
  )

  useEffect(() => {
    const onPopState = () => setPath(window.location.pathname)
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const navigate = (to: string) => {
    if (window.location.pathname === to) {
      return
    }
    window.history.pushState({}, '', to)
    setPath(to)
  }

  if (path === '/sessions' || path === '/sessions/') {
    return (
      <SessionsDashboard
        apiBaseUrl={logsApiBase}
        sessions={sessions}
        selectedSession={selectedSession}
        selectedSessionId={selectedSessionId}
        loadingSessions={loadingSessions}
        loadingDetail={loadingDetail}
        error={logsError}
        onRefresh={refresh}
        onSelectSession={selectSession}
        onBack={() => navigate('/mission-control')}
        onOpenMain={() => navigate('/')}
      />
    )
  }

  if (TRIGGER_LAB_ALIASES.includes(path)) {
    return (
      <DirectCallPage
        buildApiUrl={buildApiUrl}
        onBack={() => navigate('/mission-control')}
        onOpenMain={() => navigate('/')}
        onOpenMissionControl={() => navigate('/mission-control')}
      />
    )
  }

  if (LANDING_ALIASES.includes(path)) {
    return <MainDashboard onOpenMissionControl={() => navigate('/mission-control')} onOpenTriggerLab={() => navigate('/trigger-lab')} />
  }

  if (!MISSION_CONTROL_ALIASES.includes(path)) {
    return <MainDashboard onOpenMissionControl={() => navigate('/mission-control')} onOpenTriggerLab={() => navigate('/trigger-lab')} />
  }

  return (
    <div className="app-shell mission-shell">
      <header className="topbar">
        <div className="topbar-title">
          <h1>Mission Control</h1>
          <p>Run call operations, browser voice sessions, and realtime prompt orchestration from one command surface.</p>
        </div>
        <div className="topbar-actions">
          <button type="button" className="btn ghost" onClick={() => navigate('/')}>
            Home Hub
          </button>
          <button type="button" className="btn ghost" onClick={() => navigate('/trigger-lab')}>
            Trigger Lab
          </button>
          <button type="button" className="btn ghost" onClick={() => navigate('/sessions')}>
            Ops Logs
          </button>
        </div>
      </header>

      <section className="panel mission-hero">
        <div>
          <p className="mission-kicker">Realtime Operations Surface</p>
          <h2>Coordinate prompts, channels, and live session telemetry</h2>
          <p>
            Build and execute production-grade voice interactions with a single operator flow. Switch channel mode, monitor state,
            and launch with confidence.
          </p>
        </div>
        <div className="mission-meta-grid" aria-label="Mission telemetry">
          <article>
            <h3>Mode</h3>
            <p>{modeLabel}</p>
          </article>
          <article>
            <h3>System State</h3>
            <p>{statusRunning ? 'Live' : 'Standby'}</p>
          </article>
          <article>
            <h3>Current Session</h3>
            <p>{currentSessionId ?? 'Not started'}</p>
          </article>
          <article>
            <h3>Timeline Events</h3>
            <p>{statusTimeline.length}</p>
          </article>
        </div>
      </section>

      <main className="mission-grid">
        <CallForm
          interactionMode={interactionMode}
          onInteractionModeChange={setInteractionMode}
          disableModeSwitch={anyFlowRunning}
          runningPhone={running}
          canStartPhone={canStart && !browserConnected && !browserConnecting}
          onStartPhone={start}
          onCancelPhone={cancel}
          browserConnected={browserConnected}
          browserConnecting={browserConnecting}
          browserMuted={browserMuted}
          canStopBrowser={canStopBrowser}
          canStartBrowser={canStartBrowser}
          onStartBrowser={startBrowserTalk}
          onStopBrowser={stopBrowserTalk}
          onToggleBrowserMute={toggleBrowserMute}
        />

        {interactionMode === 'phone' ? (
          <PromptStream
            phase={phase}
            promptText={systemPrompt}
            firstMessage={firstMessage}
            callId={callId}
            sessionStatus={sessionStatus}
            sessionFetchError={sessionFetchError}
            liveMessages={liveMessages}
          />
        ) : (
          <BrowserTalkPanel
            connected={browserConnected}
            connecting={browserConnecting}
            speaking={browserSpeaking}
            muted={browserMuted}
            sessionId={browserSessionId}
            callId={browserCallId}
            error={browserError}
            messages={browserMessages}
            publicKeyConfigured={publicKeyConfigured}
          />
        )}

        <StatusPanel
          running={statusRunning}
          error={statusError}
          timeline={statusTimeline}
          apiBaseUrl={apiBaseUrl}
          sessionId={currentSessionId}
          onOpenLogs={() => navigate('/sessions')}
          webhookPublicBaseUrl={webhookPublicBaseUrl}
          onWebhookPublicBaseUrlChange={setWebhookPublicBaseUrl}
          onSyncWebhook={syncWebhook}
          webhookSyncing={webhookSyncing}
          webhookSyncResult={webhookSyncResult}
          webhookSyncError={webhookSyncError}
        />
      </main>
    </div>
  )
}

export default App
