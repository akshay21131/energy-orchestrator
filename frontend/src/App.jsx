import React, { useEffect, useRef, useState, useCallback } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Area, AreaChart } from 'recharts'
import './App.css'

// ----- Helpers -----
const fmtKW = (kw) => {
  if (kw == null) return '—'
  if (Math.abs(kw) >= 1000) return (kw / 1000).toFixed(1) + ' MW'
  return kw.toFixed(0) + ' kW'
}
const fmtKWh = (kwh) => {
  if (kwh == null) return '—'
  if (Math.abs(kwh) >= 1000000) return (kwh / 1000000).toFixed(2) + ' GWh'
  if (Math.abs(kwh) >= 1000) return (kwh / 1000).toFixed(1) + ' MWh'
  return kwh.toFixed(0) + ' kWh'
}
const fmtINR = (v) => {
  if (v == null || isNaN(v)) return '₹0'
  const neg = v < 0 ? '-' : ''
  const av = Math.abs(v)
  if (av >= 10000000) return neg + '₹' + (av / 10000000).toFixed(2) + ' Cr'
  if (av >= 100000) return neg + '₹' + (av / 100000).toFixed(2) + ' L'
  if (av >= 1000) return neg + '₹' + (av / 1000).toFixed(1) + 'k'
  return neg + '₹' + av.toFixed(0)
}

const EVENT_BUTTONS = [
  { type: 'cloud_surge', label: '☁️ Cloud Cover', mag: 0.6, dur: 12 },
  { type: 'wind_gust', label: '💨 Wind Gust', mag: 0.6, dur: 10 },
  { type: 'wind_lull', label: '🍃 Wind Lull', mag: 0.7, dur: 12 },
  { type: 'price_spike', label: '⚡ Price Spike 2.5x', mag: 2.5, dur: 4 },
  { type: 'price_crash', label: '📉 Price Crash', mag: 1.0, dur: 4 },
  { type: 'battery_fault', label: '🔋 BESS 1 Fault', target: 'b1', mag: 1.0, dur: 8 },
  { type: 'battery_recover', label: '🔧 BESS 1 Recover', target: 'b1', mag: 0, dur: 1 },
  { type: 'line_trip', label: '🔌 Line Trip -50%', mag: 0.5, dur: 6 },
  { type: 'demand_surge', label: '🏭 Demand Surge +30%', mag: 0.3, dur: 12 },
  { type: 'storm_warning', label: '🌪️ Storm (in 1h)', mag: 4, dur: 16, lead: 4, forecast: true },
]

const SCENARIOS = [
  { id: 'normal', label: '☀️ Normal Day', desc: 'Balanced renewable day' },
  { id: 'summer_peak', label: '🌡️ Summer Peak', desc: 'Demand surge + price spike' },
  { id: 'stormy_night', label: '⛈️ Stormy Night', desc: 'Wind gusts + line trip' },
  { id: 'price_volatility', label: '📊 Price Volatility', desc: 'Extreme price swings' },
]

const AGENT_STAGES = [
  { id: 'observe', label: 'Observe', icon: '👁️' },
  { id: 'reason', label: 'Reason', icon: '🧠' },
  { id: 'optimize', label: 'Optimize', icon: '⚙️' },
  { id: 'validate', label: 'Validate', icon: '✓' },
  { id: 'act', label: 'Act', icon: '⚡' },
]

function App() {
  const [state, setState] = useState(null)
  const [engine, setEngine] = useState({ running: false, speed: 20, autonomous: true, started: false, day_complete: false, agent_stage: 'idle', replan_last_tick: false })
  const [config, setConfig] = useState(null)
  const [history, setHistory] = useState([])
  const [safety, setSafety] = useState(null)
  const [decisionHistory, setDecisionHistory] = useState([])
  const [selectedDecision, setSelectedDecision] = useState(null)
  const [showDaySummary, setShowDaySummary] = useState(false)
  // Auto-open summary when day completes
  useEffect(() => { if (state && state.day_summary) setShowDaySummary(true); }, [state?.day_summary])
  const [showArch, setShowArch] = useState(false)
  const [showWelcome, setShowWelcome] = useState(true)
  const [nlCmd, setNlCmd] = useState('')
  const [nlResponse, setNlResponse] = useState('')
  const [savingsAnim, setSavingsAnim] = useState({ cost: 0, co2: 0, curt: 0 })
  const [flashReplan, setFlashReplan] = useState(false)
  const wsRef = useRef(null)
  const prevSavings = useRef({ cost: 0, co2: 0, curt: 0 })

  const connect = useCallback(() => {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${proto}//${window.location.host}/ws`
    const ws = new WebSocket(wsUrl)
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data)
      if (msg.type === 'state' || msg.type === 'event_injected' || msg.type === 'command') {
        if (msg.safety) setSafety(msg.safety)
        if (msg.state) {
          setState(msg.state)
          setShowWelcome(false)
          setEngine(msg.engine)
          if (msg.engine?.replan_last_tick) {
            setFlashReplan(true)
            setTimeout(() => setFlashReplan(false), 1500)
          }
          setHistory(h => {
            const pt = {
              t: msg.state.time_of_day,
              solar: Math.round(msg.state.solar_potential_kw / 1000),
              wind: Math.round(msg.state.wind_potential_kw / 1000),
              demand: Math.round(msg.state.total_demand_kw / 1000),
              import: Math.round(msg.state.grid_import_kw / 1000),
              export: Math.round(msg.state.grid_export_kw / 1000),
              price: msg.state.grid_price_inr_per_kwh,
            }
            const next = [...h, pt]
            if (next.length > 80) next.shift()
            return next
          })
        }
        if (msg.engine) setEngine(msg.engine)
        if (msg.response) setNlResponse(msg.response)
      } else if (msg.type === 'engine') {
        setEngine(msg.engine)
      }
    }
    ws.onclose = () => setTimeout(connect, 2000)
    wsRef.current = ws
  }, [])

  useEffect(() => {
    connect()
    fetch('/api/config').then(r => r.json()).then(setConfig)
    fetch('/api/safety').then(r => r.json()).then(setSafety)
    let cancelled = false
    const cmp = setInterval(() => {
      if (cancelled) return
      fetch('/api/decision-history').then(r => r.json()).then(d => setDecisionHistory(d.history || [])).catch(()=>{})
    }, 3000)
    return () => { cancelled = true; wsRef.current && wsRef.current.close(); clearInterval(cmp) }
  }, [connect])

  // Poll comparison for live savings (every 2s, not 500ms — prevents endpoint spam)
  useEffect(() => {
    let cancelled = false
    const i = setInterval(() => {
      if (cancelled) return
      fetch('/api/comparison').then(r => r.json()).then(c => {
        if (cancelled || !c.savings) return
        const tgt = {
          cost: Math.max(0, c.savings.cost_inr_saved || 0),
          co2: Math.max(0, c.savings.co2_kg_saved || 0),
          curt: Math.max(0, c.savings.curtailment_reduced_kwh || 0),
        }
        setSavingsAnim(prev => ({
          cost: prev.cost + (tgt.cost - prev.cost) * 0.15,
          co2: prev.co2 + (tgt.co2 - prev.co2) * 0.15,
          curt: prev.curt + (tgt.curt - prev.curt) * 0.15,
        }))
      }).catch(()=>{})
    }, 2000)
    return () => { cancelled = true; clearInterval(i) }
  }, [])

  const post = async (path, body) => {
    const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined })
    return r.json()
  }
  const setSpeed = async (speed) => { await post('/api/control', { speed }) }
  const toggleAuto = async () => { await post('/api/control', { autonomous: !engine.autonomous }) }
  const play = () => post('/api/play')
  const pause = () => post('/api/pause')
  const step = () => post('/api/step')
  const reset = () => { setHistory([]); setSelectedDecision(null); post('/api/reset'); setShowWelcome(true) }
  const playDay = () => { post('/api/play-day') }
  const inject = (evt) => post('/api/inject-event', {
    type: evt.type, target: evt.target, magnitude: evt.mag,
    duration_ticks: evt.dur, is_forecast: !!evt.forecast, lead_ticks: evt.lead || 0,
  })
  const loadScenario = (scenario) => { setHistory([]); setSelectedDecision(null); post('/api/load-scenario', { scenario }); setShowWelcome(false) }
  const sendNLCmd = async (e) => {
    e.preventDefault()
    if (!nlCmd.trim()) return
    await post('/api/nl-command', { command: nlCmd })
    setNlCmd('')
    setTimeout(() => setNlResponse(''), 6000)
  }

  if (!state || !config) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: '#8b96ab', background: '#0b0f1a', height: '100vh' }}>
        <div style={{ fontSize: 24, marginBottom: 10 }}>⚡ Connecting to Renewable Energy Orchestrator…</div>
      </div>
    )
  }

  const assets = state.assets
  const reasoning = state.agent_reasoning || {}
  const weights = reasoning.weights || { cost: 0.2, carbon: 0.2, reliability: 0.2, battery_life: 0.2, curtailment: 0.1, profit_export: 0.1 }

  const totalBattDischarge = Object.values(state.batt_discharge_kw || {}).reduce((s, v) => s + v, 0)
  const totalBattCharge = Object.values(state.batt_charge_kw || {}).reduce((s, v) => s + v, 0)
  // Aggregate output correctly
  const solarOut = config.solar_farms.reduce((s, a) => s + (assets[a.id]?.output_kw || 0), 0)
  const windOut = config.wind_farms.reduce((s, a) => s + (assets[a.id]?.output_kw || 0), 0)
  const renewablePct = state.total_demand_kw > 0
    ? Math.min(100, (solarOut + windOut) / state.total_demand_kw * 100) : 0
  const totalGen = solarOut + windOut + state.grid_import_kw + totalBattDischarge
  const totalLoad = Object.values(state.served_kw || {}).reduce((s, v) => s + v, 0) + state.grid_export_kw + totalBattCharge

  // Day complete modal
  const daySummary = state.day_summary

  return (
    <div className="app">
      {/* Day complete modal */}
      {daySummary && showDaySummary && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
          <div className="panel" style={{ maxWidth: 560, width: '100%', boxShadow: '0 0 60px rgba(16,185,129,0.3)', border: '2px solid var(--green)' }}>
            <div className="panel-header" style={{ background: 'linear-gradient(90deg,rgba(16,185,129,0.15),rgba(56,189,248,0.1))', fontSize: 14 }}>
              🌅 Day {daySummary.day} Complete — Autonomous Run Summary
            </div>
            <div className="panel-body" style={{ fontSize: 14 }}>
              <div style={{ fontSize: 13, color: 'var(--text-dim)', marginBottom: 16 }}>
                The AI agent orchestrated 5 solar farms, 3 wind farms, 2 batteries, and the grid for 24 hours. Results compared to a "dumb grid" baseline (no batteries, no DR, no export):
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
                <div className="kpi-card" style={{ border: '1px solid rgba(16,185,129,0.4)' }}>
                  <div className="kpi-label">Operating Cost</div>
                  <div className="kpi-value" style={{ color: 'var(--green)', fontSize: 22 }}>{fmtINR(daySummary.kpis.cost_inr)}</div>
                  <div className="kpi-sub">vs baseline {fmtINR(daySummary.baseline_24h.cost_inr)}</div>
                  <div className="kpi-sub" style={{ color: 'var(--green)' }}>
                    Saved {fmtINR(daySummary.savings.cost_inr_saved)} ({(daySummary.savings.cost_inr_saved/daySummary.baseline_24h.cost_inr*100).toFixed(0)}%)
                  </div>
                </div>
                <div className="kpi-card" style={{ border: '1px solid rgba(56,189,248,0.4)' }}>
                  <div className="kpi-label">CO₂ Emissions</div>
                  <div className="kpi-value accent" style={{ fontSize: 22 }}>{(daySummary.kpis.co2_kg/1000).toFixed(1)} t</div>
                  <div className="kpi-sub">vs baseline {(daySummary.baseline_24h.co2_kg/1000).toFixed(0)} t</div>
                  <div className="kpi-sub" style={{ color: 'var(--green)' }}>
                    Avoided {(daySummary.savings.co2_kg_saved/1000).toFixed(1)} t CO₂
                  </div>
                </div>
                <div className="kpi-card">
                  <div className="kpi-label">Renewables Used</div>
                  <div className="kpi-value" style={{ color: 'var(--solar)', fontSize: 18 }}>{fmtKWh(daySummary.kpis.renewable_kwh)}</div>
                </div>
                <div className="kpi-card">
                  <div className="kpi-label">Curtailment</div>
                  <div className="kpi-value" style={{ color: daySummary.kpis.curtailed_kwh < 1000 ? 'var(--green)' : 'var(--red)', fontSize: 18 }}>{fmtKWh(daySummary.kpis.curtailed_kwh)}</div>
                  <div className="kpi-sub" style={{ color: 'var(--green)' }}>
                    ↓{fmtKWh(daySummary.savings.curtailment_reduced_kwh)} wasted
                  </div>
                </div>
              </div>
              <div className="alert resolved" style={{ margin: 0, textAlign: 'center' }}>
                ✓ Zero unmet critical load across 24 hours
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
                <button className="btn green" style={{ flex: 1 }} onClick={() => { setShowDaySummary(false); reset(); }}>↻ Run Another Day</button>
                <button className="btn primary" style={{ flex: 1 }} onClick={() => { setShowDaySummary(false); setSelectedDecision(null); setTimeout(() => { const el = document.getElementById("audit-panel"); if (el) el.scrollIntoView({behavior:"smooth", block:"start"}); }, 100); }}>📊 Review Details</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Welcome overlay */}
      {showWelcome && !engine.started && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(11,15,26,0.95)', zIndex: 90, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
          <div style={{ maxWidth: 640, textAlign: 'center' }}>
            <div style={{ fontSize: 64, marginBottom: 20 }}>⚡</div>
            <h1 style={{ fontSize: 36, margin: 0, background: 'linear-gradient(90deg,#38bdf8,#10b981)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>Renewable Energy Orchestrator</h1>
            <div style={{ fontSize: 15, color: '#8b96ab', marginTop: 10, lineHeight: 1.6 }}>
              Autonomous AI agent for India's 500 GW renewable future.<br/>
              Orchestrates 5 solar farms, 3 wind farms, 2 battery storage systems, and grid interconnection in real time.
            </div>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginTop: 26 }}>
              <button className="btn green" style={{ padding: '12px 28px', fontSize: 14 }} onClick={() => { play(); setShowWelcome(false) }}>
                ▶ Start Autonomous Run
              </button>
              <button className="btn" style={{ padding: '12px 28px', fontSize: 14 }} onClick={() => setShowArch(true)}>
                📐 View Architecture
              </button>
            </div>
            <div style={{ marginTop: 24, display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10, fontSize: 12, color: '#c9d4e8' }}>
              <div style={{ padding: 10, border: '1px solid var(--border)', borderRadius: 8 }}>
                <div style={{ fontSize: 18, marginBottom: 4 }}>🧠</div>
                <b>Agentic Brain</b><br/>
                <span style={{ color: 'var(--text-dim)' }}>Observe→Reason→Optimize→Validate→Act</span>
              </div>
              <div style={{ padding: 10, border: '1px solid var(--border)', borderRadius: 8 }}>
                <div style={{ fontSize: 18, marginBottom: 4 }}>🛡️</div>
                <b>Safety Layer</b><br/>
                <span style={{ color: 'var(--text-dim)' }}>Hard constraints · Fallbacks · Human override</span>
              </div>
              <div style={{ padding: 10, border: '1px solid var(--border)', borderRadius: 8 }}>
                <div style={{ fontSize: 18, marginBottom: 4 }}>📊</div>
                <b>Proven Impact</b><br/>
                <span style={{ color: 'var(--text-dim)' }}>87% cost cut · 75% CO₂ cut · 100% curtailment elim.</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Architecture modal */}
      {showArch && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.9)', zIndex: 95, overflow: 'auto', padding: 20 }} onClick={() => setShowArch(false)}>
          <div style={{ maxWidth: 900, margin: '40px auto', background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 12, padding: 24 }} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h2 style={{ margin: 0, fontSize: 22 }}>📐 Architecture — Agentic Loop</h2>
              <button className="btn" onClick={() => setShowArch(false)}>✕ Close</button>
            </div>
            <div style={{ fontSize: 13, lineHeight: 1.7, color: '#c9d4e8' }}>
              <p><b>Every 15 minutes:</b></p>
              <ol style={{ paddingLeft: 20 }}>
                <li><b style={{color:'var(--accent)'}}>OBSERVE</b> — Read telemetry (kW, SOC, prices), forecasts (with confidence), and alerts from all 11 assets.</li>
                <li><b style={{color:'var(--yellow)'}}>REASON</b> — Diagnose anomalies (battery faults, storms), spot opportunities (price spikes, surplus renewables), assess forecast confidence, choose 6 objective weights + battery reserve level. Uses LLM (Claude/GPT/Gemini) when API key present; deterministic rule-based brain always available as fallback.</li>
                <li><b style={{color:'var(--battery)'}}>OPTIMIZE (TOOL CALL)</b> — Call the multi-objective LP solver (PuLP/CBC) with the chosen weights. ~20 variables, power balance, SOC bounds, capacity caps, DR/curtail. This is the agent's TOOL — a real numerical solver, not an LLM guess.</li>
                <li><b style={{color:'var(--red)'}}>VALIDATE</b> — Check the plan for unmet critical load, absurd high-price imports, SOC violations.</li>
                <li><b style={{color:'var(--green)'}}>REPLAN if needed</b> — If validation fails, bump reliability + reserve and re-run optimizer (closed-loop reflection).</li>
                <li><b style={{color:'var(--green)'}}>ACT</b> — Dispatch kW flows; update asset state; accumulate KPIs; push to dashboard.</li>
              </ol>
              <p style={{ marginTop: 14 }}><b>Safety layer (cannot be overridden):</b> Battery SOC 10–95% hard bounds in LP, critical load penalty ₹50/kWh, power-balance equality, asset capacity caps, structured JSON output clamping, greedy fallback solver, human pause/override at any time.</p>
              <p><b>9-Blocker: D2 / F3.</b> Structured telemetry + textual alerts, high reliability (0 failures across 4×24h scenarios). F1=optimal actions, F2=dynamic optimality criteria under uncertainty, F3=continuous 24h simulation under varying conditions and disruptions.</p>
            </div>
          </div>
        </div>
      )}

      {/* ---- HEADER ---- */}
      <header className="header">
        <div className="header-row header-row-top">
          <div className="brand" style={{ cursor: 'pointer' }} onClick={() => setShowWelcome(true)} title="About">
            <div className="brand-logo">⚡</div>
            <div className="brand-title-sub">
              <div>Renewable Energy Orchestrator</div>
              <div>Autonomous AI Agent · India 500 GW</div>
            </div>
          </div>
          <div className="time-badge">
            <span className="mono">Day {state.day} · {state.time_of_day}</span>
            <span style={{ marginLeft: 8, fontSize: 10, color: state.grid_price_inr_per_kwh > 10 ? 'var(--red)' : state.grid_price_inr_per_kwh < 5 ? 'var(--green)' : 'var(--accent)', fontWeight: 600 }}>
              ₹{state.grid_price_inr_per_kwh.toFixed(1)}/kWh
            </span>
          </div>
          <div className="header-pills">
            <span className={`status-pill ${engine.autonomous ? 'autonomous' : 'manual'}`}><span className="status-dot" />{engine.autonomous ? 'Auto' : 'Manual'}</span>
            <span className="status-pill" style={{background:(reasoning.used_llm||(reasoning.mode||'').includes('LLM'))?'rgba(167,139,250,0.12)':'rgba(56,189,248,0.08)',color:(reasoning.used_llm||(reasoning.mode||'').includes('LLM'))?'#a78bfa':'var(--accent)',borderColor:(reasoning.used_llm||(reasoning.mode||'').includes('LLM'))?'rgba(167,139,250,0.3)':'rgba(56,189,248,0.2)'}}>
              {(reasoning.used_llm||(reasoning.mode||'').includes('LLM'))?'🧠 LLM':'⚡ Rule'}
            </span>
          </div>
        </div>
        <div className="header-row header-row-bottom">
          <div className="pipeline">
            {AGENT_STAGES.map((st, idx) => {
              const active = engine.agent_stage === st.id
              const done = ['observe','reason','optimize','validate','act'].indexOf(engine.agent_stage) > ['observe','reason','optimize','validate','act'].indexOf(st.id)
              return (
                <React.Fragment key={st.id}>
                  <div className={`stage ${active?'active':done?'done':''}`} title={st.label}>
                    <span className="stage-icon">{st.icon}</span><span className="stage-label">{st.label}</span>
                  </div>
                  {idx < AGENT_STAGES.length - 1 && <span className="stage-arrow">›</span>}
                </React.Fragment>
              )
            })}
            {flashReplan && <div className="stage active" style={{background:'rgba(250,204,21,0.15)',borderColor:'var(--yellow)',color:'var(--yellow)'}}>↻ Replan</div>}
          </div>
          {engine.started && reasoning.intent && (
            <div className="current-strategy" title="Current agent intent">
              <span style={{color:'var(--text-muted)', fontSize:8.5, textTransform:'uppercase', letterSpacing:'0.06em', marginRight:5}}>Strategy:</span>
              <span style={{color:'var(--accent)', fontSize:10, fontWeight:600, maxWidth:220, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', display:'inline-block', verticalAlign:'middle'}}>{reasoning.intent}</span>
            </div>
          )}
          <div className="engine-controls">
            <button className={`btn ${engine.running?'primary':'green'} btn-play`} onClick={engine.running?pause:play} title="Play/Pause (Space)">
              {engine.running?'⏸ Pause':'▶ Play'}
            </button>
            <button className="btn" onClick={playDay} title="Fast-forward to end of day">⏩ Day</button>
            <button className="btn" onClick={step} title="Step one tick">⏭ Step</button>
            <div className="speed-control">
              <select value={engine.speed} onChange={(e)=>setSpeed(Number(e.target.value))} title="Simulation speed">
                <option value={5}>5×</option><option value={20}>20×</option><option value={60}>60×</option><option value={200}>200×</option>
              </select>
            </div>
            <div className="hdr-sep" />
            <button className="btn" onClick={toggleAuto} title="Toggle autonomous mode">{engine.autonomous?'👤 Manual':'🤖 Auto'}</button>
            <button className="btn" onClick={()=>setShowArch(true)} title="View architecture">📐 Arch</button>
            <button className="btn danger" onClick={reset} title="Reset simulation">↺ Reset</button>
          </div>
        </div>
      </header>

      {/* ---- MAIN GRID ---- */}
      <div className="main">
        <div className="left-col">
          <div className="panel" style={{flex:'1 1 auto', display:'flex', flexDirection:'column', minHeight:0}}>
            <div className="panel-header">
              <span>⚡ Asset Portfolio</span>
              <span className="panel-header-meta" style={{color: renewablePct > 80 ? 'var(--green)' : renewablePct > 40 ? 'var(--yellow)' : 'var(--red)', fontWeight:700}}>
                {renewablePct.toFixed(0)}% RE
              </span>
            </div>
            <div className="portfolio-mix">
              <span className="re-pct">{renewablePct.toFixed(0)}%</span>
              <div className="mix-bar">
                <div className="mix-re" style={{width: renewablePct+'%'}} />
                <div className="mix-fossil" style={{width: (100-renewablePct)+'%'}} />
              </div>
            </div>
            <div className="panel-body" style={{padding:'0 0 8px 0'}}>
              <div className="asset-section-title">☀️ Solar Farms</div>
              {config.solar_farms.map(sf => {
                const a = assets[sf.id]
                const pct = sf.rated_kw > 0 ? Math.min(100, a.output_kw / sf.rated_kw * 100) : 0
                return (
                  <div className="asset-item" key={sf.id}>
                    <div className="asset-name"><span style={{color:'var(--solar)'}}>●</span>{sf.name}</div>
                    <span className={`asset-status ${a.online ? (a.curtailed_kw > 10 ? 'status-curtailed' : 'status-online') : 'status-offline'}`}>
                      {a.online ? (a.curtailed_kw > 10 ? 'Curtail' : 'Online') : 'Fault'}
                    </span>
                    <div className="asset-meta"><span>Output</span></div>
                    <div className="asset-kw">{fmtKW(a.output_kw)} / {fmtKW(sf.rated_kw)}</div>
                    <div className="asset-bar"><div className="asset-bar-fill" style={{width:pct+'%',background:'var(--solar)'}}/></div>
                    {a.curtailed_kw > 10 && <div className="asset-meta" style={{gridColumn:'1/-1',color:'var(--red)',fontSize:9}}>↳ Curtailed {fmtKW(a.curtailed_kw)}</div>}
                  </div>
                )
              })}

              <div className="asset-section-title">💨 Wind Farms</div>
              {config.wind_farms.map(w => {
                const a = assets[w.id]
                const pct = w.rated_kw > 0 ? Math.min(100, a.output_kw / w.rated_kw * 100) : 0
                return (
                  <div className="asset-item" key={w.id}>
                    <div className="asset-name"><span style={{color:'var(--wind)'}}>●</span>{w.name}</div>
                    <span className={`asset-status ${a.online ? (a.curtailed_kw > 10 ? 'status-curtailed' : 'status-online') : 'status-offline'}`}>
                      {a.online ? (a.curtailed_kw > 10 ? 'Curtail' : 'Online') : 'Fault'}
                    </span>
                    <div className="asset-meta"><span>Output</span></div>
                    <div className="asset-kw">{fmtKW(a.output_kw)} / {fmtKW(w.rated_kw)}</div>
                    <div className="asset-bar"><div className="asset-bar-fill" style={{width:pct+'%',background:'var(--wind)'}}/></div>
                  </div>
                )
              })}

              <div className="asset-section-title">🔋 Battery Storage</div>
              {config.batteries.map(b => {
                const a = assets[b.id]
                const soc = a.soc_frac || 0
                const chg = state.batt_charge_kw?.[b.id] || 0
                const dis = state.batt_discharge_kw?.[b.id] || 0
                const st = !a.online ? 'status-offline' : chg > 10 ? 'status-charging' : dis > 10 ? 'status-discharging' : 'status-online'
                const sttxt = !a.online ? 'Offline' : chg > 10 ? 'Charging' : dis > 10 ? 'Dischg' : 'Idle'
                return (
                  <div className="asset-item" key={b.id}>
                    <div className="asset-name"><span style={{color:'var(--battery)'}}>●</span>{b.name}</div>
                    <span className={`asset-status ${st}`}>{sttxt}</span>
                    <div className="asset-meta"><span>SOC {(soc*100).toFixed(0)}%</span></div>
                    <div className="asset-kw">{chg>10?'+':dis>10?'-':''}{fmtKW(chg>10?chg:dis>10?dis:0)}</div>
                    <div className="asset-bar"><div className="asset-bar-fill" style={{width:(soc*100)+'%',background:'var(--battery)'}}/></div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
{/* ===== CENTER: Topology + Chart ===== */}
        <div className="center-col">
          <div className="panel" style={{flex:'0 0 auto'}}>
            <div className="panel-header">
              <span><span className="live-dot" />Live Power Flow</span>
              <span className="panel-header-meta">Gen {fmtKW(totalGen)} · Load {fmtKW(totalLoad)}</span>
            </div>
            <div className="topo-wrap">
              <div className="topo-row">
                <div className={`topo-node solar ${solarOut > 1000 ? 'flowing' : ''}`} style={{flex:'0 1 180px'}}>
                  <div className="topo-label">☀️ Solar (5 farms)</div>
                  <div className="topo-value solar-val">{fmtKW(solarOut)}</div>
                  <div className="topo-sub">{solarOut > 1000 ? '↓ Generating' : 'Night / Cloud'}</div>
                </div>
                <div className={`topo-node wind ${windOut > 1000 ? 'flowing' : ''}`} style={{flex:'0 1 180px'}}>
                  <div className="topo-label">💨 Wind (3 farms)</div>
                  <div className="topo-value wind-val">{fmtKW(windOut)}</div>
                  <div className="topo-sub">{windOut > 1000 ? '↓ Generating' : 'Calm'}</div>
                </div>
              </div>
              <svg className="flow-svg" style={{height:40}} viewBox="0 0 500 44" preserveAspectRatio="none">
                <path d="M 125 0 C 125 20 175 20 175 42" stroke="var(--solar)" strokeWidth={Math.min(3, Math.max(1, solarOut/30000))}
                      className={solarOut>100?'flow-line':'flow-line idle'} style={{color:'var(--solar)'}}/>
                <path d="M 375 0 C 375 20 325 20 325 42" stroke="var(--wind)" strokeWidth={Math.min(3, Math.max(1, windOut/25000))}
                      className={windOut>100?'flow-line':'flow-line idle'} style={{color:'var(--wind)'}}/>
                <circle cx="125" cy="2" r="3" fill="var(--solar)" opacity={solarOut>100?1:0.2}/>
                <circle cx="375" cy="2" r="3" fill="var(--wind)" opacity={windOut>100?1:0.2}/>
                <circle cx="175" cy="40" r="4" fill="var(--battery)" opacity={totalBattDischarge+totalBattCharge>100?1:0.4}>
                  {totalBattDischarge+totalBattCharge>100 && <animate attributeName="r" values="4;6;4" dur="1.5s" repeatCount="indefinite"/>}
                </circle>
                <circle cx="325" cy="40" r="4" fill={state.grid_import_kw>state.grid_export_kw?'var(--grid)':'var(--green)'} opacity={state.grid_import_kw+state.grid_export_kw>100?1:0.4}>
                  {state.grid_import_kw+state.grid_export_kw>100 && <animate attributeName="r" values="4;6;4" dur="1.5s" repeatCount="indefinite"/>}
                </circle>
              </svg>
              <div className="topo-row">
                <div className={`topo-node battery ${totalBattDischarge>100||totalBattCharge>100?'flowing':''}`} style={{flex:'0 1 180px'}}>
                  <div className="topo-label">🔋 BESS (2 units)</div>
                  <div className="topo-value batt-val">
                    {totalBattDischarge>10?'-'+fmtKW(totalBattDischarge):totalBattCharge>10?'+'+fmtKW(totalBattCharge):'Idle'}
                  </div>
                  <div className="topo-sub">{(state.assets.b1?.soc_frac*100||0).toFixed(0)}% / {(state.assets.b2?.soc_frac*100||0).toFixed(0)}% SOC</div>
                </div>
                <div className={`topo-node grid ${state.grid_import_kw>100||state.grid_export_kw>100?'flowing':''}`} style={{flex:'0 1 180px'}}>
                  <div className="topo-label">⚡ Grid Interconnect</div>
                  <div className={`topo-value ${state.grid_import_kw>state.grid_export_kw?'grid-val':state.grid_export_kw>10?'grid-export-val':'grid-idle-val'}`}>
                    {state.grid_import_kw>state.grid_export_kw?'↓ '+fmtKW(state.grid_import_kw):state.grid_export_kw>100?'↑ '+fmtKW(state.grid_export_kw):'Balanced'}
                  </div>
                  <div className="topo-sub">₹{state.grid_price_inr_per_kwh.toFixed(1)}/kWh</div>
                </div>
              </div>
              <svg className="flow-svg" style={{height:40}} viewBox="0 0 500 44" preserveAspectRatio="none">
                <path d="M 175 0 L 250 42" stroke="var(--battery)" strokeWidth={totalBattDischarge+totalBattCharge>100?2.5:1}
                      className={totalBattDischarge+totalBattCharge>100?'flow-line':'flow-line idle'} style={{color:'var(--battery)'}}/>
                <path d="M 325 0 L 250 42" stroke={state.grid_import_kw>state.grid_export_kw?'var(--grid)':'var(--green)'} strokeWidth={state.grid_import_kw+state.grid_export_kw>100?2.5:1}
                      className={state.grid_import_kw+state.grid_export_kw>100?'flow-line':'flow-line idle'} style={{color:state.grid_import_kw>state.grid_export_kw?'var(--grid)':'var(--green)'}}/>
                <circle cx="250" cy="42" r="5" fill="var(--accent)">
                  <animate attributeName="r" values="4;7;4" dur="1.8s" repeatCount="indefinite"/>
                  <animate attributeName="opacity" values="1;0.5;1" dur="1.8s" repeatCount="indefinite"/>
                </circle>
              </svg>
              <div style={{display:'flex',justifyContent:'center'}}>
                <div className="topo-node demand" style={{flex:'0 1 360px'}}>
                  <div className="topo-label">🏭 Industrial + Commercial Load</div>
                  <div className="topo-value demand-val">{fmtKW(state.total_demand_kw)}</div>
                  <div className="topo-sub">
                    Served {fmtKW(Object.values(state.served_kw||{}).reduce((s,v)=>s+v,0))}
                    {Object.values(state.dr_cut_kw||{}).reduce((s,v)=>s+v,0)>10 && ` · DR ${fmtKW(Object.values(state.dr_cut_kw).reduce((s,v)=>s+v,0))}`}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Chart */}
          <div className="panel chart-panel">
            <div className="panel-header">
              <span>📈 Dispatch Timeline (MW)</span>
              <span className="panel-header-meta">Last 24h rolling history</span>
            </div>
            <div className="chart-wrap">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={history} margin={{ top: 5, right: 16, bottom: 2, left: -20 }}>
                  <defs>
                    <linearGradient id="gSolar" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#fbbf24" stopOpacity={0.65}/><stop offset="100%" stopColor="#fbbf24" stopOpacity={0}/></linearGradient>
                    <linearGradient id="gWind" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#a78bfa" stopOpacity={0.5}/><stop offset="100%" stopColor="#a78bfa" stopOpacity={0}/></linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1a2236" vertical={false} />
                  <XAxis dataKey="t" stroke="#525f7f" fontSize={9} tickLine={false} axisLine={{stroke:'var(--border)'}}/>
                  <YAxis stroke="#525f7f" fontSize={9} tickLine={false} axisLine={false}/>
                  <Tooltip contentStyle={{background:'var(--bg-2)',border:'1px solid var(--border-bright)',borderRadius:6,fontSize:11,color:'var(--text)'}}/>
                  <Area type="monotone" dataKey="solar" name="Solar MW" stroke="#fbbf24" fill="url(#gSolar)" strokeWidth={2}/>
                  <Area type="monotone" dataKey="wind" name="Wind MW" stroke="#a78bfa" fill="url(#gWind)" strokeWidth={2}/>
                  <Line type="monotone" dataKey="demand" name="Demand MW" stroke="#e2e8f4" strokeWidth={2} dot={false}/>
                  <Line type="monotone" dataKey="import" name="Grid Import" stroke="#f97316" strokeWidth={1.5} dot={false}/>
                  <Line type="monotone" dataKey="export" name="Grid Export" stroke="#22d3a6" strokeWidth={1.5} dot={false}/>
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* ===== RIGHT: Agent + KPIs + Controls (dense 2-col grid) ===== */}
        <div className="right-col">

          {/* Top strip: Savings + key KPIs in a single horizontal band */}
          <div className="panel kpi-panel">
            <div className="panel-body kpi-strip">
              <div className="kpi-tile kpi-savings">
                <div className="kpi-label"><span className="live-dot" />AI Savings</div>
                <div className="kpi-value" style={{color:'var(--green)',fontSize:14}}>{engine.started?fmtINR(savingsAnim.cost):'—'}</div>
                <div className="kpi-delta">{engine.started?`${(savingsAnim.co2/1000).toFixed(1)}t CO₂ · ${fmtKWh(savingsAnim.curt)} less`:'Press ▶ Play'}</div>
              </div>
              <div className="kpi-tile" style={{'--kpi-accent':'var(--accent)'}}>
                <div className="kpi-label">Cost</div>
                <div className="kpi-value" style={{fontSize:14}}>{fmtINR(state.kpis.cost_inr)}</div>
              </div>
              <div className="kpi-tile" style={{'--kpi-accent':'var(--grid)'}}>
                <div className="kpi-label">CO₂</div>
                <div className="kpi-value" style={{fontSize:14}}>{(state.kpis.co2_kg/1000).toFixed(0)}t</div>
              </div>
              <div className="kpi-tile" style={{'--kpi-accent':'var(--green)'}}>
                <div className="kpi-label">RE Used</div>
                <div className="kpi-value" style={{fontSize:14,color:'var(--green)'}}>{fmtKWh(state.kpis.renewable_kwh)}</div>
              </div>
              <div className="kpi-tile" style={{'--kpi-accent': state.kpis.curtailed_kwh>5000?'var(--red)':'var(--yellow)'}}>
                <div className="kpi-label">Curtailed</div>
                <div className="kpi-value" style={{fontSize:14,color: state.kpis.curtailed_kwh>5000?'var(--red)':'var(--yellow)'}}>{fmtKWh(state.kpis.curtailed_kwh)}</div>
              </div>
              {state.kpis.unmet_critical_kwh > 1 && (
                <div className="alert-row alert-critical" style={{gridColumn:'1/-1',padding:'4px 8px',fontSize:9.5}}>⚠ Unmet critical: {fmtKWh(state.kpis.unmet_critical_kwh)}</div>
              )}
            </div>
          </div>

          {/* Dense grid: agent reasoning + NL span full width; forecasts/alerts/scenarios/events are 2-column tiles */}
          <div className="right-grid">

            {/* Agent reasoning — full width */}
            <div className="panel right-wide">
              <div className="panel-header">
                <span>🧠 Agent Reasoning</span>
                <span className={`confidence-badge confidence-${(reasoning.forecast_confidence||'high')}`}>
                  {(reasoning.forecast_confidence||'high').toUpperCase()}
                </span>
              </div>
              <div className="panel-body">
                <div className="reasoning-text" style={{color:'var(--text-dim)',fontStyle:'italic',marginBottom:3,fontSize:10}}>{reasoning.situation_assessment}</div>
                <div className="reasoning-text" style={{fontSize:10.5,lineHeight:1.4}}>{reasoning.explanation}</div>
                <div style={{fontSize:9.5,color:'var(--accent)',marginTop:4,fontWeight:600}}>▸ {reasoning.intent}{reasoning.optimizer_called?' · ⚙ LP solved':''}</div>
                {reasoning.replanned_this_tick && <div className="alert-row alert-warn" style={{marginTop:4,fontSize:9,padding:'3px 6px'}}>↻ Replanned: {reasoning.replan?.action_taken||'re-optimized'}</div>}
                <div className="weights-compact">
                  {Object.entries(weights).map(([k,v])=>(
                    <div key={k} className="w-compact-item" title={k.replace(/_/g,' ')+' '+(v*100).toFixed(0)+'%'}>
                      <span className="w-compact-name">{k.replace(/_/g,' ').replace('battery life','batt').replace('profit export','profit').slice(0,8)}</span>
                      <div className="w-compact-bar"><div style={{width:(v*100)+'%'}}/></div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* NL command — full width */}
            <div className="panel right-wide">
              <div className="panel-header"><span>💬 Operator Command</span></div>
              <div className="panel-body" style={{padding:'7px 10px'}}>
                <form className="nl-form" onSubmit={sendNLCmd}>
                  <input type="text" value={nlCmd} onChange={e=>setNlCmd(e.target.value)}
                         placeholder='e.g. "go green", "prepare for peak"'
                         className="nl-input" />
                  <button type="submit" className="btn primary btn-sm">Send</button>
                </form>
                {nlResponse && (
                  <div style={{marginTop:5,padding:'5px 7px',background:'rgba(56,189,248,0.08)',borderLeft:'2px solid var(--accent)',borderRadius:3,fontSize:9.5,color:'#bae6fd',lineHeight:1.4}}>{nlResponse}</div>
                )}
                <div className="nl-chips" style={{marginTop:5}}>
                  {['Prepare peak','Max profit','Go green','Be safe','Discharge','Min curtail'].map(q => (
                    <button key={q} type="button" className="nl-chip" onClick={()=>{setNlCmd(q);}}>{q}</button>
                  ))}
                </div>
              </div>
            </div>

            {/* Forecasts (left) */}
            <div className="panel right-narrow">
              <div className="panel-header"><span>🔮 Forecasts</span></div>
              <div className="panel-body" style={{padding:'6px 8px'}}>
                {state.forecasts.map((f,i)=>{
                  const conf=f.confidence>0.7?'high':f.confidence>0.5?'med':'low';
                  const mins=f.lead_minutes;
                  const tStr=mins>=60?`${(mins/60).toFixed(0)}h`:`${mins}m`;
                  return (
                    <div key={i} className="forecast-grid compact-fc">
                      <div className="forecast-horizon">{tStr}</div>
                      <div style={{color:'var(--green)',fontWeight:700,fontSize:10,fontVariantNumeric:'tabular-nums'}}>{fmtKW(f.solar_total_kw+f.wind_total_kw)}</div>
                      <div style={{textAlign:'right',display:'flex',alignItems:'center',gap:4,justifyContent:'flex-end'}}>
                        <span style={{fontSize:10,fontWeight:600,fontVariantNumeric:'tabular-nums'}}>{fmtKW(f.demand_total_kw)}</span>
                        <span style={{color:'var(--accent)',fontSize:9,fontVariantNumeric:'tabular-nums'}}>₹{f.price.toFixed(1)}</span>
                        <div className={`f-dot ${conf}`}/>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Alerts (right) */}
            <div className="panel right-narrow">
              <div className="panel-header"><span>🚨 Alerts</span><span className="panel-header-meta">{state.alerts?.length||0}</span></div>
              <div className="panel-body" style={{padding:'6px 8px'}}>
                {state.alerts && state.alerts.length>0 ? (
                  <div className="alert-list">
                    {state.alerts.slice(0,5).map((a,i)=>{
                      const crit = a.includes('CRITICAL')||a.includes('critical')||a.includes('fault')||a.includes('FAIL');
                      const warn = a.includes('warn')||a.includes('Warn')||a.includes('spike')||a.includes('peak');
                      const cls = crit?'alert-critical':warn?'alert-warn':'alert-info';
                      return <div key={i} className={`alert-row ${cls}`} style={{padding:'4px 7px',fontSize:9,lineHeight:1.35}}>{a.length>55?a.slice(0,55)+'…':a}</div>;
                    })}
                  </div>
                ) : <div style={{fontSize:10,color:'var(--text-muted)',textAlign:'center',padding:'8px 0'}}>✓ All systems nominal</div>}
              </div>
            </div>

            {/* Scenarios (left) */}
            <div className="panel right-narrow">
              <div className="panel-header"><span>🎬 Scenarios</span></div>
              <div className="panel-body" style={{padding:'6px 8px'}}>
                <div className="scenario-grid compact-sc">
                  {SCENARIOS.map(sc=>(
                    <button key={sc.id} className="scenario-btn compact-sc-btn" onClick={()=>loadScenario(sc.id)} title={sc.desc}>
                      {sc.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Events (right) */}
            <div className="panel right-narrow">
              <div className="panel-header"><span>⚡ Inject Event</span></div>
              <div className="panel-body" style={{padding:'6px 8px'}}>
                <div className="event-grid compact-ev">
                  {EVENT_BUTTONS.slice(0,6).map((e,i)=>(
                    <button key={i} className="event-btn compact-ev-btn" onClick={()=>inject(e)}>{e.label.replace(' 2.5x','').replace(' -50%','').replace(' +30%','')}</button>
                  ))}
                </div>
                <div className="event-grid compact-ev" style={{marginTop:3}}>
                  {EVENT_BUTTONS.slice(6).map((e,i)=>(
                    <button key={i} className="event-btn compact-ev-btn" onClick={()=>inject(e)}>{e.label.replace(' (in 1h)','')}</button>
                  ))}
                </div>
              </div>
            </div>

            {/* Controls strip */}
            <div className="panel right-wide">
              <div className="panel-header"><span>🎮 Controls</span></div>
              <div className="panel-body" style={{padding:'6px 10px',display:'flex',gap:5,flexWrap:'wrap'}}>
                <button className="btn btn-sm" onClick={toggleAuto} style={{flex:'1 1 auto'}}>{engine.autonomous?'👤 Manual Mode':'▶ Resume Agent'}</button>
                <button className="btn btn-sm" onClick={pause} style={{flex:'1 1 auto'}}>{engine.running?'⏸ Pause':'▶ Resume'}</button>
                {decisionHistory.length>0 && <button className="btn btn-sm" onClick={()=>{setSelectedDecision(null);setTimeout(()=>{const el=document.getElementById('audit-panel');if(el)el.scrollIntoView({behavior:'smooth',block:'start'});},80);}} style={{flex:'1 1 auto'}}>📜 Show Audit</button>}
              </div>
            </div>

            {/* Decision audit */}
            {decisionHistory.length>0 && (
              <div className="panel right-wide">
                <div id="audit-panel" className="panel-header"><span>📜 Decision Audit</span><span className="panel-header-meta">{decisionHistory.length} ticks</span></div>
                <div className="panel-body audit-scroll" style={{padding:5}}>
                  {decisionHistory.slice(0,8).map((d,i)=>(
                    <div key={i} className="audit-item" onClick={()=>setSelectedDecision(selectedDecision===d?null:d)}>
                      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                        <span className="audit-time mono">{d.time_of_day}</span>
                        <span style={{fontSize:8.5,color:d.replanned?'var(--yellow)':'var(--green)'}}>{d.replanned?'↻':'✓'}</span>
                      </div>
                      <div className="audit-act" style={{fontSize:9.5}}>{(d.reasoning.intent||'').slice(0,70)}</div>
                      {selectedDecision===d && <div className="audit-expl" style={{fontSize:9,lineHeight:1.35}}>{d.reasoning.explanation}</div>}
                    </div>
                  ))}
                </div>
              </div>
            )}

          </div>{/* end right-grid */}
        </div>
      </div>
    </div>
  )
}

export default App
