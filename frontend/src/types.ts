export interface CallFormValues {
  industry: string
  company: string
  use_case: string
  persona: string
  guardrails: string
  call_flow: string
  query_handling: string
  speaking_speed: string
  phone_number: string
  agent_name: string
  voice_gender: 'male' | 'female'
  start_language: 'english' | 'hindi'
  call_direction: 'outbound' | 'inbound'
  web_search_enabled: boolean
  customer_name: string
  customer_gender: 'male' | 'female'
}

export type InteractionMode = 'phone' | 'browser'

export type EventKind = 'info' | 'success' | 'error'

export interface TimelineEvent {
  id: number
  at: string
  kind: EventKind
  message: string
}

export interface BrowserTalkMessage {
  id: number
  at: string
  kind: 'event' | 'assistant' | 'user' | 'error'
  text: string
}

export interface SessionSummary {
  session_id: string
  mode: 'phone' | 'browser' | string
  status: string
  call_id: string | null
  industry: string
  company: string
  use_case: string
  created_at: string
  updated_at: string
}

export interface SessionMessage {
  at: string
  role: string
  text: string
  source: string
  event_type: string
  metadata?: Record<string, unknown> | null
}

export interface SessionDetail extends SessionSummary {
  persona: string
  guardrails: string
  system_prompt: string
  first_message: string
  messages: SessionMessage[]
  vapi_fetch_error: string | null
}
