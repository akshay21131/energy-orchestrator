#!/usr/bin/env python3
"""Build the fixed ET x Accenture pitch deck (10 slides, no team names)."""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

# Colors
BG       = RGBColor(0x0B, 0x0F, 0x1A)
BG2      = RGBColor(0x12, 0x1A, 0x2E)
BG3      = RGBColor(0x16, 0x22, 0x40)
BORDER   = RGBColor(0x2A, 0x3A, 0x5C)
ACCENT   = RGBColor(0x38, 0xBD, 0xF8)
GREEN    = RGBColor(0x34, 0xD3, 0x99)
SOLAR    = RGBColor(0xFB, 0xBF, 0x24)
WIND     = RGBColor(0xA7, 0x8B, 0xFA)
GRID     = RGBColor(0xF9, 0x73, 0x16)
TEXT     = RGBColor(0xE6, 0xED, 0xF9)
WHITE    = RGBColor(0xFF, 0xFF, 0xFF)
TEXT_DIM = RGBColor(0x94, 0xA3, 0xC4)
RED      = RGBColor(0xEF, 0x44, 0x44)

prs = Presentation()
prs.slide_width  = Inches(13.333)
prs.slide_height = Inches(7.5)
SW, SH = prs.slide_width, prs.slide_height
BLANK = prs.slide_layouts[6]
TOTAL = 10

def bg(slide, color=BG):
    r = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SW, SH)
    r.line.fill.background(); r.fill.solid(); r.fill.fore_color.rgb = color

def rect(slide, x, y, w, h, color):
    s = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    s.fill.solid(); s.fill.fore_color.rgb = color; s.line.fill.background()
    return s

def rrect(slide, x, y, w, h, color, border=None):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    s.fill.solid(); s.fill.fore_color.rgb = color
    if border: s.line.color.rgb = border; s.line.width = Pt(1)
    else: s.line.fill.background()
    return s

def text(slide, x, y, w, h, t, size=14, bold=False, color=TEXT, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, font='Calibri'):
    tb = slide.shapes.add_textbox(x, y, w, h); tf = tb.text_frame; tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.05); tf.margin_top = tf.margin_bottom = Inches(0.02)
    tf.vertical_anchor = anchor
    for i, ln in enumerate(t.split('\n')):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run(); r.text = ln
        r.font.size = Pt(size); r.font.bold = bold; r.font.color.rgb = color; r.font.name = font
    return tb

def bullets(slide, x, y, w, h, items, size=16, color=TEXT, bullet_color=ACCENT, spacing=1.3):
    tb = slide.shapes.add_textbox(x, y, w, h); tf = tb.text_frame; tf.word_wrap = True
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT; p.line_spacing = spacing
        r1 = p.add_run(); r1.text = "▸  "
        r1.font.size = Pt(size); r1.font.color.rgb = bullet_color; r1.font.bold = True
        r2 = p.add_run(); r2.text = it
        r2.font.size = Pt(size); r2.font.color.rgb = color; r2.font.name = 'Calibri'

def footer(slide, n):
    rect(slide, 0, SH-Inches(0.04), SW, Inches(0.04), ACCENT)
    text(slide, Inches(0.5), SH-Inches(0.32), Inches(8), Inches(0.28),
         "Renewable Energy Orchestrator  ·  ET × Accenture AI Hackathon — Agentic Edition  ·  Problem 4",
         size=10, color=TEXT_DIM)
    text(slide, SW-Inches(1.2), SH-Inches(0.32), Inches(0.7), Inches(0.28),
         f"{n} / {TOTAL}", size=10, color=TEXT_DIM, align=PP_ALIGN.RIGHT)

def header(slide, eyebrow, title):
    rect(slide, 0, 0, SW, Inches(0.08), ACCENT)
    text(slide, Inches(0.6), Inches(0.4), Inches(12), Inches(0.35), eyebrow, size=12, bold=True, color=ACCENT)
    text(slide, Inches(0.6), Inches(0.7), Inches(12), Inches(0.7), title, size=32, bold=True, color=WHITE)
    rect(slide, Inches(0.6), Inches(1.45), Inches(0.7), Inches(0.05), GREEN)

# ========== SLIDE 1 - TITLE ==========
s = prs.slides.add_slide(BLANK); bg(s)
rect(s, 0, 0, SW, Inches(0.08), ACCENT)
rect(s, 0, SH-Inches(0.08), SW, Inches(0.08), GREEN)
# Logo
rrect(s, Inches(5.4), Inches(1.0), Inches(2.5), Inches(2.5), ACCENT)
text(s, Inches(5.4), Inches(1.0), Inches(2.5), Inches(2.5), "⚡", size=120, bold=True,
     color=BG, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
# Badge
rrect(s, Inches(4.6), Inches(3.75), Inches(4.2), Inches(0.45), RGBColor(0x10,0x2a,0x43), border=GREEN)
text(s, Inches(4.6), Inches(3.75), Inches(4.2), Inches(0.45),
     "9-BLOCKER D2 / F3  ·  AUTONOMOUS GRID AGENT", size=12, bold=True, color=GREEN,
     align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
text(s, Inches(0.6), Inches(4.4), SW-Inches(1.2), Inches(1.2),
     "Renewable Energy\nOrchestrator", size=58, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
text(s, Inches(0.6), Inches(6.0), SW-Inches(1.2), Inches(0.5),
     "An Autonomous AI Agent for India's 500 GW Renewable Future", size=20, color=ACCENT, align=PP_ALIGN.CENTER)
text(s, Inches(0.6), Inches(6.5), SW-Inches(1.2), Inches(0.4),
     "Real-time dispatch of solar, wind, batteries, grid, and demand — every 15 minutes.",
     size=14, color=TEXT_DIM, align=PP_ALIGN.CENTER)

# ========== SLIDE 2 - PROBLEM ==========
s = prs.slides.add_slide(BLANK); bg(s)
header(s, "01  ·  PROBLEM", "India's Renewable Grid Needs an Intelligent Operator")
# Four stat cards
stats = [
    ("500 GW", "Renewable target\nby 2030", SOLAR),
    ("₹1.2L Cr+", "Lost annually to\ncurtailment + diesel", RED),
    ("15 min", "Decision window\nfor operators", ACCENT),
    ("6+", "Competing objectives\nto balance", GREEN),
]
sx = Inches(0.6); sy = Inches(1.9); sw = Inches(2.95); sh = Inches(1.6); sgap = Inches(0.17)
for i,(big,small,c) in enumerate(stats):
    x = sx + i*(sw+sgap)
    rrect(s, x, sy, sw, sh, BG2, border=BORDER)
    rect(s, x, sy, Inches(0.1), sh, c)
    text(s, x+Inches(0.3), sy+Inches(0.2), sw-Inches(0.5), Inches(0.7), big, size=36, bold=True, color=c)
    text(s, x+Inches(0.3), sy+Inches(0.95), sw-Inches(0.5), Inches(0.6), small, size=14, color=TEXT_DIM)
# Left: problems
text(s, Inches(0.6), Inches(3.8), Inches(6), Inches(0.4), "Why today's approach fails", size=18, bold=True, color=WHITE)
bullets(s, Inches(0.6), Inches(4.25), Inches(6), Inches(2.8), [
    "Solar and wind are intermittent — forecasts are uncertain; static dispatch rules break under volatility.",
    "Operators must balance cost, carbon, reliability, battery health, curtailment, and profit — humans cannot optimize 20+ variables every 15 minutes.",
    "Batteries are under-utilized as arbitrage + reserve assets; expensive diesel peakers fire up when stored solar could have been used.",
    "Demand response and grid export are rarely coordinated in real time.",
], size=14)
# Right: opportunity
rrect(s, Inches(7.1), Inches(3.8), Inches(5.7), Inches(3.0), RGBColor(0x0e,0x1c,0x17), border=GREEN)
rect(s, Inches(7.1), Inches(3.8), Inches(0.1), Inches(3.0), GREEN)
text(s, Inches(7.4), Inches(3.95), Inches(5.3), Inches(0.4), "⚡  Our Solution", size=18, bold=True, color=GREEN)
text(s, Inches(7.4), Inches(4.45), Inches(5.3), Inches(2.3),
     "An autonomous AI agent that:\n\n"
     "• reads telemetry and forecasts every 15 minutes,\n"
     "• reasons about anomalies and uncertainty,\n"
     "• calls a numerical LP optimizer as a tool,\n"
     "• validates the plan and re-plans if needed,\n"
     "• dispatches batteries, grid, curtailment, and DR,\n"
     "• accepts natural-language operator commands.\n\n"
     "Result: 71% cost cut, 153 t CO₂/day avoided, zero critical outages.",
     size=13, color=TEXT)
footer(s, 2)

# ========== SLIDE 3 - SOLUTION / AGENT LOOP ==========
s = prs.slides.add_slide(BLANK); bg(s)
header(s, "02  ·  PROPOSED SOLUTION", "A Genuinely Agentic Loop: Observe → Reason → Optimize → Validate → Act")
stages = [
    ("👁️", "OBSERVE",  "Telemetry from 11 assets\n+ 5-horizon forecasts\n+ alerts", ACCENT),
    ("🧠", "REASON",   "Diagnose anomalies;\nchoose 6 objective weights\n+ battery reserve", SOLAR),
    ("⚙️", "OPTIMIZE", "Calls LP solver (PuLP/CBC)\n— ~20 variables, <50 ms\n— as a tool", WIND),
    ("✓",  "VALIDATE", "Check critical load,\nSOC bounds, price\nsanity; replan on fail", RED),
    ("⚡", "ACT",      "Dispatch kW flows;\nstream to dashboard;\nlog to audit trail", GREEN),
]
sx = Inches(0.5); sy = Inches(2.0); sw = Inches(2.4); sh = Inches(2.4); sgap = Inches(0.13)
for i,(ic,nm,desc,c) in enumerate(stages):
    x = sx + i*(sw+sgap)
    rrect(s, x, sy, sw, sh, BG2, border=BORDER)
    rect(s, x, sy, sw, Inches(0.08), c)
    text(s, x, sy+Inches(0.3), sw, Inches(0.8), ic, size=40, color=c, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    text(s, x, sy+Inches(1.15), sw, Inches(0.4), nm, size=16, bold=True, color=c, align=PP_ALIGN.CENTER)
    text(s, x+Inches(0.2), sy+Inches(1.6), sw-Inches(0.4), Inches(0.8), desc, size=12, color=TEXT_DIM, align=PP_ALIGN.CENTER)
    if i < 4:
        ax = x + sw; text(s, ax, sy+Inches(0.85), sgap, Inches(0.7), "→", size=26, bold=True, color=TEXT_DIM, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

text(s, Inches(0.6), Inches(4.7), Inches(12), Inches(0.4), "What makes this agentic (not an LP with an LLM wrapper)", size=18, bold=True, color=ACCENT)
bullets(s, Inches(0.6), Inches(5.15), Inches(5.9), Inches(2.0), [
    "The agent chooses objective weights + reserve dynamically per tick; the LP is a called tool, not the brain.",
    "Closed-loop reflection: validation failures trigger an automatic replan with higher reliability weight.",
    "Forecast confidence modulates risk posture (low confidence → higher battery reserve).",
], size=13, bullet_color=ACCENT)
bullets(s, Inches(6.9), Inches(5.15), Inches(5.9), Inches(2.0), [
    "Natural-language commands from operators blend with (not override) the agent's reasoning.",
    "Structured telemetry + textual alerts (D2); continuous multi-timestep simulation under varying conditions (F3).",
    "Hard safety layer (SOC 10–95% bounds, power-balance equality, ₹50/kWh critical penalty) can never be overridden.",
], size=13, bullet_color=GREEN)
footer(s, 3)

# ========== SLIDE 4 - ARCHITECTURE ==========
s = prs.slides.add_slide(BLANK); bg(s)
header(s, "03  ·  ARCHITECTURE", "Four-Layered System with an Immutable Safety Layer")
# Four main layers (wider, no overlap)
lanes = [
    ("🧑‍💻   OPERATOR DASHBOARD", "React 19 · Recharts · WebSocket streaming (sub-50 ms)\nGlass UI with live topology, dispatch chart, NL commands, audit trail", ACCENT, Inches(1.85)),
    ("🧠   AGENT BRAIN",         "Observe → Reason → Optimize → Validate → Act\nRule-based expert (default, offline) · LLM-adaptive when API key present", SOLAR,   Inches(3.05)),
    ("⚙️    LP OPTIMIZER (TOOL)", "PuLP / CBC MILP · ~20 variables · <50 ms per tick\nPower balance · SOC evolution · charge/discharge exclusivity · DR caps · line derates", WIND,    Inches(4.25)),
    ("🌍   SIMULATION WORLD",    "5 solar (93 MW) · 3 wind (75 MW) · 2 BESS (40 MW / 160 MWh)\nGrid interconnection (TOU tariffs) · 3 industrial loads · 5 forecast horizons with confidence", GREEN,   Inches(5.45)),
]
for name, desc, c, y in lanes:
    rrect(s, Inches(0.6), y, Inches(12.1), Inches(1.0), BG2, border=BORDER)
    rect(s, Inches(0.6), y, Inches(0.12), Inches(1.0), c)
    text(s, Inches(0.95), y+Inches(0.12), Inches(11.5), Inches(0.35), name, size=16, bold=True, color=WHITE)
    text(s, Inches(0.95), y+Inches(0.5), Inches(11.5), Inches(0.5), desc, size=12, color=TEXT_DIM)
# Vertical arrows on the right
for y in [Inches(2.85), Inches(4.05), Inches(5.25)]:
    text(s, Inches(6.4), y, Inches(0.4), Inches(0.3), "⇅", size=20, bold=True, color=ACCENT, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
# Safety layer — full-width BANNER at bottom (not floating random box)
rect(s, Inches(0.6), Inches(6.55), Inches(12.1), Inches(0.55), RGBColor(0x1a,0x0e,0x0e), )
rrect(s, Inches(0.6), Inches(6.55), Inches(12.1), Inches(0.55), RGBColor(0x1a,0x0e,0x0e), border=RED)
rect(s, Inches(0.6), Inches(6.55), Inches(0.12), Inches(0.55), RED)
text(s, Inches(0.9), Inches(6.55), Inches(2.7), Inches(0.55),
     "🛡  SAFETY LAYER  (cannot be overridden)", size=12, bold=True, color=RED, anchor=MSO_ANCHOR.MIDDLE)
text(s, Inches(3.7), Inches(6.55), Inches(8.9), Inches(0.55),
     "Battery SOC 10–95% hard bounds in LP  ·  Power-balance equality  ·  ₹50/kWh critical-load penalty  ·  Greedy fallback when LP is infeasible  ·  Human pause/override any time",
     size=11, color=TEXT, anchor=MSO_ANCHOR.MIDDLE)
footer(s, 4)

# ========== SLIDE 5 - TECH STACK (2-col layout, bigger fonts) ==========
s = prs.slides.add_slide(BLANK); bg(s)
header(s, "04  ·  AI MODELS & TECHNOLOGIES", "Stack Overview")
# Two columns instead of three cramped ones
col_data = [
    ("AI & Optimization", ACCENT, [
        ("LLM-Adaptive Reasoning",
         "OpenAI-compatible client (Claude / GPT / Gemini) for situation diagnosis, anomaly detection, and dynamic weight selection per tick. Works when an API key is set."),
        ("Rule-Based Expert Brain (Default)",
         "Zero-dependency deterministic engine — delivers identical agentic loop and KPIs without external APIs. Critical for DISCOMs with data-sovereignty constraints."),
        ("Multi-Objective LP Solver",
         "PuLP + CBC as a called tool. ~20 variables, <50 ms per tick. Objectives: cost, carbon, reliability, battery life, curtailment, profit export. Closed-loop replan on validation failure."),
        ("Uncertainty Handling",
         "5 forecast horizons (15m–4h) with confidence values. Low confidence → elevated battery reserve; anomaly triggers (faults, storms, price spikes) automatically shift weights."),
    ]),
    ("Platform & Engineering", GREEN, [
        ("Backend",
         "FastAPI + async WebSockets for sub-50 ms tick broadcast. Structured REST API + WS push. Background tick loop with safety try/except."),
        ("Frontend",
         "React 19 + Vite + Recharts. 16:9 glass-mission-control dashboard with animated power-flow topology, live charts, decision audit, and natural-language command bar."),
        ("Reliability Engineering",
         "Hard safety constraints in LP (not in prompt). Greedy fallback dispatch when LP is infeasible. End-to-end QA: 78/78 checks across 8 phases (health, WS, 4 scenarios, 10 events, 6 NL commands)."),
        ("Deployment",
         "One command: ./run.sh auto-installs deps, builds frontend, starts server. No external API keys required. Ships with a demo simulation representing India's NCR solar/wind mix."),
    ]),
]
cx = Inches(0.5); cy = Inches(1.85); cw = Inches(6.05); ch = Inches(5.1); cg = Inches(0.2)
for i,(title,c,items) in enumerate(col_data):
    x = cx + i*(cw+cg)
    rrect(s, x, cy, cw, ch, BG2, border=BORDER)
    rect(s, x, cy, cw, Inches(0.6), c)
    text(s, x, cy, cw, Inches(0.6), title, size=18, bold=True, color=BG, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    iy = cy + Inches(0.8)
    for (st, desc) in items:
        text(s, x+Inches(0.3), iy, cw-Inches(0.5), Inches(0.3), "▸ "+st, size=13, bold=True, color=c)
        text(s, x+Inches(0.5), iy+Inches(0.3), cw-Inches(0.7), Inches(0.7), desc, size=11, color=TEXT_DIM)
        iy += Inches(1.05)
footer(s, 5)

# ========== SLIDE 6 - LIVE DASHBOARD (real screenshot, full-bleed) ==========
s = prs.slides.add_slide(BLANK); bg(s)
header(s, "05  ·  PRODUCT DEMO", "Live Mission-Control Dashboard")
# Screenshot area
pic_x, pic_y = Inches(0.5), Inches(1.85)
pic_w, pic_h = Inches(12.33), Inches(5.0)
rrect(s, pic_x-Inches(0.04), pic_y-Inches(0.04), pic_w+Inches(0.08), pic_h+Inches(0.08), BG2, border=ACCENT)
s.shapes.add_picture("/home/user/energy_orchestrator/submission/dashboard.png", pic_x, pic_y, width=pic_w, height=pic_h)
# Caption strip under screenshot
text(s, Inches(0.5), Inches(6.9), Inches(12.3), Inches(0.3),
     "◂ Left: Asset portfolio (solar/wind/BESS live outputs)  ·  Center: Live power flow + 24h dispatch timeline  ·  Right: AI savings, reasoning, NL commands, forecasts, controls, audit ▸",
     size=10, color=TEXT_DIM, align=PP_ALIGN.CENTER)
footer(s, 6)

# ========== SLIDE 7 - RESULTS (4 big KPIs + scenarios) ==========
s = prs.slides.add_slide(BLANK); bg(s)
header(s, "06  ·  BUSINESS IMPACT", "Measured Results vs. Dumb-Grid Baseline (24h Simulated Day)")
results = [
    ("71%", "Operating Cost\nReduced", GREEN, "₹13.7 L saved per day\non a ~100 MW portfolio"),
    ("153 t", "CO₂ Emissions\nAvoided", ACCENT, "≈ taking 33 cars off\nthe road per day"),
    ("487 MWh", "Curtailment\nReduced", SOLAR, "Renewable energy that\nwould have been wasted"),
    ("0 MWh", "Unmet Critical\nLoad", GREEN, "100% reliability across\nall stress scenarios"),
]
sx = Inches(0.5); sy = Inches(1.85); sw = Inches(3.0); sh = Inches(2.3); sgap = Inches(0.17)
for i,(big,sub,c,sub2) in enumerate(results):
    x = sx + i*(sw+sgap)
    rrect(s, x, sy, sw, sh, BG2, border=BORDER)
    rect(s, x, sy, sw, Inches(0.1), c)
    text(s, x, sy+Inches(0.35), sw, Inches(0.9), big, size=52, bold=True, color=c, align=PP_ALIGN.CENTER)
    text(s, x+Inches(0.15), sy+Inches(1.35), sw-Inches(0.3), Inches(0.45), sub, size=14, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    text(s, x+Inches(0.15), sy+Inches(1.8), sw-Inches(0.3), Inches(0.45), sub2, size=11, color=TEXT_DIM, align=PP_ALIGN.CENTER)
text(s, Inches(0.6), Inches(4.4), Inches(12), Inches(0.4),
     "Stress-tested across 4 scenarios — zero critical outages every run",
     size=18, bold=True, color=WHITE)
scen = [
    ("☀️ Normal Day",       "Balanced renewable day",                  "60% cost saved  ·  0 unmet load",       ACCENT),
    ("🌡️ Summer Peak",      "Demand surge + price spike",              "62% cost saved  ·  diesel avoided",     GRID),
    ("⛈️ Stormy Night",     "Wind gusts + line trip",                  "Replan triggered  ·  0 outage",          WIND),
    ("📊 Price Volatility", "Extreme price swings",                    "78% cost saved via battery arbitrage",  GREEN),
]
scw = Inches(2.95); scy = Inches(4.95); sch = Inches(1.85)
for i,(t,sub,res,c) in enumerate(scen):
    x = sx + i*(scw+sgap)
    rrect(s, x, scy, scw, sch, BG2, border=BORDER)
    rect(s, x, scy, Inches(0.1), sch, c)
    text(s, x+Inches(0.25), scy+Inches(0.2), scw-Inches(0.4), Inches(0.35), t, size=14, bold=True, color=c)
    text(s, x+Inches(0.25), scy+Inches(0.6), scw-Inches(0.4), Inches(0.4), sub, size=11, color=TEXT_DIM)
    text(s, x+Inches(0.25), scy+Inches(1.15), scw-Inches(0.4), Inches(0.6), "✓  "+res, size=12, bold=True, color=GREEN)
footer(s, 7)

# ========== SLIDE 8 - SCALABILITY ==========
s = prs.slides.add_slide(BLANK); bg(s)
header(s, "07  ·  SCALABILITY", "From One Industrial Site to National Grid")
# Three phases as big blocks
phases = [
    ("🎯 TODAY", "Portfolio Scale", ACCENT,
     ["≈ 100 MW pilot: 5 solar + 3 wind + 2 BESS + 3 industrial loads.",
      "LP solves in <50 ms → 15-minute tick is plenty of headroom.",
      "Per-tick statelessness enables horizontal scaling across portfolios."]),
    ("🚀 NEAR-TERM", "DISCOM Zone", GREEN,
     ["Swap LP for MILP with unit commitment, economic dispatch, and transmission constraints.",
      "Integrate IMD weather APIs, IEX price feeds, SCADA telemetry.",
      "Hierarchical: one agent per zone + coordinating supervisor agent."]),
    ("🌏 LONG-TERM", "National 500 GW Vision", SOLAR,
     ["Multi-zone coordination across state DISCOMs with frequency/stability signals.",
      "Plug in EV fleets, green-hydrogen electrolyzers as flexible loads.",
      "Carbon-credit & REC arbitrage as explicit objectives; autonomous market bidding."]),
]
px = Inches(0.5); py = Inches(1.9); pw = Inches(4.05); ph = Inches(4.8); pgap = Inches(0.17)
for i,(tag,name,c,items) in enumerate(phases):
    x = px + i*(pw+pgap)
    rrect(s, x, py, pw, ph, BG2, border=BORDER)
    rect(s, x, py, pw, Inches(1.0), c)
    text(s, x+Inches(0.3), py+Inches(0.1), pw-Inches(0.6), Inches(0.35), tag, size=12, bold=True, color=BG)
    text(s, x+Inches(0.3), py+Inches(0.45), pw-Inches(0.6), Inches(0.5), name, size=22, bold=True, color=BG)
    iy = py + Inches(1.25)
    for it in items:
        text(s, x+Inches(0.3), iy, pw-Inches(0.5), Inches(0.3), "▸", size=14, bold=True, color=c)
        text(s, x+Inches(0.6), iy, pw-Inches(0.8), Inches(1.0), it, size=13, color=TEXT)
        iy += Inches(1.1)
footer(s, 8)

# ========== SLIDE 9 - ROADMAP ==========
s = prs.slides.add_slide(BLANK); bg(s)
header(s, "08  ·  FUTURE ROADMAP", "Go-To-Market Plan")
phases2 = [
    ("0–30 Days",  "PILOT DEPLOYMENT", ACCENT,
     ["Deploy at one captive industrial site (5–10 MW RE + BESS) in Delhi-NCR.",
      "Integrate with site SCADA and inverter Modbus/REST APIs.",
      "A/B test agent vs human operator on cost, curtailment, and carbon KPIs.",
      "Refine UX with operator feedback."]),
    ("30–90 Days", "DISCOM MVP", SOLAR,
     ["Scale to one DISCOM zone (1–2 GW) with a zonal coordinator agent.",
      "Integrate IMD weather, IEX day-ahead prices, and short-term forecasts.",
      "Confidence-aware forecasting model trained on historical SCADA.",
      "Operator console with anomaly alerting and SLA tracking."]),
    ("6–12 Months", "MARKET LAUNCH", GREEN,
     ["Multi-zone coordination for state-level DISCOMs with transmission constraints.",
      "Onboard EV fleets and green-hydrogen electrolyzers as flexible loads.",
      "Carbon-credit / REC arbitrage; autonomous participation in power exchanges.",
      "Productized SaaS with tenant isolation and audit reporting."]),
]
for i,(when,name,c,items) in enumerate(phases2):
    x = px + i*(pw+pgap)
    rrect(s, x, py, pw, ph, BG2, border=BORDER)
    rect(s, x, py, pw, Inches(1.1), c)
    text(s, x+Inches(0.3), py+Inches(0.12), pw-Inches(0.6), Inches(0.35), when, size=13, bold=True, color=BG)
    text(s, x+Inches(0.3), py+Inches(0.5), pw-Inches(0.6), Inches(0.55), name, size=22, bold=True, color=BG)
    iy = py + Inches(1.35)
    for it in items:
        # bigger bullet, more line space
        text(s, x+Inches(0.3), iy, Inches(0.3), Inches(0.3), "▸", size=14, bold=True, color=c)
        text(s, x+Inches(0.65), iy, pw-Inches(0.85), Inches(0.75), it, size=13, color=TEXT)
        iy += Inches(0.85)
footer(s, 9)

# ========== SLIDE 10 - CLOSING (thank you, no github/demo tiles) ==========
s = prs.slides.add_slide(BLANK); bg(s)
rect(s, 0, 0, SW, Inches(0.08), GREEN)
rect(s, 0, SH-Inches(0.08), SW, Inches(0.08), ACCENT)
rrect(s, Inches(5.4), Inches(1.0), Inches(2.5), Inches(2.5), ACCENT)
text(s, Inches(5.4), Inches(1.0), Inches(2.5), Inches(2.5), "⚡", size=120, bold=True, color=BG, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
text(s, Inches(0.6), Inches(3.9), SW-Inches(1.2), Inches(1.0),
     "Let Agents Orchestrate the Renewable Transition.",
     size=44, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
text(s, Inches(0.6), Inches(5.0), SW-Inches(1.2), Inches(0.6),
     "71% cost cut  ·  153 t CO₂ avoided per day  ·  zero critical outages  ·  works fully offline",
     size=18, color=ACCENT, align=PP_ALIGN.CENTER)
# Single thank-you
text(s, Inches(0.6), Inches(6.0), SW-Inches(1.2), Inches(0.6),
     "Thank you.",
     size=30, bold=True, color=GREEN, align=PP_ALIGN.CENTER)
text(s, Inches(0.6), Inches(6.6), SW-Inches(1.2), Inches(0.4),
     "ET × Accenture AI Hackathon — Agentic Edition  ·  Problem 4: Renewable Energy Grid Orchestration",
     size=12, color=TEXT_DIM, align=PP_ALIGN.CENTER)

out = "/home/user/energy_orchestrator/submission/Renewable_Energy_Orchestrator_Pitch.pptx"
prs.save(out)
print(f"Wrote {out}")
