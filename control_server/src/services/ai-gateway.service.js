'use strict'

/**
 * AI Gateway — lớp DUY NHẤT trong hệ thống được biết provider/model/key.
 *
 * App gửi câu thoại thô; ở đây chọn provider theo `priority`, dựng prompt nội
 * bộ, gọi mô hình, đọc kết quả, và trả về đúng phần bản dịch. Không một
 * trường nào về provider, model, token hay chi phí được đưa vào response.
 *
 * Provider lỗi thì tự rơi xuống provider kế tiếp cùng `role` — đổi nhà cung
 * cấp hay hết hạn mức không làm gián đoạn người dùng.
 */
const fs = require('fs')
const path = require('path')
const dotenv = require('dotenv')
const axios = require('axios')

const AiProvider = require('../models/AiProvider')
const { encrypt, decrypt } = require('../utils/crypto')
const {
  parseResponseSegments, parseJsonObject, mergeTranslations, containsCjk,
} = require('../utils/json-repair')
const prompts = require('../prompts/translate')

class AiError extends Error {
  constructor(code, message, statusCode = 503) {
    super(message)
    this.name = 'AiError'
    this.code = code
    this.statusCode = statusCode
  }
}

const PROVIDER_CACHE_TTL_MS = 60_000
const providerCache = new Map()   // role -> { list, expiresAt }

/**
 * Tự động đồng bộ các API Key từ .env (cả control_server/.env và root .env)
 * vào database AiProvider để người dùng chỉ cần điền key vào .env là chạy được ngay.
 */
async function syncProvidersFromEnv() {
  const envPaths = [
    path.join(__dirname, '../../.env'),           // control_server/.env
    path.join(__dirname, '../../../../.env'),      // root .env
    path.join(process.cwd(), '.env'),             // current working dir .env
    path.join(process.cwd(), 'control_server/.env'),
  ]

  const loadedEnv = { ...process.env }
  for (const p of envPaths) {
    if (fs.existsSync(p)) {
      try {
        const parsed = dotenv.parse(fs.readFileSync(p, 'utf8'))
        Object.assign(loadedEnv, parsed)
      } catch {}
    }
  }

  const geminiTranslateKey = (loadedEnv.GEMINI_API_KEY || loadedEnv.GOOGLE_API_KEY || loadedEnv.SEED_GEMINI_API_KEY || '').trim()
  const geminiContentKey = (loadedEnv.GEMINI_CONTENT_API_KEY || loadedEnv.CONTENT_API_KEY || geminiTranslateKey).trim()

  const configs = [
    {
      name: 'hhtech',
      label: 'HHTech API / Custom AI',
      type: 'openai_compat',
      key: (loadedEnv.CUSTOM_AI_API_KEY || loadedEnv.HHTECH_API_KEY || '').trim(),
      model: (loadedEnv.CUSTOM_AI_MODEL || loadedEnv.HHTECH_MODEL || 'deepseek-v4-flash').trim(),
      baseUrl: (loadedEnv.CUSTOM_AI_BASE_URL || loadedEnv.HHTECH_BASE_URL || 'https://hhtechapi.net/v1').trim(),
      priority: 1,
    },
    {
      name: 'gemini',
      label: 'Google Gemini',
      type: 'google',
      translateKey: geminiTranslateKey,
      contentKey: geminiContentKey,
      model: (loadedEnv.GEMINI_MODEL || 'gemini-2.5-flash').trim(),
      baseUrl: 'https://generativelanguage.googleapis.com/v1beta',
      priority: 2,
    },
    {
      name: 'openrouter',
      label: 'OpenRouter',
      type: 'openai_compat',
      key: (loadedEnv.OPENROUTER_API_KEY || loadedEnv.SEED_OPENROUTER_API_KEY || '').trim(),
      model: (loadedEnv.OPENROUTER_MODEL || loadedEnv.SEED_OPENROUTER_MODEL || 'google/gemini-2.5-flash').trim(),
      baseUrl: 'https://openrouter.ai/api/v1',
      priority: 3,
    },
    {
      name: 'openai',
      label: 'OpenAI',
      type: 'openai_compat',
      key: (loadedEnv.OPENAI_API_KEY || loadedEnv.SEED_OPENAI_API_KEY || '').trim(),
      model: (loadedEnv.OPENAI_MODEL || 'gpt-4o-mini').trim(),
      baseUrl: 'https://api.openai.com/v1',
      priority: 4,
    },
    {
      name: 'deepseek',
      label: 'DeepSeek',
      type: 'openai_compat',
      key: (loadedEnv.DEEPSEEK_API_KEY || loadedEnv.SEED_DEEPSEEK_API_KEY || '').trim(),
      model: (loadedEnv.DEEPSEEK_MODEL || 'deepseek-chat').trim(),
      baseUrl: 'https://api.deepseek.com/v1',
      priority: 5,
    },
  ]

  let changed = false
  for (const cfg of configs) {
    for (const role of ['translate', 'content']) {
      const key = role === 'translate' ? (cfg.translateKey || cfg.key) : (cfg.contentKey || cfg.key)
      if (!key) continue
      const providerName = role === 'translate' ? cfg.name : `${cfg.name}-content`
      const providerLabel = role === 'translate' ? cfg.label : `${cfg.label} (Nội dung)`
      const updateData = {
        name: providerName,
        label: providerLabel,
        role,
        type: cfg.type,
        baseUrl: cfg.baseUrl,
        model: cfg.model,
        apiKeyEnc: encrypt(key),
        temperature: 0.3,
        maxTokens: 16384,
        priority: cfg.priority,
        enabled: true,
      }
      await AiProvider.findOneAndUpdate(
        { name: providerName },
        { $set: updateData },
        { upsert: true, new: true }
      )
      changed = true
    }
  }

  if (changed) {
    invalidateProviders()
  }
}

/** Provider đang bật của một vai trò, đã sắp theo ưu tiên. */
async function providersFor(role) {
  const hit = providerCache.get(role)
  if (hit && hit.expiresAt > Date.now()) return hit.list
  let list = await AiProvider.find({ role, enabled: true })
    .sort({ priority: 1 }).lean()
  if (!list.length) {
    await syncProvidersFromEnv()
    list = await AiProvider.find({ role, enabled: true })
      .sort({ priority: 1 }).lean()
  }
  providerCache.set(role, { list, expiresAt: Date.now() + PROVIDER_CACHE_TTL_MS })
  return list
}

function invalidateProviders() { providerCache.clear() }

// ------------------------------------------------------------ gọi mô hình ---

function openAiHeaders(provider, apiKey) {
  const headers = {
    Authorization: `Bearer ${apiKey}`,
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
  }
  const host = String(provider.baseUrl || '')
  if (host.includes('anthropic.com')) {
    headers['x-api-key'] = apiKey
    headers['anthropic-version'] = '2023-06-01'
  } else if (host.includes('openrouter.ai')) {
    headers['HTTP-Referer'] = 'https://example.com'
    headers['X-Title'] = 'VoxDub Studio'
  }
  return headers
}

/**
 * Một lượt gọi `/chat/completions`. Trả về { content, usage }.
 *
 * 429 → chờ tăng dần rồi thử lại; 5xx → chờ ngắn hơn; 401/403/404 → hỏng cấu
 * hình, báo ngay để rơi xuống provider dự phòng thay vì thử lại vô ích.
 */
async function callOpenAiCompat(provider, { system, user, schema, maxRetries = 2 }) {
  const apiKey = decrypt(provider.apiKeyEnc)
  if (!apiKey) throw new AiError('PROVIDER_MISCONFIGURED', `Provider ${provider.name} chưa có API key`)
  if (!provider.baseUrl || !provider.model) {
    throw new AiError('PROVIDER_MISCONFIGURED', `Provider ${provider.name} thiếu baseUrl/model`)
  }

  const url = provider.baseUrl.replace(/\/+$/, '').endsWith('/chat/completions')
    ? provider.baseUrl
    : `${provider.baseUrl.replace(/\/+$/, '')}/chat/completions`

  const payload = {
    model: provider.model,
    temperature: provider.temperature,
    max_tokens: provider.maxTokens,
    response_format: schema
      ? { type: 'json_schema', json_schema: { name: 'result', strict: true, schema } }
      : { type: 'json_object' },
    messages: [
      { role: 'system', content: system },
      { role: 'user', content: user },
    ],
  }
  if (provider.disableReasoning && url.includes('openrouter.ai')) {
    payload.reasoning = { enabled: false }
  }

  let lastError = ''
  let attempt = 0
  while (attempt < Math.max(1, maxRetries)) {
    let resp
    try {
      resp = await axios.post(url, payload, {
        headers: openAiHeaders(provider, apiKey),
        timeout: provider.timeoutMs || 180_000,
        validateStatus: () => true,
      })
    } catch (err) {
      lastError = `${err.code || 'NETWORK'}: ${err.message}`
      attempt += 1
      if (attempt >= maxRetries) break
      await sleep(Math.min(2 ** attempt * 1000, 8000))
      continue
    }

    if (resp.status === 200) return readOpenAiReply(resp.data, provider)

    if (resp.status === 429) {
      attempt += 1
      if (attempt >= maxRetries) {
        throw new AiError('RATE_LIMITED', `${provider.name} hết hạn mức (429)`)
      }
      await sleep(Math.min(2 ** attempt * 3000, 20_000))
      continue
    }
    if ([400, 401, 403, 404, 402].includes(resp.status)) {
      // Cấu hình sai hoặc hết tiền — thử lại cũng vậy, rơi xuống provider sau.
      const detail = typeof resp.data === 'string'
        ? resp.data.slice(0, 300) : JSON.stringify(resp.data || {}).slice(0, 300)
      // OpenRouter hay trả "Cannot read image.png" khi model/type sai
      // (key Gemini dán vào OpenAI, hoặc model vision). Hướng dẫn admin sửa.
      if (/image\.png|does not support image/i.test(detail)) {
        throw new AiError('PROVIDER_REJECTED',
          `${provider.name}: model không nhận text-only (lỗi image input). `
          + 'Nếu dùng key Gemini (AIza…): đặt Giao thức = Google Gemini, '
          + 'model = gemini-2.0-flash (không ghi google/…). '
          + 'Nếu dùng OpenRouter: model = google/gemini-2.5-flash, key sk-or-…')
      }
      throw new AiError('PROVIDER_REJECTED',
        `${provider.name} từ chối request (HTTP ${resp.status}): ${detail}`)
    }
    lastError = `HTTP ${resp.status}`
    attempt += 1
    if (attempt >= maxRetries) break
    await sleep(Math.min(2 ** attempt * 2000, 15_000))
  }
  throw new AiError('PROVIDER_UNAVAILABLE',
    `Không gọi được ${provider.name} sau ${maxRetries} lần — ${lastError}`)
}

function readOpenAiReply(data, provider) {
  const choice = data && data.choices && data.choices[0]
  const content = choice && choice.message && choice.message.content
  if (!content || !String(content).trim()) {
    throw new AiError('EMPTY_RESPONSE', `${provider.name} trả về nội dung rỗng`)
  }
  if (choice.finish_reason === 'length') {
    try {
      parseJsonObject(content)
    } catch {
      throw new AiError('TRUNCATED', `${provider.name} cắt phản hồi giữa chừng`)
    }
  }
  const usage = data.usage || {}
  return {
    content: String(content),
    usage: {
      promptTokens: usage.prompt_tokens || 0,
      completionTokens: usage.completion_tokens || 0,
    },
  }
}

/**
 * Chuẩn hóa tên model Gemini.
 * Admin hay dán nhầm `google/gemini-2.5-flash` (kiểu OpenRouter) hoặc
 * `models/gemini-2.5-flash` — API native chỉ nhận `gemini-2.5-flash`.
 */
function normalizeGeminiModel(model) {
  let name = String(model || '').trim()
  name = name.replace(/^models\//, '')
  name = name.replace(/^google\//, '')
  if (name === 'gemini-2.0-flash' || !name) {
    name = 'gemini-2.5-flash'
  }
  return name
}

/** Google Gemini — API riêng, không tương thích OpenAI. Chỉ gửi TEXT. */
async function callGemini(provider, { system, user, schema, maxRetries = 3 }) {
  const rawKey = decrypt(provider.apiKeyEnc)
  if (!rawKey) throw new AiError('PROVIDER_MISCONFIGURED', `Provider ${provider.name} chưa có API key`)

  const allKeys = rawKey.split(/[,;\n]+/).map((k) => k.trim()).filter(Boolean)
  let keyIndex = 0
  let apiKey = allKeys[0] || rawKey

  const initialModel = normalizeGeminiModel(provider.model) || 'gemini-2.5-flash'
  const fallbackList = [
    initialModel,
    'gemini-2.5-flash',
    'gemini-1.5-flash',
    'gemini-2.5-pro',
    'gemini-1.5-pro',
  ].filter((m, i, arr) => m && arr.indexOf(m) === i)

  let base = (provider.baseUrl || 'https://generativelanguage.googleapis.com/v1beta').replace(/\/+$/, '')
  // Nếu admin dán nhầm endpoint OpenAI-compat của Google → ép về v1beta native.
  if (base.includes('/openai')) {
    base = 'https://generativelanguage.googleapis.com/v1beta'
  }

  const generationConfig = {
    temperature: provider.temperature,
    maxOutputTokens: provider.maxTokens,
    responseMimeType: 'application/json',
  }
  // responseSchema không bắt buộc — một số model/region lỗi schema thì vẫn
  // chạy được nhờ responseMimeType=json + prompt đã dặn format.
  if (schema) {
    try {
      generationConfig.responseSchema = toGeminiSchema(schema)
    } catch {
      // bỏ schema, vẫn yêu cầu JSON
    }
  }

  // Chỉ TEXT — tuyệt đối không đính kèm image/file (tránh lỗi
  // "Cannot read image.png (this model does not support image input)").
  const payload = {
    contents: [{ role: 'user', parts: [{ text: String(user || '') }] }],
    generationConfig,
  }
  if (system && String(system).trim()) {
    payload.systemInstruction = { parts: [{ text: String(system).trim() }] }
  }

  let lastError = ''
  let modelIndex = 0
  let model = fallbackList[0]

  for (let attempt = 0; attempt < Math.max(1, maxRetries); attempt += 1) {
    const url = `${base}/models/${model}:generateContent`
    let resp
    try {
      resp = await axios.post(url, payload, {
        headers: { 'Content-Type': 'application/json', 'x-goog-api-key': apiKey },
        params: { key: apiKey },
        timeout: provider.timeoutMs || 180_000,
        validateStatus: () => true,
      })
    } catch (err) {
      lastError = `${err.code || 'NETWORK'}: ${err.message}`
      await sleep(Math.min(2 ** (attempt + 1) * 1000, 8000))
      continue
    }
    if (resp.status === 200) {
      const cand = resp.data && resp.data.candidates && resp.data.candidates[0]
      const text = cand && cand.content && cand.content.parts
        && cand.content.parts.map((p) => p.text || '').join('')
      if (!text || !text.trim()) {
        throw new AiError('EMPTY_RESPONSE', `${provider.name} trả về nội dung rỗng`)
      }
      if (cand.finishReason === 'MAX_TOKENS') {
        throw new AiError('TRUNCATED', `${provider.name} cắt phản hồi giữa chừng`)
      }
      const um = resp.data.usageMetadata || {}
      return {
        content: text,
        usage: {
          promptTokens: um.promptTokenCount || 0,
          completionTokens: um.candidatesTokenCount || 0,
        },
      }
    }
    const detail = _geminiErrorDetail(resp.data)
    if (resp.status === 429 || (resp.status === 403 && detail.toLowerCase().includes('quota'))) {
      if (keyIndex + 1 < allKeys.length) {
        keyIndex += 1
        apiKey = allKeys[keyIndex]
        lastError = `Rate limit trên key #${keyIndex}, đã chuyển sang key #${keyIndex + 1}`
        continue
      }
      const waitMs = Math.min(2 ** (attempt + 1) * 2000 + Math.floor(Math.random() * 1000), 20_000)
      lastError = `Rate limit (429): ${detail}`
      await sleep(waitMs)
      continue
    }
    if ([400, 401, 403, 404].includes(resp.status)) {
      // Schema không hỗ trợ → thử lại 1 lần không schema.
      if (resp.status === 400 && generationConfig.responseSchema && attempt === 0) {
        delete generationConfig.responseSchema
        lastError = detail || `HTTP ${resp.status}`
        continue
      }
      // Model 404 → chuyển sang model kế tiếp trong danh sách fallback
      if (resp.status === 404 && modelIndex + 1 < fallbackList.length) {
        modelIndex += 1
        model = fallbackList[modelIndex]
        lastError = detail || `HTTP ${resp.status}`
        continue
      }
      throw new AiError('PROVIDER_REJECTED',
        `${provider.name} từ chối request (HTTP ${resp.status}): ${detail}`)
    }
    lastError = detail || `HTTP ${resp.status}`
    await sleep(Math.min(2 ** (attempt + 1) * 2000, 15_000))
  }
  throw new AiError('PROVIDER_UNAVAILABLE', `Không gọi được ${provider.name} — ${lastError}`)
}

function _geminiErrorDetail(data) {
  if (!data) return ''
  if (typeof data === 'string') return data.slice(0, 300)
  const err = data.error || data
  const msg = err.message || err.status || JSON.stringify(err).slice(0, 300)
  return String(msg).slice(0, 300)
}

/** JSON Schema → lược đồ Gemini (không nhận `additionalProperties`, type viết HOA). */
function toGeminiSchema(schema) {
  if (!schema || typeof schema !== 'object') return schema
  if (Array.isArray(schema)) return schema.map(toGeminiSchema)
  const out = {}
  for (const [k, v] of Object.entries(schema)) {
    if (k === 'additionalProperties') continue
    if (k === 'type' && typeof v === 'string') {
      out[k] = v.toUpperCase()
    } else {
      out[k] = (v && typeof v === 'object') ? toGeminiSchema(v) : v
    }
  }
  return out
}

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)) }

/**
 * Gọi mô hình qua provider ưu tiên nhất còn dùng được.
 *
 * Trả về { content, usage, provider }. Provider nào lỗi thì ghi lại lý do
 * (để admin nhìn thấy trong dashboard) rồi thử provider kế tiếp; hết provider
 * mới ném lỗi lên trên.
 */
async function callWithFallback(role, args) {
  const list = await providersFor(role)
  if (!list.length) {
    throw new AiError('NO_PROVIDER',
      `Chưa cấu hình API Key cho "${role}". Hãy thêm GEMINI_API_KEY hoặc OPENROUTER_API_KEY vào tệp .env hoặc trang Cài đặt.`, 503)
  }

  let lastError = null
  for (const provider of list) {
    try {
      // Key Gemini (AIza...) bắt buộc đi API native — nếu admin lỡ chọn
      // openai_compat/OpenRouter sẽ ra lỗi lạ kiểu "Cannot read image.png".
      const apiKey = decrypt(provider.apiKeyEnc || '')
      const looksGeminiKey = /^(AIza|AQ\.)/i.test(apiKey)
      const useGemini = provider.type === 'google' || provider.type === 'gemini'
        || looksGeminiKey
      const result = useGemini
        ? await callGemini(provider, args)
        : await callOpenAiCompat(provider, args)
      AiProvider.updateOne({ _id: provider._id },
        { $set: { lastOkAt: new Date(), lastError: '' } }).catch(() => {})
      return { ...result, provider }
    } catch (err) {
      lastError = err
      AiProvider.updateOne({ _id: provider._id }, {
        $set: { lastErrorAt: new Date(), lastError: String(err.message).slice(0, 300) },
      }).catch(() => {})
    }
  }
  throw lastError || new AiError('AI_UNAVAILABLE', 'Không nơi nào phản hồi')
}

// ---------------------------------------------------------------- dịch lô ---

/**
 * Dịch một lô câu. Trả về { segments, usage, provider, model }.
 *
 * Thiếu câu thì chia đôi lô rồi thử lại đúng phần thiếu — mô hình yếu hay
 * nghẹn ở lô lớn, và một lô 60 câu thiếu 2 câu không đáng phải dịch lại cả 60.
 * Hết hạn mức (RATE_LIMITED) thì KHÔNG chia đôi: chia đôi làm số request tăng
 * gấp đôi, đúng thứ đang bị chặn.
 */
async function translateBatch({ segments, sourceLang, targetField, context,
  cpsBudget, prevContext = [], maxRetries = 2, depth = 0 }) {
  const system = prompts.buildTranslateSystemPrompt({
    sourceLang, targetField, context, cpsBudget,
  })
  const user = prompts.buildTranslateUserPrompt({ segments, targetField, prevContext })
  const schema = prompts.translateSchema(targetField)

  const { content, usage, provider } = await callWithFallback('translate',
    { system, user, schema, maxRetries })
  const returned = parseResponseSegments(content)
  const { merged, missing } = mergeTranslations(segments, returned, targetField)

  if (!missing.length) {
    return { segments: merged, usage, provider: provider.name, model: provider.model }
  }
  if (segments.length === 1 || depth >= 3) {
    // Không chia nhỏ hơn được nữa — trả về phần dịch được, lớp trên quyết
    // định (câu thiếu sẽ được app giữ nguyên bản gốc).
    return { segments: merged, usage, provider: provider.name, model: provider.model, missing }
  }

  const missingSet = new Set(missing.map(String))
  const rest = segments.filter((s) => missingSet.has(String(s.id)))
  const mid = Math.floor(rest.length / 2) || 1
  const halves = [rest.slice(0, mid), rest.slice(mid)].filter((h) => h.length)

  const results = await Promise.all(halves.map((half) => translateBatch({
    segments: half, sourceLang, targetField, context, cpsBudget,
    prevContext, maxRetries, depth: depth + 1,
  }).catch(() => null)))

  const extra = []
  let extraPrompt = 0
  let extraCompletion = 0
  for (const r of results) {
    if (!r) continue
    extra.push(...r.segments)
    extraPrompt += r.usage.promptTokens
    extraCompletion += r.usage.completionTokens
  }

  const byId = new Map([...merged, ...extra].map((s) => [String(s.id), s]))
  const ordered = segments.map((s) => byId.get(String(s.id))).filter(Boolean)
  return {
    segments: ordered,
    usage: {
      promptTokens: usage.promptTokens + extraPrompt,
      completionTokens: usage.completionTokens + extraCompletion,
    },
    provider: provider.name,
    model: provider.model,
  }
}

/** Dịch lại các câu còn sót chữ Hán (lưới cuối trước khi trả về app). */
async function fixCjkLeftovers({ merged, sourceLang, targetField, context, cpsBudget }) {
  const bad = merged.filter((s) => containsCjk(s[targetField]))
  if (!bad.length) return { segments: merged, usage: { promptTokens: 0, completionTokens: 0 } }

  const system = prompts.buildTranslateSystemPrompt({ sourceLang, targetField, context, cpsBudget })
  const schema = prompts.translateSchema(targetField)
  let promptTokens = 0
  let completionTokens = 0

  const fixes = await Promise.all(bad.map(async (seg) => {
    const user = 'Your previous translation still contained Chinese characters: '
      + `${JSON.stringify(seg[targetField])}\n`
      + `Translate this ONE segment again. "${targetField}" must be pure Vietnamese `
      + '(Latin script only). Return ONLY JSON: '
      + `{"segments": [{"id": ..., "${targetField}": "..."}]}\n\n`
      + JSON.stringify({ id: seg.id })
    try {
      const { content, usage } = await callWithFallback('translate',
        { system, user, schema, maxRetries: 2 })
      promptTokens += usage.promptTokens
      completionTokens += usage.completionTokens
      const returned = parseResponseSegments(content)
      const text = returned[0] && String(returned[0][targetField] || '').trim()
      if (text && !containsCjk(text)) return [seg.id, text]
    } catch {
      // Giữ bản cũ — giọng đọc sẽ bỏ qua ký tự lạ, còn hơn mất cả câu.
    }
    return null
  }))

  const fixed = new Map(fixes.filter(Boolean))
  const segments = merged.map((s) => (
    fixed.has(s.id) ? { ...s, [targetField]: fixed.get(s.id) } : s
  ))
  return { segments, usage: { promptTokens, completionTokens } }
}

/** Phân tích ngữ cảnh video (lượt 0). Trả về dict hoặc null. */
async function analyze({ lines, sourceLang, videoTitle }) {
  const user = prompts.buildAnalysisPrompt({ lines, sourceLang, videoTitle })
  const { content, usage, provider } = await callWithFallback('translate', {
    system: prompts.ANALYSIS_SYSTEM,
    user,
    schema: prompts.ANALYSIS_SCHEMA,
    maxRetries: 2,
  })
  const data = parseJsonObject(content)
  return { analysis: data, usage, provider: provider.name, model: provider.model }
}

/** Rà soát và dịch lại một câu nghi vấn. */
async function reviewOne({ segment, reason, neighbors, sourceLang, targetField,
  context, cpsBudget }) {
  const system = prompts.buildTranslateSystemPrompt({ sourceLang, targetField, context, cpsBudget })
  const user = prompts.buildReviewUserPrompt({ segment, reason, targetField, neighbors })
  const { content, usage } = await callWithFallback('translate', {
    system, user, schema: prompts.translateSchema(targetField), maxRetries: 2,
  })
  const returned = parseResponseSegments(content)
  const text = returned[0] && String(returned[0][targetField] || '').trim()
  return { text: text || '', usage }
}

// ------------------------------------------------------ nội dung đăng bài ---

// Emoji và ký hiệu trang trí — người dùng cấm tuyệt đối, prompt đã dặn nhưng
// mô hình vẫn hay lỡ tay, nên đây là lớp bảo đảm cuối.
const EMOJI_RE = /[\u{1F000}-\u{1FAFF}\u{2700}-\u{27BF}\u{2600}-\u{26FF}\u{1F1E6}-\u{1F1FF}\u{FE00}-\u{FE0F}\u{1F3FB}-\u{1F3FF}\u{200D}\u{20E3}\u{2B00}-\u{2BFF}\u{2190}-\u{21FF}\u{2500}-\u{25FF}]+/gu

function stripEmoji(value) {
  if (typeof value === 'string') {
    const cleaned = value.replace(EMOJI_RE, '')
    return cleaned === value ? value : cleaned.split(/\s+/).filter(Boolean).join(' ')
  }
  if (Array.isArray(value)) return value.map(stripEmoji)
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, stripEmoji(v)]))
  }
  return value
}

async function generatePost({ scriptOriginal, scriptVi, videoTitle }) {
  const user = prompts.buildContentPrompt({ scriptOriginal, scriptVi, videoTitle })
  // Vai trò "content" có provider riêng thì dùng; chưa cấu hình thì dùng
  // chung với dịch (một provider chạy được cả hai việc).
  const contentProviders = await providersFor('content')
  const role = contentProviders.length ? 'content' : 'translate'
  const { content, usage, provider } = await callWithFallback(role, {
    system: prompts.CONTENT_SYSTEM,
    user,
    schema: prompts.CONTENT_SCHEMA,
    maxRetries: 3,
  })
  const data = parseJsonObject(content)
  if (!data) throw new AiError('BAD_AI_RESPONSE', 'Không đọc được nội dung đăng bài', 502)
  return { metadata: stripEmoji(data), usage, provider: provider.name, model: provider.model }
}

module.exports = {
  AiError,
  translateBatch,
  fixCjkLeftovers,
  analyze,
  reviewOne,
  generatePost,
  invalidateProviders,
  providersFor,
  syncProvidersFromEnv,
}
