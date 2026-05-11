/* LearnPilot — Frontend Logic
   Team: Priyanshu & Kashif
   Course: CSC 603/803 Generative AI Capstone
*/

// ─── Backend URL ──────────────────────────────────────────────────────────────
// Automatically points to the right backend depending on where the app is running.
//
//  Local dev (file:// or localhost) → uses http://127.0.0.1:8000  (Brosil's server)
//  Deployed (GitHub Pages etc.)     → set BACKEND_URL to the Railway/Render URL
//
//  HOW TO DEPLOY:
//  1. Brosil deploys backend to Railway and gets a URL like:
//       https://learnpilot-backend.up.railway.app
//  2. Paste that URL into BACKEND_URL below (keep the quotes)
//  3. Push to GitHub — done, works everywhere
// ─────────────────────────────────────────────────────────────────────────────
const BACKEND_URL = ''   // <- paste deployed backend URL here when ready

const isLocal = window.location.hostname === 'localhost'
             || window.location.hostname === '127.0.0.1'
             || window.location.protocol === 'file:'

const API = BACKEND_URL || (isLocal ? 'http://127.0.0.1:8000' : '')
let currentMode   = 'Concept-First Learning'
let history       = []
let activePdfId   = null
let activePdfName = ''

// Session context for feature buttons
let currentSessionTopic    = ''
let currentSessionMode     = ''
let currentSessionContexts = []
let currentSessionRawData  = null

// Chunked learning state
let learningPlan    = []
let currentChunk    = 0
let currentTopic    = ''
let chunkResponses  = {}

// New feature state
let currentFormat    = 'text'          // Idea 7 — teaching format
let precheckLevel    = null            // Idea 2 — knowledge level
let pendingTopic     = null            // held while precheck modal open
let timerInterval    = null            // Idea 8 — study timer
let timerTotal       = 0
let timerRemaining   = 0
let timerPaused      = false
let breakInterval    = null
let breakRemaining   = 0
let compareMode      = false           // Ideas 4/5 — compare view
let compareHistory   = {}             // {index: responseData}

loadPdfList()
mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  suppressErrorRendering: true,
  flowchart: {
    useMaxWidth: true,
    htmlLabels: true,
    curve: 'basis',
    nodeSpacing: 50,
    rankSpacing: 70,
  },
  themeVariables: {
    background: '#1a1e26',
    primaryColor: '#253050',
    primaryBorderColor: '#4a5a8a',
    primaryTextColor: '#e8eaf0',
    secondaryColor: '#1a2035',
    tertiaryColor: '#1a1e26',
    lineColor: '#6c8fff',
    edgeLabelBackground: '#1a1e26',
    fontSize: '14px',
    fontFamily: 'DM Sans, sans-serif',
    nodeBorder: '#4a5a8a',
    clusterBkg: '#1a2035',
    titleColor: '#e8eaf0',
    nodeTextColor: '#e8eaf0',
  }
})

function selectMode(btn) {
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'))
  btn.classList.add('active')
  currentMode = btn.dataset.mode
  const icons = { 'Concept-First Learning':'📖', 'Reverse Engineering':'🔬', 'Visual Learning':'🗺️' }
  document.getElementById('mode-pill-text').textContent = `${icons[currentMode]} ${currentMode}`
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() }
}

function autoResize(el) {
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 140) + 'px'
}

function tryExample(topic) {
  document.getElementById('topic-input').value = topic
  submit()
}

async function submit() {
  const input = document.getElementById('topic-input')
  const topic = input.value.trim()
  if (!topic) return

  // Idea 2 — show pre-assessment if first time for this topic
  if (precheckLevel === null) {
    pendingTopic = topic
    document.getElementById('precheck-sub').textContent =
      `Before diving into "${topic}", let us know your starting point.`
    document.getElementById('precheck-overlay').classList.add('open')
    return
  }

  const btn = document.getElementById('submit-btn')
  btn.disabled = true
  btn.innerHTML = '<span>Generating...</span>'

  document.getElementById('empty-state').style.display = 'none'
  const container = document.getElementById('response-container')
  container.style.display = 'block'

  container.innerHTML = `
    <div class="loading">
      <div class="loading-dots">
        <div class="dot"></div><div class="dot"></div><div class="dot"></div>
      </div>
      <div class="loading-text">Searching sources & generating explanation...</div>
    </div>`

  try {
    // Detect chapter reference from input or topic text
    const chapterEl  = document.getElementById('chapter-input')
    const chapterRef = (chapterEl && chapterEl.value ? chapterEl.value.trim() : '') ||
                       ((topic.match(/chapter\s*\d+/i) || [])[0] || '')

    // If PDF active + chapter detected → use chunked learning
    if (activePdfId && chapterRef && /chapter\s*\d+/i.test(chapterRef)) {
      currentTopic = topic
      input.value  = ''
      input.style.height = 'auto'
      btn.disabled = false
      btn.innerHTML = '<span>Generate</span><span>→</span>'
      await startChunkedLearning(topic, chapterRef)
      return
    }

    // Normal generate (no PDF or no chapter ref)
    const res = await fetch(`${API}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        topic,
        mode: currentMode,
        code_snippet: null,
        pdf_id: activePdfId || null,
        chapter_ref: chapterRef || null,
      })
    })

    if (!res.ok) throw new Error(`Server error: ${res.status}`)
    const data = await res.json()

    renderResponse(topic, data)
    addToHistory(topic, currentMode)
    input.value = ''
    input.style.height = 'auto'

  } catch (err) {
    container.innerHTML = `
      <div class="error-box">
        The backend server is not connected. Please try again later.
      </div>`
  }

  btn.disabled = false
  btn.innerHTML = '<span>Generate</span><span>→</span>'
}

function renderResponse(topic, data) {
  const container = document.getElementById('response-container')

  const modeColors = {
    'Concept-First Learning': 'tag-concept',
    'Reverse Engineering':    'tag-reverse',
    'Visual Learning':        'tag-visual'
  }

  const stepsHtml = (data.steps || []).map(s => `
    <div class="step-item">
      <div class="step-dot"></div>
      <div>${renderInlineMd(s)}</div>
    </div>`).join('')

  // Strip leaked system prompt content and Real World section from raw markdown
  const rawCleaned = (data.raw || data.explanation || '')
    .replace(/## Real World Applications[\s\S]*?(?=## |$)/g, '')
    .replace(/Give a concrete, relevant example that matches the subject:[\s\S]*?Match the example to the subject\.?\n*/g, '')
    .replace(/Biology\/Nature topic[^\n]*\n/g, '')
    .replace(/History\/Social topic[^\n]*\n/g, '')
    .replace(/Math\/Physics topic[^\n]*\n/g, '')
    .replace(/Programming\/CS topic[^\n]*\n/g, '')
    .replace(/Language\/Arts topic[^\n]*\n/g, '')
    .replace(/One clear question that tests genuine understanding[^\n]*\n/g, '')
    .replace(/Format exactly as:[^\n]*\n/g, '')
    .replace(/Show exactly where this concept[^\n]*\n/g, '')
    .replace(/Give 3-5 specific[^\n]*\n/g, '')
    .replace(/Explain the core idea[^\n]*\n/g, '')
    .replace(/Go deeper\. Explain[^\n]*\n/g, '')
    .replace(/Introduce one more advanced[^\n]*\n/g, '')
    .replace(/Give ONE concrete example[^\n]*\n/g, '')
    .replace(/\[Write the[^\]]*\]\n*/g, '')
    .replace(/\[Write [^\]]*\]\n*/g, '')
    .trim()
  const rawHtml = renderMarkdown(rawCleaned)

  const realWorldHtml = data.real_world
    ? `<div class="realworld-box">
        <div class="realworld-label">🌍 Real World Applications</div>
        <div class="md-body">${renderMarkdown(data.real_world)}</div>
       </div>`
    : ''

  // Store session context for features
  currentSessionTopic    = topic
  currentSessionMode     = data.mode
  currentSessionContexts = [data.raw || '']
  currentSessionRawData  = data

  container.innerHTML = `
    <div class="response-card" id="main-response-card">
      <div class="response-header">
        <div class="response-meta">
          <div class="response-topic">${escHtml(topic)}</div>
          <span class="mode-tag ${modeColors[data.mode] || 'tag-concept'}">${data.mode}</span>
        </div>
      </div>
      <div class="response-body">
        <div class="response-content">
          <div class="md-body" id="md-output">${rawHtml}</div>
        </div>
        <div class="steps-panel">
          <div class="steps-title">Summary</div>
          ${stepsHtml}
        </div>
      </div>
      ${realWorldHtml}
      ${data.exercise ? `<div class="exercise-box">
        <div class="exercise-label">Practice</div>
        <div class="exercise-text">${escHtml(data.exercise)}</div>
      </div>` : ''}
      <div class="action-bar">
        <button class="action-btn" onclick="doMoreContext(this)">
          <span class="btn-icon">➕</span> More Context
        </button>
        <button class="action-btn" onclick="doQuiz(this)">
          <span class="btn-icon">🧠</span> Quizlet
        </button>
        <button class="action-btn" onclick="doExercises(this)">
          <span class="btn-icon">✏️</span> Exercise Questions
        </button>
        <button class="action-btn" onclick="doRelatedLinks(this)">
          <span class="btn-icon">🔗</span> Related Links
        </button>
      </div>
      <div class="exam-trigger" onclick="doExam(this)">
        🎓 <strong>Final Assessment</strong> — Test everything you've learned in this session
      </div>
      <div id="features-container"></div>
      <div class="export-bar">
        <span class="export-label">Export</span>
        <button class="export-btn" onclick="exportMarkdown()">📄 Markdown</button>
        <button class="export-btn" onclick="exportPDF()">🖨️ Print / PDF</button>
        <button class="export-btn" onclick="copyToClipboard()">📋 Copy text</button>
      </div>
    </div>`

  renderMermaidBlocks()
}

function renderMarkdown(raw) {
  if (!raw) return ''
  const parts = raw.split(/(```mermaid[\s\S]*?```)/g)
  return parts.map((part, i) => {
    if (part.startsWith('```mermaid')) {
      const code = part.replace(/^```mermaid\n?/, '').replace(/```$/, '').trim()
      const id = `mermaid-${Date.now()}-${i}`
      return `<div class="mermaid-wrapper"><div class="mermaid" id="${id}">${escHtml(code)}</div></div>`
    }
    return marked.parse(part)
  }).join('')
}

function renderInlineMd(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
}

function escHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')
}

function cleanMermaidCode(raw) {
  let code = raw
    .replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"')
    .replace(/-->\|([^|]*)\|>/g, '-->|$1|')
    .replace(/---\|([^|]*)\|>/g, '---|$1|')
    .trim()
  // If the model put everything on one line, split at node transitions
  if (!code.includes('\n')) {
    code = code
      .replace(/(\s+)(graph |flowchart |sequenceDiagram|classDiagram|stateDiagram|timeline|mindmap|gantt|pie)/g, '\n$2')
      .replace(/\s+(A\[|B\[|C\[|D\[|E\[|F\[|G\[|H\[)/g, '\n    $1')
      .replace(/([A-Z]\])\s+-->/g, '$1\n    -->')
      .replace(/-->\s+([A-Z]\[)/g, '-->\n    $1')
  }
  return code
}

function makeFallbackDiagram(rawCode) {
  // Parse node labels from mermaid code and render as a pretty HTML flow diagram
  const nodePattern = /[A-Za-z0-9]+\[([^\]]+)\]/g
  const nodes = []
  let m
  while ((m = nodePattern.exec(rawCode)) !== null) {
    if (!nodes.includes(m[1])) nodes.push(m[1])
  }
  if (nodes.length < 2) {
    return '<pre style="font-size:12px;color:var(--text3);padding:12px;overflow-x:auto;white-space:pre-wrap;">' + rawCode.replace(/</g,'&lt;') + '</pre>'
  }
  const items = nodes.slice(0,8).map((label, i) => `
    <div style="display:flex;flex-direction:column;align-items:center;gap:6px;">
      <div style="background:rgba(108,143,255,0.12);border:1px solid rgba(108,143,255,0.3);border-radius:8px;padding:8px 14px;font-size:12px;font-weight:500;color:#6c8fff;text-align:center;max-width:120px;line-height:1.3;">${label}</div>
      ${i < nodes.slice(0,8).length - 1 ? '<div style="font-size:16px;color:var(--text3);">↓</div>' : ''}
    </div>`).join('')
  return `<div style="display:flex;flex-direction:column;align-items:center;gap:0;padding:8px 0;">${items}</div>`
}

async function renderMermaidBlocks() {
  await new Promise(r => setTimeout(r, 120))
  const blocks = document.querySelectorAll('.mermaid:not([data-processed])')
  for (const block of blocks) {
    block.setAttribute('data-processed', 'true')
    const rawCode = cleanMermaidCode(block.textContent)
    const uid = 'mg' + Date.now() + Math.random().toString(36).slice(2,6)
    const wrapper = block.closest('.mermaid-wrapper')
    try {
      const { svg } = await mermaid.render(uid, rawCode)
      block.innerHTML = svg
      // Keep SVG at natural rendered size — just cap at container width
      const svgEl = block.querySelector('svg')
      if (svgEl) {
        svgEl.removeAttribute('width')
        svgEl.removeAttribute('height')
        svgEl.style.maxWidth = '100%'
        svgEl.style.height = 'auto'
        svgEl.style.overflow = 'visible'
      }
    } catch(e) {
      if (wrapper) {
        wrapper.innerHTML = makeFallbackDiagram(rawCode)
      }
    }
  }
}

async function startChunkedLearning(topic, chapterRef) {
  const container = document.getElementById('response-container')
  document.getElementById('empty-state').style.display = 'none'
  container.style.display = 'block'
  container.innerHTML = `
    <div class="loading">
      <div class="loading-dots"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>
      <div class="loading-text">Building your learning plan for ${chapterRef}...</div>
    </div>`

  try {
    // Step 1: Get learning plan
    const planRes = await fetch(`${API}/plan`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({pdf_id: activePdfId, chapter_ref: chapterRef})
    })
    if (!planRes.ok) throw new Error('Could not build learning plan')
    const plan = await planRes.json()

    if (!plan.subtopics || plan.subtopics.length === 0) {
      throw new Error('No subtopics found in this chapter')
    }

    // Reset chunked state
    learningPlan   = plan.subtopics
    currentChunk   = 0
    currentTopic   = topic
    chunkResponses = {}

    // Step 2: Teach first chunk
    await teachChunk(0)

  } catch(err) {
    container.innerHTML = `<div class="error-box">The backend server is not connected. Please try again later.</div>`
  }
}

async function teachChunk(index) {
  if (index < 0 || index >= learningPlan.length) return

  currentChunk = index
  const chunk  = learningPlan[index]
  const container = document.getElementById('response-container')

  // Show from cache if available
  if (chunkResponses[index]) {
    renderChunkResponse(chunkResponses[index], index)
    return
  }

  container.innerHTML = `
    <div class="loading">
      <div class="loading-dots"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>
      <div class="loading-text">Teaching: ${chunk.title}...</div>
    </div>`

  try {
    const res = await fetch(`${API}/generate-chunk`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        topic:        currentTopic,
        mode:         currentMode,
        pdf_id:       activePdfId,
        page_start:   chunk.page_start,
        page_end:     chunk.page_end,
        chunk_title:  chunk.title,
        chunk_index:  index,
        total_chunks: learningPlan.length,
      })
    })
    if (!res.ok) throw new Error(`Server error: ${res.status}`)
    const data = await res.json()

    // Cache the response
    chunkResponses[index] = data
    renderChunkResponse(data, index)
    addToHistory(`${currentTopic} [${chunk.title}]`, currentMode)

  } catch(err) {
    container.innerHTML = `<div class="error-box">The backend server is not connected. Please try again later.</div>`
  }
}

function renderChunkResponse(data, index) {
  const container = document.getElementById('response-container')
  const chunk     = learningPlan[index]
  const total     = learningPlan.length

  // Build plan progress bar
  const planSteps = learningPlan.map((s, i) => {
    const cls = i < index ? 'plan-step done' : i === index ? 'plan-step active' : 'plan-step'
    const icon = i < index ? '✓ ' : ''
    return `<span class="${cls}" onclick="teachChunk(${i})">${icon}${s.section}</span>`
  }).join('')

  const modeColors = {
    'Concept-First Learning': 'tag-concept',
    'Reverse Engineering':    'tag-reverse',
    'Visual Learning':        'tag-visual'
  }

  const stepsHtml = (data.steps || []).map(s => `
    <div class="step-item">
      <div class="step-dot"></div>
      <div>${renderInlineMd(s)}</div>
    </div>`).join('')

  const rawCleaned = (data.raw || data.explanation || '')
    .replace(/## Real World Applications[\s\S]*?(?=## |$)/g, '')
    .replace(/Give a concrete, relevant example that matches the subject:[\s\S]*?Match the example to the subject\.?\n*/g, '')
    .replace(/Biology\/Nature topic[^\n]*\n/g, '')
    .replace(/History\/Social topic[^\n]*\n/g, '')
    .replace(/Math\/Physics topic[^\n]*\n/g, '')
    .replace(/Programming\/CS topic[^\n]*\n/g, '')
    .replace(/Language\/Arts topic[^\n]*\n/g, '')
    .replace(/One clear question that tests genuine understanding[^\n]*\n/g, '')
    .replace(/Format exactly as:[^\n]*\n/g, '')
    .replace(/Show exactly where this concept[^\n]*\n/g, '')
    .replace(/Give 3-5 specific[^\n]*\n/g, '')
    .replace(/Explain the core idea[^\n]*\n/g, '')
    .replace(/Go deeper\. Explain[^\n]*\n/g, '')
    .replace(/Introduce one more advanced[^\n]*\n/g, '')
    .replace(/Give ONE concrete example[^\n]*\n/g, '')
    .replace(/\[Write the[^\]]*\]\n*/g, '')
    .replace(/\[Write [^\]]*\]\n*/g, '')
    .trim()
  const rawHtml = renderMarkdown(rawCleaned)

  const realWorldHtml = data.real_world
    ? `<div class="realworld-box">
        <div class="realworld-label">🌍 Real World Applications</div>
        <div class="md-body">${renderMarkdown(data.real_world)}</div>
       </div>` : ''

  // Nav buttons
  const prevDisabled = index === 0 ? 'disabled' : ''
  const navHtml = index < total - 1
    ? `<button class="prev-btn" onclick="teachChunk(${index-1})" ${prevDisabled}>← Previous</button>
       <span class="chunk-progress">Part <strong>${index+1}</strong> of <strong>${total}</strong></span>
       <button class="next-btn" onclick="teachChunk(${index+1})">Next → <small>${learningPlan[index+1]?.section || ''}</small></button>`
    : `<button class="prev-btn" onclick="teachChunk(${index-1})" ${prevDisabled}>← Previous</button>
       <span class="chunk-progress">Part <strong>${index+1}</strong> of <strong>${total}</strong></span>
       <span class="complete-badge">✓ Chapter Complete!</span>`

  container.innerHTML = `
    <div class="plan-bar">
      <span class="plan-title">Learning Plan</span>
      <div class="plan-steps">${planSteps}</div>
    </div>
    <div class="response-card">
      <div class="response-header">
        <div class="response-meta">
          <div class="response-topic">${escHtml(chunk.title)}</div>
          <span class="mode-tag ${modeColors[data.mode] || 'tag-concept'}">${data.mode}</span>
        </div>
      </div>
      <div class="response-body">
        <div class="response-content">
          <div class="md-body">${rawHtml}</div>
        </div>
        <div class="steps-panel">
          <div class="steps-title">Summary</div>
          ${stepsHtml}
        </div>
      </div>
      ${realWorldHtml}
      ${data.exercise ? `<div class="exercise-box">
        <div class="exercise-label">Practice</div>
        <div class="exercise-text">${escHtml(data.exercise)}</div>
      </div>` : ''}
      <div class="chunk-nav">${navHtml}</div>
    </div>`

  renderMermaidBlocks()
}

// ── Feature Button Functions ──────────────────────────────────────────────────

function getFeatureContainer() {
  return document.getElementById('features-container')
}

function setActionBtnLoading(btn, loading, label) {
  btn.disabled = loading
  if (loading) {
    btn.classList.add('loading')
    btn.innerHTML = `<span class="btn-icon">⏳</span> Loading...`
  } else {
    btn.classList.remove('loading')
    btn.innerHTML = label
  }
}

// ── More Context ──────────────────────────────────────────────────────────────
async function doMoreContext(btn) {
  setActionBtnLoading(btn, true, '')
  const fc = getFeatureContainer()

  // Show loading in panel
  const panelId = 'more-ctx-' + Date.now()
  const loadDiv = document.createElement('div')
  loadDiv.className = 'feature-panel'
  loadDiv.id = panelId
  loadDiv.innerHTML = `
    <div class="feature-panel-header">
      <div class="feature-panel-title">➕ Additional Context</div>
    </div>
    <div class="feature-panel-body">
      <div class="panel-loading">
        <div class="dot"></div><div class="dot" style="animation-delay:0.2s"></div><div class="dot" style="animation-delay:0.4s"></div>
        <span>Generating additional context...</span>
      </div>
    </div>`
  fc.appendChild(loadDiv)

  try {
    const res = await fetch(`${API}/more-context`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        topic:           currentSessionTopic,
        mode:            currentSessionMode,
        already_covered: currentSessionContexts,
        rag_context:     '',
      })
    })
    const data = await res.json()

    // Add to accumulated contexts
    if (data.raw) currentSessionContexts.push(data.raw)

    const panel = document.getElementById(panelId)
    const cleanRaw = (data.raw || '').replace(/## Real World Applications[\s\S]*?(?=## |$)/g,'').trim()
    const realW = data.real_world ? `
      <div class="realworld-box" style="margin-top:12px;">
        <div class="realworld-label">🌍 Real World Applications</div>
        <div class="md-body">${renderMarkdown(data.real_world)}</div>
      </div>` : ''

    panel.innerHTML = `
      <div class="feature-panel-header">
        <div class="feature-panel-title">➕ Additional Context — ${escHtml(data.title || 'More Detail')}</div>
      </div>
      <div class="feature-panel-body">
        <div class="md-body">${renderMarkdown(cleanRaw)}</div>
        ${realW}
      </div>`

    renderMermaidBlocks()
  } catch(e) {
    document.getElementById(panelId).innerHTML = `<div class="error-box">The backend server is not connected. Please try again later.</div>`
  }

  setActionBtnLoading(btn, false, '<span class="btn-icon">➕</span> More Context')
}

// ── Quiz ──────────────────────────────────────────────────────────────────────
async function doQuiz(btn) {
  setActionBtnLoading(btn, true, '')
  const fc = getFeatureContainer()
  const panelId = 'quiz-' + Date.now()

  const loadDiv = document.createElement('div')
  loadDiv.className = 'feature-panel'
  loadDiv.id = panelId
  loadDiv.innerHTML = `
    <div class="feature-panel-header">
      <div class="feature-panel-title">🧠 Quizlet</div>
    </div>
    <div class="feature-panel-body">
      <div class="panel-loading">
        <div class="dot"></div><div class="dot" style="animation-delay:0.2s"></div><div class="dot" style="animation-delay:0.4s"></div>
        <span>Generating quiz questions based on ${currentSessionContexts.length} context(s)...</span>
      </div>
    </div>`
  fc.appendChild(loadDiv)

  try {
    const res = await fetch(`${API}/quiz`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        topic:        currentSessionTopic,
        all_contexts: currentSessionContexts,
        num_questions: 5,
      })
    })
    const data = await res.json()

    let score = 0
    let answered = 0
    const total = (data.questions || []).length

    const questionsHtml = (data.questions || []).map((q, qi) => {
      const opts = (q.options || []).map((opt, oi) => {
        const letter = opt.charAt(0)
        return `<div class="quiz-option" onclick="answerQuiz(this, '${letter}', '${q.correct}', 'quiz-exp-${panelId}-${qi}', 'quiz-score-${panelId}')" data-letter="${letter}">
          ${escHtml(opt)}
        </div>`
      }).join('')

      return `<div class="quiz-question">
        <div class="quiz-q-text">${qi+1}. ${escHtml(q.question)}</div>
        <div class="quiz-options" id="quiz-opts-${panelId}-${qi}">${opts}</div>
        <div class="quiz-explanation" id="quiz-exp-${panelId}-${qi}">${escHtml(q.explanation || '')}</div>
      </div>`
    }).join('')

    document.getElementById(panelId).innerHTML = `
      <div class="feature-panel-header">
        <div class="feature-panel-title">🧠 Quizlet — ${total} Questions</div>
        <span style="font-size:12px;color:var(--text3)">Based on ${currentSessionContexts.length} context(s)</span>
      </div>
      <div class="feature-panel-body">
        <div class="quiz-score" id="quiz-score-${panelId}">Answer the questions to see your score</div>
        ${questionsHtml || '<div style="color:var(--text3)">No questions generated. Try adding more context first.</div>'}
      </div>`

    window['quizState_' + panelId] = { score: 0, answered: 0, total }

  } catch(e) {
    document.getElementById(panelId).innerHTML = `<div class="error-box">The backend server is not connected. Please try again later.</div>`
  }

  setActionBtnLoading(btn, false, '<span class="btn-icon">🧠</span> Quizlet')
}

function answerQuiz(optEl, chosen, correct, expId, scoreId) {
  const optsContainer = optEl.parentElement
  if (optsContainer.dataset.answered) return  // already answered

  optsContainer.dataset.answered = '1'
  Array.from(optsContainer.children).forEach(o => {
    o.classList.add('revealed')
    if (o.dataset.letter === correct) o.classList.add('correct')
    else if (o.dataset.letter === chosen && chosen !== correct) o.classList.add('wrong')
  })

  // Show explanation
  const exp = document.getElementById(expId)
  if (exp) exp.style.display = 'block'

  // Update score
  const scoreEl = document.getElementById(scoreId)
  if (scoreEl) {
    // Count answered questions
    const card = scoreEl.closest('.feature-panel-body')
    const allOpts = card.querySelectorAll('.quiz-options[data-answered]')
    const correct_count = card.querySelectorAll('.quiz-option.correct.revealed').length - card.querySelectorAll('.quiz-option.correct.wrong').length
    // Simpler: count green ones the user selected
    const userCorrect = card.querySelectorAll('.quiz-option.correct:not(.wrong)').length
    const totalQ = card.querySelectorAll('.quiz-question').length
    const answeredQ = allOpts.length
    scoreEl.textContent = `${answeredQ} of ${totalQ} answered`
  }
}

// ── Exercises ─────────────────────────────────────────────────────────────────
async function doExercises(btn) {
  setActionBtnLoading(btn, true, '')
  const fc = getFeatureContainer()
  const panelId = 'ex-' + Date.now()

  const loadDiv = document.createElement('div')
  loadDiv.className = 'feature-panel'
  loadDiv.id = panelId
  loadDiv.innerHTML = `
    <div class="feature-panel-header">
      <div class="feature-panel-title">✏️ Exercise Questions</div>
    </div>
    <div class="feature-panel-body">
      <div class="panel-loading">
        <div class="dot"></div><div class="dot" style="animation-delay:0.2s"></div><div class="dot" style="animation-delay:0.4s"></div>
        <span>Generating exercises based on ${currentSessionContexts.length} context(s)...</span>
      </div>
    </div>`
  fc.appendChild(loadDiv)

  try {
    const res = await fetch(`${API}/exercises`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        topic:         currentSessionTopic,
        all_contexts:  currentSessionContexts,
        num_questions: 4,
      })
    })
    const data = await res.json()

    const exercisesHtml = (data.exercises || []).map((ex, i) => `
      <div class="exercise-item">
        <div class="exercise-type">${ex.type || 'exercise'}</div>
        <div class="exercise-q-text">${i+1}. ${escHtml(ex.question)}</div>
        ${ex.hint ? `<div class="exercise-hint">💡 Hint: ${escHtml(ex.hint)}</div>` : ''}
        <button class="show-answer-btn" onclick="toggleAnswer(this)">Show sample answer</button>
        <div class="exercise-answer">${escHtml(ex.sample_answer || '')}</div>
      </div>`).join('')

    document.getElementById(panelId).innerHTML = `
      <div class="feature-panel-header">
        <div class="feature-panel-title">✏️ Exercise Questions</div>
        <span style="font-size:12px;color:var(--text3)">Based on ${currentSessionContexts.length} context(s)</span>
      </div>
      <div class="feature-panel-body">
        ${exercisesHtml || '<div style="color:var(--text3)">No exercises generated. Try adding more context first.</div>'}
      </div>`

  } catch(e) {
    document.getElementById(panelId).innerHTML = `<div class="error-box">The backend server is not connected. Please try again later.</div>`
  }

  setActionBtnLoading(btn, false, '<span class="btn-icon">✏️</span> Exercise Questions')
}

function toggleAnswer(btn) {
  const ans = btn.nextElementSibling
  if (ans.style.display === 'block') {
    ans.style.display = 'none'
    btn.textContent = 'Show sample answer'
  } else {
    ans.style.display = 'block'
    btn.textContent = 'Hide answer'
  }
}

// ── Related Links ─────────────────────────────────────────────────────────────
async function doRelatedLinks(btn) {
  setActionBtnLoading(btn, true, '')
  const fc = getFeatureContainer()
  const panelId = 'links-' + Date.now()

  const loadDiv = document.createElement('div')
  loadDiv.className = 'feature-panel'
  loadDiv.id = panelId
  loadDiv.innerHTML = `
    <div class="feature-panel-header">
      <div class="feature-panel-title">🔗 Related Links</div>
    </div>
    <div class="feature-panel-body">
      <div class="panel-loading">
        <div class="dot"></div><div class="dot" style="animation-delay:0.2s"></div><div class="dot" style="animation-delay:0.4s"></div>
        <span>Fetching helpful resources...</span>
      </div>
    </div>`
  fc.appendChild(loadDiv)

  try {
    const res = await fetch(`${API}/related-links`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ topic: currentSessionTopic })
    })
    const data = await res.json()

    const linksHtml = (data.links || []).map(link => `
      <a href="${link.url}" target="_blank" rel="noopener noreferrer" class="link-item">
        <div class="link-icon">${link.icon || '🔗'}</div>
        <div class="link-info">
          <div class="link-title">${escHtml(link.title)}</div>
          <div class="link-desc">${escHtml(link.description || '')}</div>
        </div>
        <div class="link-source">${escHtml(link.source || '')}</div>
      </a>`).join('')

    document.getElementById(panelId).innerHTML = `
      <div class="feature-panel-header">
        <div class="feature-panel-title">🔗 Related Links</div>
      </div>
      <div class="feature-panel-body">
        ${linksHtml || '<div style="color:var(--text3)">No links found for this topic.</div>'}
      </div>`

  } catch(e) {
    document.getElementById(panelId).innerHTML = `<div class="error-box">The backend server is not connected. Please try again later.</div>`
  }

  setActionBtnLoading(btn, false, '<span class="btn-icon">🔗</span> Related Links')
}

async function uploadPDF(input) {
  const file = input.files[0]
  if (!file) return
  const status = document.getElementById('upload-status')
  const label  = document.getElementById('upload-label')
  status.textContent = 'Uploading...'
  label.textContent  = 'Uploading...'
  try {
    const formData = new FormData()
    formData.append('file', file)
    const res  = await fetch(`${API}/upload`, { method: 'POST', body: formData })
    const data = await res.json()
    if (data.success) {
      status.textContent = `✓ ${data.name} (${data.pages} pages)`
      status.style.color = 'var(--green)'
      label.textContent  = 'Upload another PDF'
      // Auto-select the newly uploaded PDF
      selectPdf(data.file_id, data.name)
      loadPdfList()
    } else {
      status.textContent = 'Upload failed'
      status.style.color = '#f87171'
      label.textContent  = 'Upload PDF resource'
    }
  } catch(e) {
    status.textContent = 'Upload error — is server running?'
    status.style.color = '#f87171'
    label.textContent  = 'Upload PDF resource'
  }
  input.value = ''
}

async function loadPdfList() {
  try {
    const res   = await fetch(`${API}/files`)
    const files = await res.json()
    const list  = document.getElementById('pdf-list')
    if (!files.length) { list.innerHTML = ''; return }
    list.innerHTML = files.map(f => `
      <div style="display:flex;align-items:center;gap:6px;padding:5px 8px;border-radius:6px;background:${activePdfId===f.id?'rgba(74,222,128,0.1)':'transparent'};cursor:pointer;margin-bottom:2px;"
           onclick="selectPdf('${f.id}','${f.name.replace(/'/g,"\\'")}')">
        <span style="font-size:12px;">📄</span>
        <span style="font-size:11px;color:${activePdfId===f.id?'var(--green)':'var(--text2)'};flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${f.name}</span>
        <span style="font-size:10px;color:var(--text3);">${f.pages}p</span>
        <button onclick="event.stopPropagation();deletePdf('${f.id}')" style="background:none;border:none;color:var(--text3);cursor:pointer;font-size:11px;padding:0 2px;">✕</button>
      </div>`).join('')
  } catch(e) {}
}

function selectPdf(id, name) {
  activePdfId   = id
  activePdfName = name
  const row     = document.getElementById('pdf-context-row')
  const nameEl  = document.getElementById('active-pdf-name')
  row.style.display  = 'flex'
  nameEl.textContent = name.length > 20 ? name.slice(0,20)+'...' : name
  loadPdfList()
}

function clearPdfContext() {
  activePdfId   = null
  activePdfName = ''
  document.getElementById('pdf-context-row').style.display = 'none'
  document.getElementById('chapter-input').value = ''
  loadPdfList()
}

async function deletePdf(id) {
  await fetch(`${API}/files/${id}`, { method: 'DELETE' })
  if (activePdfId === id) clearPdfContext()
  loadPdfList()
}

function addToHistory(topic, mode) {
  history.unshift({ topic, mode })
  if (history.length > 20) history.pop()
  renderHistory()
}

function renderHistory() {
  const list = document.getElementById('history-list')
  if (!history.length) {
    list.innerHTML = '<div style="font-size:12px;color:var(--text3);padding:8px 10px;">No history yet</div>'
    return
  }
  const icons = { 'Concept-First Learning':'📖', 'Reverse Engineering':'🔬', 'Visual Learning':'🗺️' }
  list.innerHTML = history.map(h => `
    <div class="history-item" onclick="tryExample('${escHtml(h.topic)}')">
      <div class="history-topic">${escHtml(h.topic)}</div>
      <div class="history-mode">${icons[h.mode] || ''} ${h.mode}</div>
    </div>`).join('')
}
// ══════════════════════════════════════════════════════
// IDEA 7 — Teaching Format Selector
// ══════════════════════════════════════════════════════
function selectFormat(btn) {
  const fmt = btn.dataset.fmt
  if (fmt !== 'text') {
    // Coming soon — show a brief visual cue
    btn.style.animation = 'none'
    btn.textContent = '🚧 Coming soon!'
    setTimeout(() => {
      btn.innerHTML = btn.dataset.fmt === 'visual' ? '🖼️ Image <span class="format-badge">SOON</span>'
        : btn.dataset.fmt === 'video' ? '🎬 Video <span class="format-badge">SOON</span>'
        : '🧊 3D <span class="format-badge">SOON</span>'
    }, 1400)
    return
  }
  document.querySelectorAll('.format-btn').forEach(b => b.classList.remove('active'))
  btn.classList.add('active')
  currentFormat = fmt
}

// ══════════════════════════════════════════════════════
// IDEA 2 — Pre-Assessment / Knowledge Check
// ══════════════════════════════════════════════════════
function selectPrecheck(el, level) {
  document.querySelectorAll('.precheck-opt').forEach(o => o.classList.remove('selected'))
  el.classList.add('selected')
  precheckLevel = level
}

function closePrecheck(skipped) {
  document.getElementById('precheck-overlay').classList.remove('open')
  if (skipped) precheckLevel = 'skip'
  if (pendingTopic) {
    document.getElementById('topic-input').value = pendingTopic
    pendingTopic = null
    submit()
  }
}

// ══════════════════════════════════════════════════════
// IDEA 8 — Study Timer & Breaks
// ══════════════════════════════════════════════════════
function startTimer(minutes) {
  if (timerInterval) clearInterval(timerInterval)
  timerTotal     = minutes * 60
  timerRemaining = timerTotal
  timerPaused    = false
  document.getElementById('timer-bar').classList.add('active')
  document.getElementById('timer-label').textContent = `Study session (${minutes} min)`
  updateTimerDisplay()
  timerInterval = setInterval(tickTimer, 1000)
}

function tickTimer() {
  if (timerPaused) return
  timerRemaining--
  updateTimerDisplay()
  if (timerRemaining <= 0) {
    clearInterval(timerInterval)
    timerInterval = null
    document.getElementById('timer-bar').classList.remove('active')
    startBreak(5)
  }
}

function updateTimerDisplay() {
  const m = Math.floor(timerRemaining / 60)
  const s = timerRemaining % 60
  const str = `${m}:${s.toString().padStart(2,'0')}`
  const pct = (timerRemaining / timerTotal) * 100
  const disp = document.getElementById('timer-display')
  const fill = document.getElementById('timer-fill')
  disp.textContent = str
  fill.style.width = pct + '%'
  const warn = timerRemaining < 300  // last 5 min
  disp.className = 'timer-display' + (warn ? ' warning' : '')
  fill.className  = 'timer-fill'   + (warn ? ' warning' : '')
}

function pauseTimer() {
  timerPaused = !timerPaused
  document.getElementById('timer-pause-btn').textContent = timerPaused ? 'Resume' : 'Pause'
}

function stopTimer() {
  if (timerInterval) clearInterval(timerInterval)
  timerInterval = null
  document.getElementById('timer-bar').classList.remove('active')
}

function startBreak(minutes) {
  breakRemaining = minutes * 60
  document.getElementById('break-overlay').classList.add('open')
  updateBreakDisplay()
  breakInterval = setInterval(() => {
    breakRemaining--
    updateBreakDisplay()
    if (breakRemaining <= 0) endBreak()
  }, 1000)
}

function updateBreakDisplay() {
  const m = Math.floor(breakRemaining / 60)
  const s = breakRemaining % 60
  document.getElementById('break-timer-display').textContent = `${m}:${s.toString().padStart(2,'0')}`
}

function endBreak() {
  if (breakInterval) clearInterval(breakInterval)
  breakInterval = null
  document.getElementById('break-overlay').classList.remove('open')
  // reset precheck for next topic
  precheckLevel = null
}

// ══════════════════════════════════════════════════════
// IDEAS 4 & 5 — Compare Sessions
// ══════════════════════════════════════════════════════
function toggleCompareView() {
  compareMode = !compareMode
  const view    = document.getElementById('compare-view')
  const resArea = document.getElementById('response-area')
  const inputB  = document.getElementById('input-area-block')
  const btn     = document.getElementById('compare-toggle-btn')

  if (compareMode) {
    view.classList.add('open')
    resArea.style.display = 'none'
    inputB.style.display  = 'none'
    btn.classList.add('active')
    btn.textContent = '✕ Exit Compare'
    populateCompareSelects()
  } else {
    view.classList.remove('open')
    resArea.style.display = 'block'
    inputB.style.display  = 'block'
    btn.classList.remove('active')
    btn.textContent = '⇄ Compare Sessions'
  }
}

function populateCompareSelects() {
  const opts = history.map((h, i) =>
    `<option value="${i}">${h.topic.slice(0,32)}${h.topic.length>32?'…':''} · ${h.mode.split(' ')[0]}</option>`
  ).join('')
  const base = '<option value="">Select session</option>'
  document.getElementById('compare-select-left').innerHTML  = base + opts
  document.getElementById('compare-select-right').innerHTML = base + opts
}

function loadComparePane(side, idx) {
  const bodyId  = `compare-body-${side}`
  const topicId = `compare-topic-${side}`
  const body    = document.getElementById(bodyId)
  const topicEl = document.getElementById(topicId)

  if (idx === '') {
    topicEl.textContent = '—'
    body.innerHTML = '<div class="compare-empty"><div class="compare-empty-icon">📄</div><div>Select a session from history to compare</div></div>'
    return
  }

  const session = history[parseInt(idx)]
  if (!session) return
  topicEl.textContent = session.topic

  if (compareHistory[idx]) {
    body.innerHTML = `<div class="md-body">${renderMarkdown(compareHistory[idx].raw || compareHistory[idx].explanation || '')}</div>`
    renderMermaidBlocks()
    return
  }

  body.innerHTML = '<div class="panel-loading"><div class="dot"></div><span>Loading session...</span></div>'
  // Since history is in-memory (no persistent storage yet), show what we have
  body.innerHTML = `
    <div style="padding:12px 0;">
      <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.8px;color:var(--text3);margin-bottom:8px;">Topic</div>
      <div style="font-size:14px;color:var(--text);margin-bottom:16px;">${escHtml(session.topic)}</div>
      <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.8px;color:var(--text3);margin-bottom:8px;">Mode</div>
      <div style="font-size:13px;color:var(--text2);">${escHtml(session.mode)}</div>
      <div style="margin-top:16px;padding:12px;background:var(--bg3);border-radius:var(--radius-sm);font-size:12px;color:var(--text3);">
        Full response available when Brosil adds session persistence to the backend via <code>/history</code> endpoint returning raw content.
      </div>
    </div>`
}

// ══════════════════════════════════════════════════════
// IDEA 9 — Final Assessment / Exam
// ══════════════════════════════════════════════════════
async function doExam(trigger) {
  trigger.style.display = 'none'
  const fc = document.getElementById('features-container')
  const panelId = 'exam-' + Date.now()

  const loadDiv = document.createElement('div')
  loadDiv.className = 'exam-panel'
  loadDiv.id = panelId
  loadDiv.innerHTML = `
    <div class="exam-header">
      <div class="exam-title">🎓 Final Assessment — ${escHtml(currentSessionTopic)}</div>
    </div>
    <div class="exam-body">
      <div class="panel-loading">
        <div class="dot"></div><div class="dot" style="animation-delay:0.2s"></div><div class="dot" style="animation-delay:0.4s"></div>
        <span>Building your final exam from all session content...</span>
      </div>
    </div>`
  fc.appendChild(loadDiv)

  try {
    const res = await fetch(`${API}/exercises`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        topic: currentSessionTopic,
        all_contexts: currentSessionContexts,
        num_questions: 5,
      })
    })
    const data = await res.json()
    const questions = data.exercises || []

    const qsHtml = questions.map((q, i) => `
      <div class="exam-q">
        <div class="exam-q-num">Question ${i+1} · <span style="text-transform:capitalize;">${q.type || 'written'}</span></div>
        <div class="exam-q-text">${escHtml(q.question)}</div>
        ${q.hint ? `<div style="font-size:11px;color:var(--text3);font-style:italic;margin-bottom:8px;">💡 ${escHtml(q.hint)}</div>` : ''}
        <textarea class="exam-input" id="exam-ans-${i}" placeholder="Write your answer here…"></textarea>
        <div class="exam-result" id="exam-res-${i}">
          <strong style="color:var(--green);">Sample answer:</strong><br/>${escHtml(q.sample_answer || '')}
        </div>
        <button class="show-answer-btn" onclick="revealExamAnswer(${i})">Show model answer</button>
      </div>`).join('')

    document.getElementById(panelId).innerHTML = `
      <div class="exam-header">
        <div class="exam-title">🎓 Final Assessment — ${escHtml(currentSessionTopic)}</div>
        <span style="font-size:11px;color:var(--text3);">${questions.length} questions · Based on your full session</span>
      </div>
      <div class="exam-body">
        <div class="exam-score-bar">
          <div class="exam-score-num">${questions.length}</div>
          <div><div style="font-size:13px;font-weight:500;color:var(--text2);">Questions</div><div class="exam-score-label">Answer all, then check your work</div></div>
        </div>
        ${qsHtml}
      </div>`

  } catch(e) {
    document.getElementById(panelId).innerHTML =
      `<div class="error-box">The backend server is not connected. Please try again later.</div>`
  }
}

function revealExamAnswer(i) {
  const res = document.getElementById(`exam-res-${i}`)
  const btn = res.previousElementSibling
  if (res.style.display === 'block') {
    res.style.display = 'none'
    btn.textContent = 'Show model answer'
  } else {
    res.style.display = 'block'
    btn.textContent = 'Hide answer'
  }
}

// ══════════════════════════════════════════════════════
// IDEA 10 — Export / Preview Options
// ══════════════════════════════════════════════════════
function exportMarkdown() {
  if (!currentSessionRawData) return
  const md = `# ${currentSessionTopic}\n\n**Mode:** ${currentSessionMode}\n\n---\n\n${currentSessionRawData.raw || currentSessionRawData.explanation || ''}`
  const blob = new Blob([md], {type: 'text/markdown'})
  const a    = document.createElement('a')
  a.href     = URL.createObjectURL(blob)
  a.download = `${currentSessionTopic.replace(/[^a-z0-9]/gi,'_').toLowerCase()}_learnpilot.md`
  a.click()
}

function exportPDF() {
  window.print()
}

function copyToClipboard() {
  if (!currentSessionRawData) return
  const text = currentSessionRawData.raw || currentSessionRawData.explanation || ''
  navigator.clipboard.writeText(text).then(() => {
    const btns = document.querySelectorAll('.export-btn')
    btns.forEach(b => { if (b.textContent.includes('Copy')) { b.textContent = '✓ Copied!'; setTimeout(() => { b.innerHTML = '📋 Copy text' }, 1800) } })
  })
}