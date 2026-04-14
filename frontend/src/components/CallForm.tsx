import { useState } from 'react'
import type { CallFormValues, InteractionMode } from '../types'

interface CallFormProps {
  interactionMode: InteractionMode
  onInteractionModeChange: (mode: InteractionMode) => void
  disableModeSwitch: boolean
  runningPhone: boolean
  canStartPhone: boolean
  onStartPhone: (values: CallFormValues) => Promise<void>
  onCancelPhone: () => void
  browserConnected: boolean
  browserConnecting: boolean
  browserMuted: boolean
  canStopBrowser: boolean
  canStartBrowser: boolean
  onStartBrowser: (values: CallFormValues) => Promise<void>
  onStopBrowser: () => Promise<void>
  onToggleBrowserMute: () => void
}

const lendingUseCases = [
  'Lead Qualification',
  'Welcome call',
  'Predues / Postdues',
  'Disbursement Readiness Follow-Up',
  'Balance Transfer Campaigns',
  'GST / Bank Statement Follow-Up',
  'Loan Renewal / Top-Up',
  'Cashflow Pre-qualification',
  'Sanction Acceptance Follow-Up',
  'RM Appointment Booking',
  'Case Progress Follow-Up',
  'Immediate Loan Intent Capture',
  'Loan Approval Follow-Up',
  'EMI Reminder',
  'CX (Customer Experience)',
  'Service Call',
]

const insuranceUseCases = [
  'Lead Qualification',
  'Welcome call',
  'Renewal Reminder',
  'Proposal Completion Follow-Up',
  'Premium Reminder',
  'Lapse Revival Campaigns',
  'Quote Follow-Up',
  'Policy Issuance Follow-Up',
  'Claims Intimation Support',
  'Expiry Follow-Up',
  'Cross-Sell Outreach',
  'Claims Triage',
  'CX (Customer Experience)',
  'Service Call',
]

const investmentUseCases = [
  'Lead Qualification',
  'Welcome call',
  'SIP Reminder / SIP Bounce Recovery',
  'SIP Order',
  'KYC & RM Callback',
  'Investor Queries',
  'Redemption Retention',
  'New Investor Onboarding',
  'NFO Campaign Outreach',
  'Portfolio Review Reminder',
  'Event / Webinar Outreach',
  'CX (Customer Experience)',
  'Service Call',
]

const industryMapping = {
  'Personal Loan': lendingUseCases,
  'Home Loan': [...lendingUseCases, 'Auction Prevention Alerts'],
  'Business Loan': lendingUseCases,
  LAP: lendingUseCases,
  'Gold Loan': [...lendingUseCases, 'Auction Prevention Alerts'],
  'Vehicle Loan': [...lendingUseCases, 'Test Drive Coordination'],
  'Consumer Durable Loan': [...lendingUseCases, 'Checkout Financing Assistance'],
  'Life Insurance': insuranceUseCases,
  'Health Insurance': insuranceUseCases,
  'Motor Insurance': [...insuranceUseCases, 'Inspection Coordination'],
  'Home Insurance': [...insuranceUseCases, 'Inspection Coordination'],
  'General Insurance': [...insuranceUseCases, 'Inspection Coordination'],
  'Mutual Funds': investmentUseCases,
  'Wealth Management': investmentUseCases,
  Brokerages: [...investmentUseCases, 'Account Opening Follow-Up', 'First Trade Activation', 'Dormant Account Reactivation'],
  Investor_Queries: ['Investor Queries', 'Service Call', 'KYC & RM Callback', 'CX (Customer Experience)'],
} as const

type IndustryKey = keyof typeof industryMapping
const industryOptions = Object.keys(industryMapping) as IndustryKey[]
const defaultIndustry: IndustryKey = 'Personal Loan'

const initialValues: CallFormValues = {
  industry: defaultIndustry,
  company: 'Acme AI',
  use_case: industryMapping[defaultIndustry][0],
  persona: 'Warm, direct, consultative voice agent who speaks clearly and confidently.',
  guardrails: 'Never claim fake discounts. End immediately if asked to stop. Stay truthful.',
  call_flow: '',
  query_handling: '',
  speaking_speed: '1.0',
  phone_number: '+918435527927',
  agent_name: 'Aisha',
  voice_gender: 'female',
  start_language: 'english',
  call_direction: 'outbound',
  web_search_enabled: true,
  customer_name: 'Customer',
  customer_gender: 'male',
}

export function CallForm({
  interactionMode,
  onInteractionModeChange,
  disableModeSwitch,
  runningPhone,
  canStartPhone,
  onStartPhone,
  onCancelPhone,
  browserConnected,
  browserConnecting,
  browserMuted,
  canStopBrowser,
  canStartBrowser,
  onStartBrowser,
  onStopBrowser,
  onToggleBrowserMute,
}: CallFormProps) {
  const [values, setValues] = useState<CallFormValues>(initialValues)
  const useCaseOptions = industryMapping[values.industry as IndustryKey] ?? []

  const update = (field: keyof CallFormValues, value: string | boolean) => {
    setValues((prev) => ({ ...prev, [field]: value }))
  }

  const updateIndustry = (industry: IndustryKey) => {
    const options = industryMapping[industry]
    setValues((prev) => ({
      ...prev,
      industry,
      use_case: options[0] ?? '',
    }))
  }

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (interactionMode === 'phone') {
      await onStartPhone(values)
      return
    }

    await onStartBrowser(values)
  }

  return (
    <form className="panel form-panel" onSubmit={handleSubmit}>
      <div className="panel-head">
        <h2>Call Composer</h2>
        <p>Define the agent, stream prompt generation, then place the outbound call.</p>
      </div>

      <div className="mode-switch" role="tablist" aria-label="Interaction mode">
        <button
          type="button"
          role="tab"
          aria-selected={interactionMode === 'phone'}
          className={`mode-btn ${interactionMode === 'phone' ? 'active' : ''}`}
          onClick={() => onInteractionModeChange('phone')}
          disabled={disableModeSwitch}
        >
          Phone Call
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={interactionMode === 'browser'}
          className={`mode-btn ${interactionMode === 'browser' ? 'active' : ''}`}
          onClick={() => onInteractionModeChange('browser')}
          disabled={disableModeSwitch}
        >
          Talk In Browser
        </button>
      </div>

      <div className="mode-switch" role="tablist" aria-label="Call direction">
        <button
          type="button"
          role="tab"
          aria-selected={values.call_direction === 'outbound'}
          className={`mode-btn ${values.call_direction === 'outbound' ? 'active' : ''}`}
          onClick={() => update('call_direction', 'outbound')}
        >
          Outbound
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={values.call_direction === 'inbound'}
          className={`mode-btn ${values.call_direction === 'inbound' ? 'active' : ''}`}
          onClick={() => update('call_direction', 'inbound')}
        >
          Inbound
        </button>
      </div>

      <div className="mode-switch" role="tablist" aria-label="Web search tools">
        <button
          type="button"
          role="tab"
          aria-selected={values.web_search_enabled}
          className={`mode-btn ${values.web_search_enabled ? 'active' : ''}`}
          onClick={() => update('web_search_enabled', true)}
        >
          Web Search On
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={!values.web_search_enabled}
          className={`mode-btn ${!values.web_search_enabled ? 'active' : ''}`}
          onClick={() => update('web_search_enabled', false)}
        >
          Web Search Off
        </button>
      </div>

      <div className="grid two-col">
        <label>
          <span>Industry</span>
          <select
            required
            value={values.industry}
            onChange={(e) => updateIndustry(e.target.value as IndustryKey)}
          >
            {industryOptions.map((industry) => (
              <option key={industry} value={industry}>
                {industry}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Company</span>
          <input
            required
            minLength={2}
            maxLength={100}
            value={values.company}
            onChange={(e) => update('company', e.target.value)}
            placeholder="Your company name"
          />
        </label>

        <label>
          <span>Use Case</span>
          <select
            required
            value={values.use_case}
            onChange={(e) => update('use_case', e.target.value)}
          >
            {useCaseOptions.map((useCase) => (
              <option key={useCase} value={useCase}>
                {useCase}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Phone Number (E.164, phone mode)</span>
          <input
            required={interactionMode === 'phone'}
            pattern="^\+[1-9]\d{7,14}$"
            value={values.phone_number}
            onChange={(e) => update('phone_number', e.target.value)}
            placeholder="+918435527927"
          />
        </label>

        <label>
          <span>Agent Name</span>
          <input
            required
            minLength={1}
            maxLength={50}
            value={values.agent_name}
            onChange={(e) => update('agent_name', e.target.value)}
            placeholder="Aisha"
          />
        </label>

        <label>
          <span>Voice Gender</span>
          <select
            required
            value={values.voice_gender}
            onChange={(e) => update('voice_gender', e.target.value as 'male' | 'female')}
          >
            <option value="female">Female</option>
            <option value="male">Male</option>
          </select>
        </label>

        <label>
          <span>Start Language</span>
          <select
            required
            value={values.start_language}
            onChange={(e) => update('start_language', e.target.value as 'english' | 'hindi')}
          >
            <option value="english">English</option>
            <option value="hindi">Hindi</option>
          </select>
        </label>

        <label>
          <span>Speaking Speed</span>
          <select
            required
            value={values.speaking_speed}
            onChange={(e) => update('speaking_speed', e.target.value)}
          >
            <option value="0.7">0.7 — Slow</option>
            <option value="0.85">0.85 — Relaxed</option>
            <option value="1.0">1.0 — Normal</option>
            <option value="1.15">1.15 — Fast</option>
            <option value="1.3">1.3 — Brisk</option>
          </select>
        </label>

        <label>
          <span>Customer Name</span>
          <input
            required
            minLength={1}
            maxLength={50}
            value={values.customer_name}
            onChange={(e) => update('customer_name', e.target.value)}
            placeholder="Priya"
          />
        </label>

        <label>
          <span>Customer Gender</span>
          <select
            required
            value={values.customer_gender}
            onChange={(e) => update('customer_gender', e.target.value as 'male' | 'female')}
          >
            <option value="male">Male</option>
            <option value="female">Female</option>
          </select>
        </label>
      </div>

      <div className="grid">
        <label>
          <span>Persona</span>
          <textarea
            required
            minLength={5}
            maxLength={300}
            rows={4}
            value={values.persona}
            onChange={(e) => update('persona', e.target.value)}
            placeholder="Tone, style, and personality"
          />
        </label>

        <label>
          <span>Guardrails</span>
          <textarea
            required
            minLength={5}
            rows={10}
            value={values.guardrails}
            onChange={(e) => update('guardrails', e.target.value)}
            placeholder="Hard constraints the agent must follow"
          />
        </label>

        <label>
          <span>Call Flow / Instructions <em style={{ fontWeight: 400, opacity: 0.6, fontSize: '0.85em' }}>(Optional)</em></span>
          <textarea
            rows={10}
            value={values.call_flow}
            onChange={(e) => update('call_flow', e.target.value)}
            placeholder="Paste your full call script here. Stage 1: Greeting → Stage 2: Discovery → Stage 3: Value Prop → Stage 4: Close. If left empty, the AI will auto-generate a script."
          />
        </label>

        <label>
          <span>Query Handling <em style={{ fontWeight: 400, opacity: 0.6, fontSize: '0.85em' }}>(Optional)</em></span>
          <textarea
            rows={6}
            value={values.query_handling}
            onChange={(e) => update('query_handling', e.target.value)}
            placeholder={`Rules for specific customer queries. E.g:\n- If customer asks about interest rate → say 'Our rates start from 10.5% p.a.'\n- If customer asks about eligibility → ask for monthly income first`}
          />
        </label>
      </div>

      <div className="actions">
        {interactionMode === 'phone' ? (
          <>
            <button type="submit" className="btn primary" disabled={!canStartPhone}>
              {runningPhone ? 'Running…' : 'Generate + Dial'}
            </button>
            <button type="button" className="btn ghost" onClick={onCancelPhone} disabled={!runningPhone}>
              Cancel
            </button>
          </>
        ) : (
          <>
            <button type="submit" className="btn primary" disabled={!canStartBrowser}>
              {browserConnecting ? 'Connecting…' : browserConnected ? 'Connected' : 'Start Browser Talk'}
            </button>
            <button type="button" className="btn ghost" onClick={onStopBrowser} disabled={!canStopBrowser}>
              Stop
            </button>
            <button type="button" className="btn ghost" onClick={onToggleBrowserMute} disabled={!browserConnected}>
              {browserMuted ? 'Unmute Mic' : 'Mute Mic'}
            </button>
          </>
        )}
      </div>
    </form>
  )
}
