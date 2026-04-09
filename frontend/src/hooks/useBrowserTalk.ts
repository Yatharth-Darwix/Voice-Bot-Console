import { useCallback, useRef, useState } from 'react'
import VapiModule from '@vapi-ai/web'
import type { BrowserTalkMessage, CallFormValues, EventKind, TimelineEvent } from '../types'

interface PrepareBrowserBotResponse {
  session_id: string
  system_prompt: string
  first_message: string
  assistant_id: string
  assistant_overrides: Record<string, unknown>
}

interface BrowserTalkState {
  connected: boolean
  connecting: boolean
  speaking: boolean
  muted: boolean
  sessionId: string | null
  callId: string | null
  error: string | null
  messages: BrowserTalkMessage[]
  timeline: TimelineEvent[]
}

interface VapiClient {
  on: (event: string, handler: (payload?: unknown) => void) => void
  stop: () => unknown
  start: (assistantId: string, assistantOverrides?: Record<string, unknown>) => unknown
  setMuted: (muted: boolean) => unknown
}

type VapiConstructor = new (publicKey: string) => VapiClient

interface ParsedBrowserMessage {
  kind: BrowserTalkMessage['kind']
  text: string
  eventType: string
  persist: boolean
  metadata?: Record<string, unknown>
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''
const VAPI_PUBLIC_KEY = import.meta.env.VITE_VAPI_PUBLIC_KEY ?? ''

function resolveVapiConstructor(): VapiConstructor {
  const direct = VapiModule as unknown
  if (typeof direct === 'function') {
    return direct as VapiConstructor
  }

  if (typeof direct === 'object' && direct !== null && 'default' in direct) {
    const first = (direct as { default?: unknown }).default
    if (typeof first === 'function') {
      return first as VapiConstructor
    }
    if (typeof first === 'object' && first !== null && 'default' in first) {
      const second = (first as { default?: unknown }).default
      if (typeof second === 'function') {
        return second as VapiConstructor
      }
    }
  }

  throw new Error('Failed to load @vapi-ai/web constructor from module export')
}

function buildApiUrl(path: string): string {
  if (!API_BASE_URL) {
    return path
  }

  return `${API_BASE_URL.replace(/\/$/, '')}${path}`
}

const initialState: BrowserTalkState = {
  connected: false,
  connecting: false,
  speaking: false,
  muted: false,
  sessionId: null,
  callId: null,
  error: null,
  messages: [],
  timeline: [],
}

export function useBrowserTalk() {
  const [state, setState] = useState<BrowserTalkState>(initialState)
  const vapiRef = useRef<VapiClient | null>(null)
  const nextTimelineIdRef = useRef(1)
  const nextMessageIdRef = useRef(1)
  const sessionIdRef = useRef<string | null>(null)

  const addTimeline = useCallback((kind: EventKind, message: string) => {
    setState((prev) => ({
      ...prev,
      timeline: [
        ...prev.timeline,
        {
          id: nextTimelineIdRef.current++,
          at: new Date().toLocaleTimeString(),
          kind,
          message,
        },
      ],
    }))
  }, [])

  const extractErrorMessage = (value: unknown): string => {
    if (value instanceof Error) {
      return value.message
    }

    if (typeof value === 'string') {
      return value
    }

    if (typeof value === 'object' && value !== null && 'message' in value) {
      const msg = (value as { message?: unknown }).message
      return typeof msg === 'string' ? msg : 'Unknown browser talk error'
    }

    return 'Unknown browser talk error'
  }

  const persistSessionEvent = useCallback(
    async (event: { role: string; text: string; eventType: string; metadata?: Record<string, unknown> }) => {
      if (!sessionIdRef.current || !event.text.trim()) {
        return
      }

      try {
        await fetch(buildApiUrl(`/api/sessions/${sessionIdRef.current}/events`), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            role: event.role,
            text: event.text,
            source: 'frontend_browser_sdk',
            event_type: event.eventType,
            metadata: event.metadata,
          }),
        })
      } catch {
        // Keep browser UX responsive even if event logging fails.
      }
    },
    [],
  )

  const addMessage = useCallback(
    (
      kind: BrowserTalkMessage['kind'],
      text: string,
      options?: {
        eventType?: string
        persist?: boolean
        metadata?: Record<string, unknown>
      },
    ) => {
      const messageText = text.trim()
      if (!messageText) {
        return
      }

      setState((prev) => ({
        ...prev,
        messages: [
          ...prev.messages,
          {
            id: nextMessageIdRef.current++,
            at: new Date().toLocaleTimeString(),
            kind,
            text: messageText,
          },
        ],
      }))

      const shouldPersist = options?.persist ?? (kind === 'assistant' || kind === 'user')
      if (!shouldPersist) {
        return
      }

      const role = kind === 'assistant' ? 'assistant' : kind === 'user' ? 'user' : 'event'
      void persistSessionEvent({
        role,
        text: messageText,
        eventType: options?.eventType ?? 'message',
        metadata: options?.metadata,
      })
    },
    [persistSessionEvent],
  )

  const parseMessage = useCallback((message: unknown): ParsedBrowserMessage | null => {
    if (typeof message === 'string') {
      const trimmed = message.trim()
      if (!trimmed) {
        return null
      }

      if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
        try {
          const decoded = JSON.parse(trimmed)
          const parsedDecoded = parseMessage(decoded)
          if (parsedDecoded) {
            return parsedDecoded
          }
        } catch {
          // Keep raw message fallback when SDK emits plain text.
        }
      }

      return { kind: 'event', text: trimmed, eventType: 'sdk-string', persist: false }
    }

    if (typeof message !== 'object' || message === null) {
      return { kind: 'event', text: 'Received non-standard message payload', eventType: 'unknown', persist: false }
    }

    const typed = message as {
      type?: string
      status?: string
      role?: string
      transcriptType?: string
      transcript?: string
      message?: { content?: string }
      output?: unknown
      turnId?: string
    }

    const type = typed.type ?? 'unknown'

    if (type === 'model-output') {
      return null
    }

    if (type === 'speech-update') {
      return null
    }

    if (type === 'status-update') {
      const status = typeof typed.status === 'string' ? typed.status : 'unknown'
      return {
        kind: 'event',
        text: `Status: ${status}`,
        eventType: `status-update:${status}`,
        persist: true,
      }
    }

    if ((type === 'transcript' || type.startsWith('transcript')) && typeof typed.transcript === 'string') {
      if (typed.transcriptType && typed.transcriptType !== 'final') {
        return null
      }

      if (typed.role === 'assistant') {
        return {
          kind: 'assistant',
          text: typed.transcript,
          eventType: 'transcript',
          persist: true,
          metadata: message as Record<string, unknown>,
        }
      }
      if (typed.role === 'user') {
        return {
          kind: 'user',
          text: typed.transcript,
          eventType: 'transcript',
          persist: true,
          metadata: message as Record<string, unknown>,
        }
      }
      return {
        kind: 'event',
        text: typed.transcript,
        eventType: 'transcript',
        persist: true,
        metadata: message as Record<string, unknown>,
      }
    }

    if (typed.message?.content) {
      if (typed.role === 'assistant') {
        return {
          kind: 'assistant',
          text: typed.message.content,
          eventType: type,
          persist: true,
          metadata: message as Record<string, unknown>,
        }
      }
      if (typed.role === 'user') {
        return {
          kind: 'user',
          text: typed.message.content,
          eventType: type,
          persist: true,
          metadata: message as Record<string, unknown>,
        }
      }
      return {
        kind: 'event',
        text: typed.message.content,
        eventType: type,
        persist: true,
        metadata: message as Record<string, unknown>,
      }
    }

    return {
      kind: 'event',
      text: `Event: ${type}`,
      eventType: type,
      persist: false,
    }
  }, [])

  const stop = useCallback(async () => {
    const vapi = vapiRef.current

    if (vapi) {
      try {
        await Promise.resolve(vapi.stop())
      } catch {
        // Keep UI reset behavior even if stop throws.
      }
    }

    vapiRef.current = null
    sessionIdRef.current = null
    setState(initialState)
  }, [])

  const bindCallToSession = useCallback(
    async (sessionId: string, callId: string) => {
      try {
        await fetch(buildApiUrl(`/api/sessions/${sessionId}/bind-call`), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ call_id: callId }),
        })
        setState((prev) => ({ ...prev, callId }))
        addTimeline('success', `Session linked with call (${callId})`)
      } catch (error) {
        const message = extractErrorMessage(error)
        addTimeline('error', `Failed to bind call to session: ${message}`)
      }
    },
    [addTimeline],
  )

  const tryBindCallFromPayload = useCallback(
    async (payload: unknown) => {
      if (!sessionIdRef.current || typeof payload !== 'object' || payload === null) {
        return
      }

      const typed = payload as { callId?: unknown; call?: { id?: unknown }; type?: unknown; id?: unknown }
      let maybeCallId: unknown = typed.call?.id ?? typed.callId ?? null

      if (!maybeCallId && (typed.type === 'call-start' || typed.type === 'call-started')) {
        maybeCallId = typed.id
      }

      if (typeof maybeCallId === 'string' && maybeCallId.length > 1) {
        await bindCallToSession(sessionIdRef.current, maybeCallId)
      }
    },
    [bindCallToSession],
  )

  const toggleMute = useCallback(() => {
    const vapi = vapiRef.current
    if (!vapi || !state.connected) {
      return
    }

    const nextMuted = !state.muted
    vapi.setMuted(nextMuted)
    setState((prev) => ({ ...prev, muted: nextMuted }))
    addTimeline('info', nextMuted ? 'Microphone muted' : 'Microphone unmuted')
  }, [addTimeline, state.connected, state.muted])

  const start = useCallback(
    async (values: CallFormValues) => {
      if (state.connecting || state.connected) {
        return
      }

      if (!VAPI_PUBLIC_KEY) {
        const message = 'Missing VITE_VAPI_PUBLIC_KEY in frontend env'
        setState((prev) => ({ ...prev, error: message }))
        addTimeline('error', message)
        return
      }

      if (vapiRef.current) {
        await stop()
      }

      nextTimelineIdRef.current = 1
      nextMessageIdRef.current = 1

      setState({
        connected: false,
        connecting: true,
        speaking: false,
        muted: false,
        sessionId: null,
        callId: null,
        error: null,
        messages: [],
        timeline: [],
      })

      addTimeline('info', 'Preparing browser bot configuration')

      const requestBody = {
        industry: values.industry,
        company: values.company,
        use_case: values.use_case,
        persona: values.persona,
        guardrails: values.guardrails,
        agent_name: values.agent_name,
        voice_gender: values.voice_gender,
      }

      try {
        const response = await fetch(buildApiUrl('/api/prepare-browser-bot'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(requestBody),
        })

        if (!response.ok) {
          const detail = await response.text()
          throw new Error(`API ${response.status}: ${detail}`)
        }

        const prepared = (await response.json()) as PrepareBrowserBotResponse
        addTimeline('success', 'Browser bot prepared')
        addTimeline('info', `Session created (${prepared.session_id})`)
        addMessage('event', 'Connecting browser voice session...', { persist: false })
        sessionIdRef.current = prepared.session_id
        setState((prev) => ({ ...prev, sessionId: prepared.session_id }))

        const Vapi = resolveVapiConstructor()
        const vapi = new Vapi(VAPI_PUBLIC_KEY)
        vapiRef.current = vapi

        vapi.on('call-start', (payload?: unknown) => {
          void tryBindCallFromPayload(payload)
          setState((prev) => ({ ...prev, connected: true, connecting: false }))
          addTimeline('success', 'Browser session connected')
          addMessage('event', 'Call started. Speak to the assistant.', { eventType: 'call-start', persist: true })
        })

        vapi.on('call-end', () => {
          setState((prev) => ({ ...prev, connected: false, connecting: false, speaking: false, muted: false }))
          addTimeline('info', 'Browser session ended')
          addMessage('event', 'Call ended.', { eventType: 'call-end', persist: true })
          vapiRef.current = null
        })

        vapi.on('speech-start', () => {
          setState((prev) => ({ ...prev, speaking: true }))
        })

        vapi.on('speech-end', () => {
          setState((prev) => ({ ...prev, speaking: false }))
        })

        vapi.on('message', (message: unknown) => {
          void tryBindCallFromPayload(message)
          const parsed = parseMessage(message)
          if (!parsed) {
            return
          }
          addMessage(parsed.kind, parsed.text, {
            eventType: parsed.eventType,
            persist: parsed.persist,
            metadata: parsed.metadata,
          })
        })

        vapi.on('error', (error: unknown) => {
          const message = extractErrorMessage(error)
          setState((prev) => ({ ...prev, error: message, connecting: false }))
          addTimeline('error', message)
          addMessage('error', message, { eventType: 'error', persist: true })
        })

        const startResult = await Promise.resolve(vapi.start(prepared.assistant_id, prepared.assistant_overrides))
        await tryBindCallFromPayload(startResult)
      } catch (error) {
        const message = extractErrorMessage(error)
        setState((prev) => ({
          ...prev,
          connected: false,
          connecting: false,
          speaking: false,
          muted: false,
          sessionId: sessionIdRef.current,
          error: message,
        }))
        addTimeline('error', message)
        addMessage('error', message, { eventType: 'error', persist: true })

        if (vapiRef.current) {
          try {
            await Promise.resolve(vapiRef.current.stop())
          } catch {
            // no-op
          }
          vapiRef.current = null
        }
      }
    },
    [addMessage, addTimeline, parseMessage, state.connected, state.connecting, stop, tryBindCallFromPayload],
  )

  return {
    publicKeyConfigured: Boolean(VAPI_PUBLIC_KEY),
    ...state,
    start,
    stop,
    toggleMute,
  }
}
