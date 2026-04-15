interface MainDashboardProps {
  onOpenMissionControl: () => void
  onOpenTriggerLab: () => void
}

export function MainDashboard({ onOpenMissionControl, onOpenTriggerLab }: MainDashboardProps) {
  return (
    <div className="landing-shell">
      <section className="landing-hero panel">
        <div className="landing-hero-copy">
          <p className="landing-eyebrow">VoiceForge Control Center</p>
          <h1>Welcome to the Operations Nexus</h1>
          <p className="landing-subtitle">
            Reimagined for high-velocity voice teams: jump into orchestration, rapid outbound testing, and session intelligence without friction.
          </p>

          <div className="landing-actions">
            <button type="button" className="btn primary" onClick={onOpenMissionControl}>
              Enter Mission Control
            </button>
            <button type="button" className="btn ghost" onClick={onOpenTriggerLab}>
              Open Trigger Lab
            </button>
          </div>
        </div>

        <aside className="landing-spotlight">
          <div className="landing-spotlight-card">
            <p>Live flow</p>
            <strong>Mission Control</strong>
            <span>Campaigns, prompts, and browser voice sessions</span>
          </div>
          <div className="landing-spotlight-card">
            <p>Fast testing</p>
            <strong>Trigger Lab</strong>
            <span>Preset numbers and direct call overrides</span>
          </div>
        </aside>
      </section>

      <section className="landing-grid">
        <article className="dashboard-card panel">
          <p className="card-kicker">Core Orchestration</p>
          <h2>Mission Control</h2>
          <p>Path: <code>/mission-control</code></p>
          <p>Compose interactions, launch phone or browser sessions, and watch realtime pipeline telemetry.</p>
          <button type="button" className="btn primary" onClick={onOpenMissionControl}>
            Enter Mission Control
          </button>
        </article>

        <article className="dashboard-card panel">
          <p className="card-kicker">Rapid Outbound Testing</p>
          <h2>Trigger Lab</h2>
          <p>Path: <code>/trigger-lab</code></p>
          <p>Fire direct assistant calls with preset dial targets plus optional first-message and system-prompt tuning.</p>
          <button type="button" className="btn primary" onClick={onOpenTriggerLab}>
            Open Trigger Lab
          </button>
        </article>
      </section>

      <section className="landing-ribbon panel">
        <span>Live command visibility</span>
        <span>Safer rapid experimentation</span>
        <span>Built for operators</span>
      </section>
    </div>
  )
}
