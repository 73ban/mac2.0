#!/usr/bin/env node
import { spawnSync } from "node:child_process"
import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url))
const PROJECT_ROOT = path.resolve(process.env.WIKI_PROJECT_PATH ?? path.join(SCRIPT_DIR, "../.."))
const RUNTIME_SOURCE = path.resolve(process.env.WIKI_RUNTIME_SOURCE_PATH ?? "/Users/qixinchaye/Workspace/73WIKI-1.0-source")
const CS_CAILIAN_SCRIPT = path.resolve(process.env.CS_CAILIAN_SCRIPT ?? "/Users/qixinchaye/Desktop/standalone-small-files/fetch-cs-cailian-raw.mjs")
const THS_FETCH_SCRIPT = path.resolve(process.env.THS_HOTLIST_FETCH_SCRIPT ?? "/Users/qixinchaye/.codex/skills/playwright-ths-hotlist/scripts/fetch-ths-hotlist.mjs")

const HEALTH_PATH = path.join(PROJECT_ROOT, ".system/cloud-data-connectors-health.json")
const LOG_PATH = path.join(PROJECT_ROOT, ".system/logs/cloud-data-connectors.log")
const LOCK_PATH = path.join(PROJECT_ROOT, ".system/cloud-data-connectors.lock")
const THS_HOTLIST_STATE_PATH = path.join(PROJECT_ROOT, ".system/ths-hotlist-scheduler-state.json")
const MAX_STDIO = 128 * 1024 * 1024

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true })
}

function writeJson(file, value) {
  ensureDir(path.dirname(file))
  fs.writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`, "utf8")
}

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"))
  } catch {
    return fallback
  }
}

function appendLog(message) {
  ensureDir(path.dirname(LOG_PATH))
  fs.appendFileSync(LOG_PATH, `${message}\n`, "utf8")
}

function nowLocalTimestamp(date = new Date()) {
  const pad = (n) => String(n).padStart(2, "0")
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

function tail(text, size = 4000) {
  const value = String(text ?? "")
  return value.length > size ? value.slice(-size) : value
}

function extractJson(stdout) {
  const text = String(stdout ?? "")
  const start = text.indexOf("{")
  const end = text.lastIndexOf("}")
  if (start < 0 || end <= start) return null
  try {
    return JSON.parse(text.slice(start, end + 1))
  } catch {
    return null
  }
}

function cleanCell(value) {
  return String(value ?? "")
    .replace(/\r?\n/g, " ")
    .replace(/\|/g, " / ")
    .trim()
}

function renderThsHotlistMarkdown(snapshot, generatedAt) {
  const rows = Array.isArray(snapshot?.rows) ? snapshot.rows : []
  const tradeDate = snapshot?.evidenceTradeDate ?? snapshot?.tradeDate ?? snapshot?.planTradeDate ?? nowLocalTimestamp().slice(0, 10)
  const lines = [
    `# ${tradeDate} 同花顺热榜 Top100`,
    "",
    `生成时间：${generatedAt}`,
    "",
    "## 元信息",
    "",
    "```yaml",
    `source: ${cleanCell(snapshot?.source ?? "tonghuashun-hotlist")}`,
    `source_url: ${cleanCell(snapshot?.sourceUrl ?? "")}`,
    `snapshot_id: ${cleanCell(snapshot?.id ?? "")}`,
    `rows: ${rows.length}`,
    `complete: ${Boolean(snapshot?.counts?.complete)}`,
    "```",
    "",
    "## 明细",
    "",
    "| 排名 | 代码 | 名称 | 涨跌幅% | 热度分 | 热榜变化 | 概念标签 | 人气标签 | 分析标题 |",
    "|---:|---|---|---:|---:|---:|---|---|---|",
  ]
  for (const row of rows) {
    const tags = Array.isArray(row?.conceptTags) ? row.conceptTags.join("、") : ""
    lines.push([
      cleanCell(row?.rank),
      cleanCell(row?.code),
      cleanCell(row?.name),
      cleanCell(row?.changePercent),
      cleanCell(row?.hotScore),
      cleanCell(row?.hotRankChange),
      cleanCell(tags),
      cleanCell(row?.popularityTag),
      cleanCell(row?.analyseTitle || row?.analyse),
    ].join(" | ").replace(/^/, "| ").replace(/$/, " |"))
  }
  lines.push(
    "",
    "## 使用口径",
    "",
    "- 本文件是同花顺热榜 RAW 归档，给人看用 Markdown，给脚本训练用同目录 JSON。",
    "- 热榜只代表关注度和异动线索，不直接代表买入权限。",
    "- 热榜排名快速上升、涨幅大、且能在新闻/公告/涨停结构中找到催化的个股，进入作战室复核。",
  )
  return `${lines.join("\n")}\n`
}

function archiveThsHotlistToRaw(snapshot) {
  if (!snapshot || !Array.isArray(snapshot.rows)) {
    return { ok: false, reason: "missing_snapshot_rows" }
  }
  const tradeDate = snapshot.evidenceTradeDate ?? snapshot.tradeDate ?? snapshot.planTradeDate ?? nowLocalTimestamp().slice(0, 10)
  const outDir = path.join(PROJECT_ROOT, "raw/04-市场数据/同花顺热榜", tradeDate)
  const unifiedDir = path.join(PROJECT_ROOT, "raw/04-市场数据/热榜", tradeDate)
  const generatedAt = nowLocalTimestamp()
  const payload = {
    ...snapshot,
    rawArchive: {
      schema: "73wiki-ths-hotlist-raw-archive-v1",
      archivedAt: generatedAt,
      json: `raw/04-市场数据/同花顺热榜/${tradeDate}/ths-hot-top100.json`,
      md: `raw/04-市场数据/同花顺热榜/${tradeDate}/ths-hot-top100.md`,
      unifiedJson: `raw/04-市场数据/热榜/${tradeDate}/同花顺热榜Top100.json`,
      unifiedMd: `raw/04-市场数据/热榜/${tradeDate}/同花顺热榜Top100.md`,
    },
  }
  const jsonPath = path.join(outDir, "ths-hot-top100.json")
  const mdPath = path.join(outDir, "ths-hot-top100.md")
  const unifiedJsonPath = path.join(unifiedDir, "同花顺热榜Top100.json")
  const unifiedMdPath = path.join(unifiedDir, "同花顺热榜Top100.md")
  writeJson(jsonPath, payload)
  writeJson(unifiedJsonPath, payload)
  ensureDir(outDir)
  const markdown = renderThsHotlistMarkdown(payload, generatedAt)
  fs.writeFileSync(mdPath, markdown, "utf8")
  ensureDir(unifiedDir)
  fs.writeFileSync(unifiedMdPath, markdown, "utf8")
  return {
    ok: true,
    tradeDate,
    rows: payload.rows.length,
    json: path.relative(PROJECT_ROOT, jsonPath),
    md: path.relative(PROJECT_ROOT, mdPath),
    unifiedJson: path.relative(PROJECT_ROOT, unifiedJsonPath),
    unifiedMd: path.relative(PROJECT_ROOT, unifiedMdPath),
  }
}

function pidAlive(pid) {
  if (!Number.isFinite(pid) || pid <= 0) return false
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

function acquireRunLock() {
  ensureDir(path.dirname(LOCK_PATH))
  const staleMs = Number(process.env.CONNECTOR_STALE_LOCK_MS ?? 60 * 60 * 1000)
  const nowMs = Date.now()
  const lockPayload = {
    pid: process.pid,
    startedAt: nowLocalTimestamp(),
    startedAtMs: nowMs,
  }
  try {
    const fd = fs.openSync(LOCK_PATH, "wx")
    fs.writeFileSync(fd, `${JSON.stringify(lockPayload, null, 2)}\n`, "utf8")
    return {
      acquired: true,
      release() {
        try {
          fs.closeSync(fd)
        } catch {}
        try {
          fs.unlinkSync(LOCK_PATH)
        } catch {}
      },
    }
  } catch (error) {
    const existing = readJson(LOCK_PATH, {})
    const ageMs = nowMs - Number(existing.startedAtMs ?? 0)
    const alive = pidAlive(Number(existing.pid))
    if (!alive || ageMs > staleMs) {
      try {
        fs.unlinkSync(LOCK_PATH)
      } catch {}
      return acquireRunLock()
    }
    return {
      acquired: false,
      lock: existing,
      ageMs,
      error: String(error?.message ?? error),
      release() {},
    }
  }
}

function runNode(script, args, options = {}) {
  const startedAt = Date.now()
  const result = spawnSync(process.execPath, [script, ...args], {
    cwd: options.cwd ?? PROJECT_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, HOME: process.env.HOME ?? "/Users/qixinchaye", WIKI_PROJECT_PATH: PROJECT_ROOT },
    maxBuffer: MAX_STDIO,
    timeout: options.timeoutMs ?? Number(process.env.CONNECTOR_STEP_TIMEOUT_MS ?? 120000),
  })
  return {
    ok: result.status === 0,
    status: result.status,
    durationMs: Date.now() - startedAt,
    stdout: result.stdout ?? "",
    stderr: result.stderr ?? "",
    error: result.error ? String(result.error.message ?? result.error) : null,
    signal: result.signal ?? null,
  }
}

function readWatchlistSymbols() {
  const file = path.join(PROJECT_ROOT, ".llm-wiki/market-watchlist/latest-warroom-watchlist.json")
  const limit = Number(process.env.TENCENT_SYMBOL_LIMIT ?? 20)
  const symbols = []
  try {
    const payload = JSON.parse(fs.readFileSync(file, "utf8"))
    for (const section of ["focus", "warroom", "normal"]) {
      for (const item of payload?.tiers?.[section] ?? []) {
        const code = String(item?.code ?? "").trim()
        if (/^\d{6}$/.test(code) && !symbols.includes(code)) symbols.push(code)
      }
    }
  } catch {
    return []
  }
  return symbols.slice(0, Number.isFinite(limit) && limit > 0 ? limit : 20)
}

function fileExists(file) {
  return fs.existsSync(file) && fs.statSync(file).isFile()
}

function fileFingerprint(file) {
  try {
    const stat = fs.statSync(file)
    return `${Math.round(stat.mtimeMs)}:${stat.size}`
  } catch {
    return ""
  }
}

function parseLocalTimestampMs(value) {
  const text = String(value ?? "").trim()
  if (!text) return 0
  const parsed = Date.parse(text.replace(" ", "T"))
  return Number.isFinite(parsed) ? parsed : 0
}

function listFilesRecursive(dir, out = []) {
  if (!fs.existsSync(dir)) return out
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) listFilesRecursive(full, out)
    else out.push(full)
  }
  return out
}

function checkRequiredFiles() {
  const files = {
    csCailianScript: CS_CAILIAN_SCRIPT,
    runtimeSource: RUNTIME_SOURCE,
    tencentMarketScript: path.join(RUNTIME_SOURCE, "scripts/tencent-market.mjs"),
    thsCaptureImportScript: path.join(RUNTIME_SOURCE, "scripts/ths-hotlist-capture-import.mjs"),
    thsFetchScript: THS_FETCH_SCRIPT,
  }
  return Object.fromEntries(Object.entries(files).map(([key, value]) => {
    const exists = key === "runtimeSource" ? fs.existsSync(value) && fs.statSync(value).isDirectory() : fileExists(value)
    return [key, { path: value, exists }]
  }))
}

function runCsCailian() {
  const outDir = path.join(PROJECT_ROOT, "raw/05-研报新闻/财联社/CS财经")
  const result = runNode(CS_CAILIAN_SCRIPT, [
    "--out", outDir,
    "--state", path.join(PROJECT_ROOT, ".system/cs-cailian-seen.json"),
    "--image-cache-file", path.join(PROJECT_ROOT, ".system/cs-cailian-image-ocr-cache.json"),
    "--log", path.join(PROJECT_ROOT, ".system/logs/cs-cailian-watch.log"),
    "--pagesize", String(process.env.CS_CAILIAN_PAGESIZE ?? 10),
    "--no-ocr",
    "--no-wiki-artifacts",
    "--no-war-room-candidates",
  ], { timeoutMs: Number(process.env.CS_CAILIAN_TIMEOUT_MS ?? 60000) })
  const match = result.stdout.match(/new=(\d+)/)
  return {
    ok: result.ok,
    status: result.status,
    durationMs: result.durationMs,
    rawOut: outDir,
    newItems: match ? Number(match[1]) : null,
    stderr: tail(result.stderr),
    stdoutTail: tail(result.stdout),
    error: result.error,
    signal: result.signal,
  }
}

function runTencentMarket() {
  const symbols = readWatchlistSymbols()
  const args = ["snapshot", "--project", PROJECT_ROOT, "--write"]
  if (symbols.length > 0) args.push("--symbols", symbols.join(","))
  const result = runNode(path.join(RUNTIME_SOURCE, "scripts/tencent-market.mjs"), args, {
    cwd: RUNTIME_SOURCE,
    timeoutMs: Number(process.env.TENCENT_MARKET_TIMEOUT_MS ?? 90000),
  })
  const payload = extractJson(result.stdout)
  return {
    ok: result.ok,
    status: result.status,
    durationMs: result.durationMs,
    symbolsRequested: symbols,
    stockQuotes: payload?.record?.stockQuotes?.length ?? null,
    indexQuotes: payload?.record?.indexQuotes?.length ?? null,
    tradeDate: payload?.record?.evidenceTradeDate ?? payload?.record?.tradeDate ?? null,
    written: payload?.written ?? null,
    stderr: tail(result.stderr),
    error: result.error,
    signal: result.signal,
  }
}

function runThsHotlist() {
  const latestPath = path.join(PROJECT_ROOT, ".llm-wiki/ths-hotlist/latest-ths-hotlist.json")
  const latest = readJson(latestPath, null)
  const state = readJson(THS_HOTLIST_STATE_PATH, {})
  const intervalHours = Number(process.env.THS_HOTLIST_INTERVAL_HOURS ?? 2)
  const intervalMs = Math.max(0.25, Number.isFinite(intervalHours) ? intervalHours : 2) * 60 * 60 * 1000
  const latestMtimeMs = (() => {
    try {
      return fs.statSync(latestPath).mtimeMs
    } catch {
      return 0
    }
  })()
  const lastRunAtMs = Number(state.lastRunAtMs ?? 0) || latestMtimeMs
  const forced = process.env.THS_HOTLIST_FORCE === "1"
  const latestRows = latest?.counts?.rows ?? (Array.isArray(latest?.rows) ? latest.rows.length : null)
  const latestComplete = Boolean(latest?.counts?.complete)
  const shouldRun = forced || !lastRunAtMs || Date.now() - lastRunAtMs >= intervalMs || !latestComplete

  if (!shouldRun) {
    const rawArchive = archiveThsHotlistToRaw(latest)
    return {
      ok: true,
      skipped: true,
      skipReason: "two_hour_interval_not_due",
      runReason: "not_due",
      intervalHours: intervalMs / 60 / 60 / 1000,
      lastRunAt: state.lastRunAt ?? (latestMtimeMs ? nowLocalTimestamp(new Date(latestMtimeMs)) : null),
      lastRunAtMs,
      nextDueAt: nowLocalTimestamp(new Date(lastRunAtMs + intervalMs)),
      capturedRows: latestRows,
      capturePath: latest?.captureFile ?? null,
      imported: {
        dryRun: false,
        id: latest?.id ?? null,
        rows: latestRows,
        complete: latestComplete,
        written: {
          facts: "data/facts/ths_hotlist_snapshots.jsonl",
          latest: ".llm-wiki/ths-hotlist/latest-ths-hotlist.json",
        },
      },
      rawArchive,
      message: "THS hotlist capture skipped; using latest Top100 snapshot because the 2-hour interval is not due.",
    }
  }

  const result = runNode(path.join(RUNTIME_SOURCE, "scripts/ths-hotlist-capture-import.mjs"), [
    "--project", PROJECT_ROOT,
    "--fetch-script", THS_FETCH_SCRIPT,
    "--max-items", String(process.env.THS_HOTLIST_MAX_ITEMS ?? 100),
    "--write",
  ], {
    cwd: RUNTIME_SOURCE,
    timeoutMs: Number(process.env.THS_HOTLIST_TIMEOUT_MS ?? 120000),
  })
  const payload = extractJson(result.stdout)
  if (result.ok && payload?.ok !== false) {
    writeJson(THS_HOTLIST_STATE_PATH, {
      lastRunAt: nowLocalTimestamp(),
      lastRunAtMs: Date.now(),
      intervalHours: intervalMs / 60 / 60 / 1000,
      capturedRows: payload?.capturedRows ?? null,
      importedRows: payload?.imported?.rows ?? null,
      complete: Boolean(payload?.imported?.complete),
      runReason: forced ? "forced" : "interval_due",
    })
  }
  const rawArchive = archiveThsHotlistToRaw(readJson(latestPath, null))
  return {
    ok: result.ok,
    status: result.status,
    durationMs: result.durationMs,
    skipped: false,
    intervalHours: intervalMs / 60 / 60 / 1000,
    capturedRows: payload?.capturedRows ?? null,
    capturePath: payload?.capturePath ?? null,
    imported: payload?.imported ?? null,
    rawArchive,
    stderr: tail(result.stderr || payload?.stderr || ""),
    stdoutTail: result.ok ? "" : tail(result.stdout),
    error: result.error,
    signal: result.signal,
  }
}

function runThsHotlistMovers() {
  const script = path.join(PROJECT_ROOT, "raw/07-系统脚本/codex_ths_hotlist_movers.py")
  if (!fileExists(script)) {
    return {
      ok: false,
      skipped: true,
      script,
      message: "THS hotlist movers script is missing.",
    }
  }
  const tradeDate = process.env.TRADING_REVIEW_DATE ?? nowLocalTimestamp().slice(0, 10)
  const startedAt = Date.now()
  const result = spawnSync("python3", [
    script,
    "--date", tradeDate,
    "--top", String(process.env.THS_HOTLIST_MOVERS_TOP ?? 20),
    "--lookback-hours", String(process.env.THS_HOTLIST_MOVERS_LOOKBACK_HOURS ?? 36),
    "--write",
  ], {
    cwd: PROJECT_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, HOME: process.env.HOME ?? "/Users/qixinchaye" },
    maxBuffer: MAX_STDIO,
    timeout: Number(process.env.THS_HOTLIST_MOVERS_TIMEOUT_MS ?? 60000),
  })
  const payload = extractJson(result.stdout)
  return {
    ok: result.status === 0 && payload?.ok !== false,
    status: result.status,
    durationMs: Date.now() - startedAt,
    date: tradeDate,
    tracked: payload?.tracked ?? null,
    withDirectReason: payload?.withDirectReason ?? null,
    withLocalEvidence: payload?.withLocalEvidence ?? null,
    outputs: payload?.outputs ?? null,
    stderr: tail(result.stderr),
    stdoutTail: result.status === 0 ? "" : tail(result.stdout),
    error: result.error ? String(result.error.message ?? result.error) : null,
    signal: result.signal ?? null,
  }
}

function runMpHotTop10Extraction() {
  const script = path.join(PROJECT_ROOT, "raw/07-系统脚本/codex_extract_mp_hot_top10.py")
  if (!fileExists(script)) {
    return {
      ok: false,
      skipped: true,
      script,
      message: "MP hot Top10 extractor is missing.",
    }
  }
  const startedAt = Date.now()
  const result = spawnSync("python3", [
    script,
    "--days",
    String(process.env.MP_HOT_TOP10_LOOKBACK_DAYS ?? 14),
    "--write",
  ], {
    cwd: PROJECT_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, HOME: process.env.HOME ?? "/Users/qixinchaye" },
    maxBuffer: MAX_STDIO,
    timeout: Number(process.env.MP_HOT_TOP10_TIMEOUT_MS ?? 60000),
  })
  const payload = extractJson(result.stdout)
  return {
    ok: result.status === 0 && payload?.ok !== false,
    status: result.status,
    durationMs: Date.now() - startedAt,
    recordCount: payload?.recordCount ?? null,
    platformCount: payload?.platformCount ?? null,
    outputs: payload?.outputs ?? null,
    stderr: tail(result.stderr),
    stdoutTail: result.status === 0 ? "" : tail(result.stdout),
    error: result.error ? String(result.error.message ?? result.error) : null,
    signal: result.signal ?? null,
  }
}

function runWechatMpSeeds() {
  const seedsPath = path.join(PROJECT_ROOT, ".system/wechat-mp-url-seeds.json")
  const seedScript = path.join(PROJECT_ROOT, ".system/scripts/fetch-wechat-mp-seeds.mjs")
  const statePath = path.join(PROJECT_ROOT, ".system/wechat-mp-url-seeds-state.json")
  if (!fileExists(seedScript) || !fileExists(seedsPath)) {
    return {
      ok: false,
      skipped: true,
      seedScript,
      seedsPath,
      message: "Wechat MP URL seed capture is not configured.",
    }
  }
  const seeds = readJson(seedsPath, []).filter((item) => item?.enabled !== false && item?.url)
  const state = readJson(statePath, { seen: {}, runs: [] })
  const schedule = state.scheduler ?? {}
  const seedFingerprint = fileFingerprint(seedsPath)
  const intervalHours = Number(process.env.WECHAT_MP_SEEDS_FALLBACK_INTERVAL_HOURS ?? 6)
  const intervalMs = Math.max(1, Number.isFinite(intervalHours) ? intervalHours : 6) * 60 * 60 * 1000
  const previousRun = Array.isArray(state.runs) ? state.runs[state.runs.length - 1] : null
  const lastRunAtMs = Number(schedule.lastRunAtMs ?? 0)
    || parseLocalTimestampMs(schedule.lastRunAt)
    || parseLocalTimestampMs(previousRun?.at)
  const lastResults = Array.isArray(state.runs) ? state.runs[state.runs.length - 1]?.results ?? [] : []
  const seedChanged = schedule.seedFingerprint !== seedFingerprint
  const dueByInterval = !lastRunAtMs || Date.now() - lastRunAtMs >= intervalMs
  const forced = process.env.WECHAT_MP_SEEDS_FORCE === "1"
  const shouldRun = forced || seedChanged || dueByInterval
  if (!shouldRun) {
    return {
      ok: true,
      skipped: true,
      skipReason: "low_frequency_url_seed_capture",
      runReason: "not_due",
      seeds: seeds.length,
      seedFingerprint,
      lastRunAt: schedule.lastRunAt ?? (Array.isArray(state.runs) ? state.runs[state.runs.length - 1]?.at ?? null : null),
      lastRunAtMs,
      nextDueAt: nowLocalTimestamp(new Date(lastRunAtMs + intervalMs)),
      fallbackIntervalHours: intervalMs / 60 / 60 / 1000,
      lastOk: Array.isArray(lastResults) && lastResults.length > 0 ? lastResults.every((item) => item?.ok) : null,
      lastOkCount: Array.isArray(lastResults) ? countOk(lastResults) : null,
      lastTotal: Array.isArray(lastResults) ? lastResults.length : null,
      message: "URL seed capture skipped; WeRSS remains the primary 15-minute公众号 capture path.",
      results: [],
    }
  }
  const result = runNode(seedScript, [], {
    cwd: PROJECT_ROOT,
    timeoutMs: Number(process.env.WECHAT_MP_SEEDS_TIMEOUT_MS ?? 90000),
  })
  const payload = extractJson(result.stdout)
  const completedAt = nowLocalTimestamp()
  const nextState = readJson(statePath, { seen: {}, runs: [] })
  nextState.scheduler = {
    ...(nextState.scheduler ?? {}),
    lastRunAt: completedAt,
    lastRunAtMs: Date.now(),
    lastRunReason: forced ? "forced" : seedChanged ? "seed_file_changed" : "fallback_interval_due",
    seedFingerprint,
    fallbackIntervalHours: intervalMs / 60 / 60 / 1000,
  }
  writeJson(statePath, nextState)
  return {
    ok: result.ok,
    status: result.status,
    durationMs: result.durationMs,
    seeds: payload?.seeds ?? null,
    results: payload?.results ?? [],
    skipped: false,
    runReason: nextState.scheduler.lastRunReason,
    lastRunAt: completedAt,
    lastRunAtMs: nextState.scheduler.lastRunAtMs,
    nextDueAt: nowLocalTimestamp(new Date(nextState.scheduler.lastRunAtMs + intervalMs)),
    seedFingerprint,
    fallbackIntervalHours: intervalMs / 60 / 60 / 1000,
    stderr: tail(result.stderr),
    stdoutTail: result.ok ? "" : tail(result.stdout),
    error: result.error,
    signal: result.signal,
  }
}

function werssLogin(baseUrl, username, password) {
  const result = spawnSync("curl", [
    "-fsS",
    "--max-time", "10",
    "-X", "POST",
    `${baseUrl}/auth/login`,
    "-H", "Content-Type: application/x-www-form-urlencoded",
    "--data-urlencode", `username=${username}`,
    "--data-urlencode", `password=${password}`,
  ], {
    cwd: PROJECT_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    timeout: 12000,
  })
  const payload = extractJson(result.stdout)
  return {
    ok: result.status === 0 && payload?.code === 0 && Boolean(payload?.data?.access_token),
    status: result.status,
    token: payload?.data?.access_token ?? null,
    stderr: tail(result.stderr),
    stdoutTail: result.status === 0 ? "" : tail(result.stdout),
    error: result.error ? String(result.error.message ?? result.error) : null,
    signal: result.signal ?? null,
  }
}

function runWerssMpsUpdate() {
  const baseUrl = (process.env.WERSS_API_BASE_URL ?? "http://127.0.0.1:8002/api/v1/wx").replace(/\/+$/, "")
  const username = process.env.WERSS_USERNAME ?? "admin"
  const password = process.env.WERSS_PASSWORD ?? "admin@123"
  const login = werssLogin(baseUrl, username, password)
  if (!login.ok) {
    return {
      ok: false,
      status: login.status,
      baseUrl,
      loginOk: false,
      updated: [],
      message: "WeRSS login failed; scan authorization or check local WeRSS service.",
      stderr: login.stderr,
      stdoutTail: login.stdoutTail,
      error: login.error,
      signal: login.signal,
    }
  }

  const listResult = spawnSync("curl", [
    "-fsS",
    "--max-time", "10",
    "-H", `Authorization: Bearer ${login.token}`,
    `${baseUrl}/mps?offset=0&limit=${String(process.env.WERSS_UPDATE_MPS_LIMIT ?? 100)}`,
  ], {
    cwd: PROJECT_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    timeout: 12000,
  })
  const listPayload = extractJson(listResult.stdout)
  const mps = listPayload?.data?.list ?? []
  if (listResult.status !== 0 || listPayload?.code !== 0 || !Array.isArray(mps)) {
    return {
      ok: false,
      status: listResult.status,
      baseUrl,
      loginOk: true,
      listOk: false,
      updated: [],
      stderr: tail(listResult.stderr),
      stdoutTail: listResult.status === 0 ? "" : tail(listResult.stdout),
      error: listResult.error ? String(listResult.error.message ?? listResult.error) : null,
      signal: listResult.signal ?? null,
    }
  }

  const maxMps = Number(process.env.WERSS_UPDATE_MAX_MPS ?? 100)
  const selectedMps = mps.slice(0, Number.isFinite(maxMps) && maxMps > 0 ? maxMps : 100)
  const startPage = String(process.env.WERSS_UPDATE_START_PAGE ?? 0)
  const endPage = String(process.env.WERSS_UPDATE_END_PAGE ?? 1)
  const timeoutMs = Number(process.env.WERSS_UPDATE_ONE_TIMEOUT_MS ?? 45000)
  const updated = []
  for (const mp of selectedMps) {
    const mpId = mp?.mp_id ?? mp?.id
    if (!mpId) continue
    const startedAt = Date.now()
    const result = spawnSync("curl", [
      "-fsS",
      "--max-time", String(Math.max(5, Math.ceil(timeoutMs / 1000))),
      "-H", `Authorization: Bearer ${login.token}`,
      `${baseUrl}/mps/update/${encodeURIComponent(mpId)}?start_page=${startPage}&end_page=${endPage}`,
    ], {
      cwd: PROJECT_ROOT,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      timeout: timeoutMs,
    })
    const payload = extractJson(result.stdout)
    const code = payload?.code
    updated.push({
      ok: result.status === 0 && (code === 0 || code === 40402),
      status: result.status,
      code,
      mpId,
      mpName: mp?.mp_name ?? null,
      total: payload?.data?.total ?? null,
      message: payload?.message ?? null,
      durationMs: Date.now() - startedAt,
      stderr: tail(result.stderr, 800),
      error: result.error ? String(result.error.message ?? result.error) : null,
      signal: result.signal ?? null,
    })
  }

  const failed = updated.filter((item) => !item.ok)
  const toleratedFailures = Number(process.env.WERSS_UPDATE_TOLERATED_MP_FAILURES ?? 3)
  const okCount = updated.length - failed.length
  const tolerated = okCount > 0 && failed.length <= Math.max(0, Number.isFinite(toleratedFailures) ? toleratedFailures : 3)
  const allOk = failed.length === 0
  return {
    ok: allOk || tolerated,
    degraded: !allOk && tolerated,
    status: allOk || tolerated ? 0 : 1,
    baseUrl,
    loginOk: true,
    listOk: true,
    mpCount: mps.length,
    mpNames: mps.map((mp) => mp?.mp_name ?? "").filter(Boolean),
    updatedCount: updated.length,
    okCount,
    failedCount: failed.length,
    failedMps: failed.map((item) => ({
      mpId: item.mpId,
      mpName: item.mpName,
      code: item.code,
      message: item.message,
      status: item.status,
    })),
    newArticleTotal: updated.reduce((sum, item) => sum + (Number(item.total) || 0), 0),
    updated,
  }
}

function runWerssApiIngest() {
  const script = path.join(PROJECT_ROOT, "raw/07-系统脚本/codex_ingest_werss_api.py")
  if (!fileExists(script)) {
    return {
      ok: false,
      skipped: true,
      script,
      message: "WeRSS API ingest script is missing.",
    }
  }
  const baseUrl = process.env.WERSS_API_BASE_URL ?? "http://127.0.0.1:8002/api/v1/wx"
  const result = spawnSync("python3", [
    script,
    "--mode", "ingest",
    "--once",
    "--base-url", baseUrl,
    "--username", process.env.WERSS_USERNAME ?? "admin",
    "--password", process.env.WERSS_PASSWORD ?? "admin@123",
    "--state", path.join(PROJECT_ROOT, ".system/werss-api-state.json"),
    "--log", path.join(PROJECT_ROOT, ".system/logs/werss-api-ingest.log"),
    "--audit-json", path.join(PROJECT_ROOT, ".system/werss-api-repair-audit.json"),
    "--audit-md", path.join(PROJECT_ROOT, ".system/werss-api-repair-audit.md"),
    "--with-image-download",
    "--with-ocr",
  ], {
    cwd: PROJECT_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, HOME: process.env.HOME ?? "/Users/qixinchaye" },
    maxBuffer: MAX_STDIO,
    timeout: Number(process.env.WERSS_API_INGEST_TIMEOUT_MS ?? 180000),
  })
  const payload = extractJson(result.stdout)
  return {
    ok: result.status === 0,
    status: result.status,
    baseUrl,
    ingest: payload?.ingest ?? payload ?? null,
    stderr: tail(result.stderr),
    stdoutTail: result.status === 0 ? "" : tail(result.stdout),
    error: result.error ? String(result.error.message ?? result.error) : null,
    signal: result.signal ?? null,
  }
}

function runRawQueueScan() {
  const script = path.join(PROJECT_ROOT, "raw/07-系统脚本/codex_raw_watch.py")
  if (!fileExists(script)) {
    return {
      ok: false,
      skipped: true,
      script,
      message: "RAW watcher script is missing.",
    }
  }
  const lookbackHours = String(process.env.RAW_QUEUE_LOOKBACK_HOURS ?? 6)
  const startedAt = Date.now()
  const result = spawnSync("python3", [
    script,
    "--root", PROJECT_ROOT,
    "--once",
    "--lookback-hours", lookbackHours,
    "--no-wiki-log",
  ], {
    cwd: PROJECT_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, HOME: process.env.HOME ?? "/Users/qixinchaye" },
    maxBuffer: MAX_STDIO,
    timeout: Number(process.env.RAW_QUEUE_SCAN_TIMEOUT_MS ?? 60000),
  })
  const payload = extractJson(result.stdout)
  return {
    ok: result.status === 0,
    status: result.status,
    durationMs: Date.now() - startedAt,
    lookbackHours: Number(lookbackHours),
    queued: payload?.new_files ?? payload?.queued ?? payload?.new_items ?? payload?.count ?? null,
    payload,
    stderr: tail(result.stderr),
    stdoutTail: result.status === 0 ? "" : tail(result.stdout),
    error: result.error ? String(result.error.message ?? result.error) : null,
    signal: result.signal ?? null,
  }
}

function runRawQueueIngest() {
  const script = path.join(PROJECT_ROOT, "raw/07-系统脚本/codex_batch_ingest_queue.py")
  if (!fileExists(script)) {
    return {
      ok: false,
      skipped: true,
      script,
      message: "RAW batch ingest script is missing.",
    }
  }
  const startedAt = Date.now()
  const result = spawnSync("python3", [script], {
    cwd: PROJECT_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, HOME: process.env.HOME ?? "/Users/qixinchaye" },
    maxBuffer: MAX_STDIO,
    timeout: Number(process.env.RAW_QUEUE_INGEST_TIMEOUT_MS ?? 120000),
  })
  const payload = extractJson(result.stdout)
  return {
    ok: result.status === 0,
    status: result.status,
    durationMs: Date.now() - startedAt,
    processed: payload?.processed ?? null,
    registryAdded: payload?.registry_added ?? null,
    archive: payload?.archive ?? null,
    payload,
    stderr: tail(result.stderr),
    stdoutTail: result.status === 0 ? "" : tail(result.stdout),
    error: result.error ? String(result.error.message ?? result.error) : null,
    signal: result.signal ?? null,
  }
}

function runCatalystRadar() {
  const script = path.join(PROJECT_ROOT, "raw/07-系统脚本/codex_realtime_catalyst_radar.py")
  if (!fileExists(script)) {
    return {
      ok: false,
      skipped: true,
      script,
      message: "Realtime catalyst radar script is missing.",
    }
  }
  const tradeDate = process.env.TRADING_REVIEW_DATE ?? nowLocalTimestamp().slice(0, 10)
  const startedAt = Date.now()
  const result = spawnSync("python3", [
    script,
    "--date", tradeDate,
    "--lookback-hours", String(process.env.CATALYST_RADAR_LOOKBACK_HOURS ?? 18),
    "--top", String(process.env.CATALYST_RADAR_TOP ?? 10),
    "--notify-threshold", String(process.env.CATALYST_RADAR_NOTIFY_THRESHOLD ?? 70),
  ], {
    cwd: PROJECT_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, HOME: process.env.HOME ?? "/Users/qixinchaye" },
    maxBuffer: MAX_STDIO,
    timeout: Number(process.env.CATALYST_RADAR_TIMEOUT_MS ?? 60000),
  })
  const payload = extractJson(result.stdout)
  return {
    ok: result.status === 0 && payload?.ok !== false,
    status: result.status,
    durationMs: Date.now() - startedAt,
    date: tradeDate,
    payload,
    stderr: tail(result.stderr),
    stdoutTail: result.status === 0 ? "" : tail(result.stdout),
    error: result.error ? String(result.error.message ?? result.error) : null,
    signal: result.signal ?? null,
  }
}

function runFeishuPendingNotifications() {
  const script = path.join(PROJECT_ROOT, ".system/scripts/send-feishu-pending-notifications.py")
  if (!fileExists(script)) {
    return {
      ok: false,
      skipped: true,
      script,
      message: "Feishu pending notification sender is missing.",
    }
  }
  const startedAt = Date.now()
  const result = spawnSync("python3", [script], {
    cwd: PROJECT_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, HOME: process.env.HOME ?? "/Users/qixinchaye" },
    maxBuffer: MAX_STDIO,
    timeout: Number(process.env.FEISHU_NOTIFY_TIMEOUT_MS ?? 60000),
  })
  const payload = extractJson(result.stdout)
  return {
    ok: result.status === 0 && payload?.ok !== false,
    status: result.status,
    durationMs: Date.now() - startedAt,
    payload,
    stderr: tail(result.stderr),
    stdoutTail: result.status === 0 ? "" : tail(result.stdout),
    error: result.error ? String(result.error.message ?? result.error) : null,
    signal: result.signal ?? null,
  }
}

function runWarroomValidation() {
  const script = path.join(PROJECT_ROOT, "raw/07-系统脚本/codex_warroom_validation_pipeline.py")
  if (!fileExists(script)) {
    return {
      ok: false,
      skipped: true,
      script,
      message: "Warroom validation pipeline script is missing.",
    }
  }
  const tradeDate = process.env.TRADING_REVIEW_DATE ?? nowLocalTimestamp().slice(0, 10)
  const startedAt = Date.now()
  const result = spawnSync("python3", [script, "--date", tradeDate], {
    cwd: PROJECT_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, HOME: process.env.HOME ?? "/Users/qixinchaye" },
    maxBuffer: MAX_STDIO,
    timeout: Number(process.env.WARROOM_VALIDATION_TIMEOUT_MS ?? 90000),
  })
  const payload = extractJson(result.stdout)
  return {
    ok: result.status === 0 && payload?.schema === "73wiki-warroom-validation-run-v1",
    status: result.status,
    durationMs: Date.now() - startedAt,
    date: tradeDate,
    payload,
    stderr: tail(result.stderr),
    stdoutTail: result.status === 0 ? "" : tail(result.stdout),
    error: result.error ? String(result.error.message ?? result.error) : null,
    signal: result.signal ?? null,
  }
}

function runDplusOverview() {
  const script = path.join(PROJECT_ROOT, "raw/07-系统脚本/codex_generate_dplus_tasks.py")
  if (!fileExists(script)) {
    return {
      ok: false,
      skipped: true,
      script,
      message: "D+ validation task generator is missing.",
    }
  }
  const tradeDate = process.env.TRADING_REVIEW_DATE ?? nowLocalTimestamp().slice(0, 10)
  const startedAt = Date.now()
  const result = spawnSync("python3", [script, "--all", "--force", "--overview", "--today", tradeDate], {
    cwd: PROJECT_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, HOME: process.env.HOME ?? "/Users/qixinchaye" },
    maxBuffer: MAX_STDIO,
    timeout: Number(process.env.DPLUS_OVERVIEW_TIMEOUT_MS ?? 60000),
  })
  const overview = readJson(path.join(PROJECT_ROOT, "data/facts/dplus_due_tasks.json"), { dates: {} })
  const overviewText = (() => {
    try {
      return fs.readFileSync(path.join(PROJECT_ROOT, "wiki/09-统计与进化/D+验证待回填总览.md"), "utf8")
    } catch {
      return ""
    }
  })()
  const summaryMatch = {
    resolvedCount: Number(overviewText.match(/resolved_count:\s*(\d+)/)?.[1] ?? NaN),
    overduePendingCount: Number(overviewText.match(/overdue_pending_count:\s*(\d+)/)?.[1] ?? NaN),
    dueTodayCount: Number(overviewText.match(/due_today_count:\s*(\d+)/)?.[1] ?? NaN),
    futurePendingCount: Number(overviewText.match(/future_pending_count:\s*(\d+)/)?.[1] ?? NaN),
  }
  return {
    ok: result.status === 0,
    status: result.status,
    durationMs: Date.now() - startedAt,
    date: tradeDate,
    dueDateCount: Object.keys(overview?.dates ?? {}).length,
    resolvedCount: Number.isFinite(summaryMatch.resolvedCount) ? summaryMatch.resolvedCount : null,
    overduePendingCount: Number.isFinite(summaryMatch.overduePendingCount) ? summaryMatch.overduePendingCount : null,
    dueTodayCount: Number.isFinite(summaryMatch.dueTodayCount) ? summaryMatch.dueTodayCount : null,
    futurePendingCount: Number.isFinite(summaryMatch.futurePendingCount) ? summaryMatch.futurePendingCount : null,
    overview: "wiki/09-统计与进化/D+验证待回填总览.md",
    stderr: tail(result.stderr),
    stdoutTail: tail(result.stdout),
    error: result.error ? String(result.error.message ?? result.error) : null,
    signal: result.signal ?? null,
  }
}

function runDplusAutofill() {
  const script = path.join(PROJECT_ROOT, "raw/07-系统脚本/codex_dplus_validation_autofill.py")
  if (!fileExists(script)) {
    return {
      ok: false,
      skipped: true,
      script,
      message: "D+ validation autofill script is missing.",
    }
  }
  const tradeDate = process.env.TRADING_REVIEW_DATE ?? nowLocalTimestamp().slice(0, 10)
  const startedAt = Date.now()
  const args = [script, "--today", tradeDate]
  if (process.env.DPLUS_AUTOFILL_ALLOW_INTRADAY === "1") args.push("--allow-intraday")
  const result = spawnSync("python3", args, {
    cwd: PROJECT_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, HOME: process.env.HOME ?? "/Users/qixinchaye" },
    maxBuffer: MAX_STDIO,
    timeout: Number(process.env.DPLUS_AUTOFILL_TIMEOUT_MS ?? 90000),
  })
  const payload = extractJson(result.stdout)
  return {
    ok: result.status === 0 && payload?.ok !== false,
    status: result.status,
    durationMs: Date.now() - startedAt,
    date: tradeDate,
    skipped: Boolean(payload?.skipped),
    pendingChecked: payload?.pendingChecked ?? null,
    resolved: payload?.resolved ?? null,
    added: payload?.added ?? null,
    existingResolvedDue: payload?.existingResolvedDue ?? null,
    missing: payload?.missing ?? null,
    payload,
    stderr: tail(result.stderr),
    stdoutTail: result.status === 0 ? "" : tail(result.stdout),
    error: result.error ? String(result.error.message ?? result.error) : null,
    signal: result.signal ?? null,
  }
}

function runDplusMonthlyDashboard() {
  const script = path.join(PROJECT_ROOT, "raw/07-系统脚本/codex_dplus_monthly_dashboard.py")
  if (!fileExists(script)) {
    return {
      ok: false,
      skipped: true,
      script,
      message: "D+ monthly dashboard script is missing.",
    }
  }
  const tradeDate = process.env.TRADING_REVIEW_DATE ?? nowLocalTimestamp().slice(0, 10)
  const month = tradeDate.slice(0, 7)
  const startedAt = Date.now()
  const result = spawnSync("python3", [script, "--month", month], {
    cwd: PROJECT_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, HOME: process.env.HOME ?? "/Users/qixinchaye" },
    maxBuffer: MAX_STDIO,
    timeout: Number(process.env.DPLUS_MONTHLY_DASHBOARD_TIMEOUT_MS ?? 90000),
  })
  const payload = extractJson(result.stdout)
  const monthStat = payload?.summary?.byMonth?.[payload?.month ?? month] ?? {}
  return {
    ok: result.status === 0 && payload?.schema === "73wiki-dplus-monthly-dashboard-v1",
    status: result.status,
    durationMs: Date.now() - startedAt,
    date: tradeDate,
    month,
    predictionCount: payload?.predictionCount ?? null,
    resultCount: payload?.resultCount ?? null,
    monthTotal: monthStat.total ?? null,
    strictHitRate: monthStat.strictHitRate ?? null,
    usableRate: monthStat.usableRate ?? null,
    failRate: monthStat.failRate ?? null,
    avgRelativeToSH: monthStat.avgRelativeToSH ?? null,
    outputs: payload?.outputs ?? null,
    payload,
    stderr: tail(result.stderr),
    stdoutTail: result.status === 0 ? "" : tail(result.stdout),
    error: result.error ? String(result.error.message ?? result.error) : null,
    signal: result.signal ?? null,
  }
}

function runAiContextUpdate() {
  const script = path.join(PROJECT_ROOT, "raw/07-系统脚本/codex_update_ai_context.py")
  if (!fileExists(script)) {
    return {
      ok: false,
      skipped: true,
      script,
      message: "AI context update script is missing.",
    }
  }
  const tradeDate = process.env.TRADING_REVIEW_DATE ?? nowLocalTimestamp().slice(0, 10)
  const startedAt = Date.now()
  const result = spawnSync("python3", [script, "--date", tradeDate], {
    cwd: PROJECT_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, HOME: process.env.HOME ?? "/Users/qixinchaye" },
    maxBuffer: MAX_STDIO,
    timeout: Number(process.env.AI_CONTEXT_UPDATE_TIMEOUT_MS ?? 60000),
  })
  return {
    ok: result.status === 0,
    status: result.status,
    durationMs: Date.now() - startedAt,
    date: tradeDate,
    stdoutTail: tail(result.stdout),
    stderr: tail(result.stderr),
    error: result.error ? String(result.error.message ?? result.error) : null,
    signal: result.signal ?? null,
  }
}

function runDailyWikiPublishAudit() {
  const script = path.join(PROJECT_ROOT, "raw/07-系统脚本/codex_publish_daily_raw_to_wiki.py")
  if (!fileExists(script)) {
    return {
      ok: false,
      skipped: true,
      script,
      message: "Daily RAW-to-WIKI publish script is missing.",
    }
  }
  const tradeDate = process.env.TRADING_REVIEW_DATE ?? nowLocalTimestamp().slice(0, 10)
  const startedAt = Date.now()
  const result = spawnSync("python3", [script, "--date", tradeDate], {
    cwd: PROJECT_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, HOME: process.env.HOME ?? "/Users/qixinchaye" },
    maxBuffer: MAX_STDIO,
    timeout: Number(process.env.DAILY_WIKI_PUBLISH_TIMEOUT_MS ?? 60000),
  })
  const payload = extractJson(result.stdout)
  return {
    ok: result.status === 0 && payload?.schema === "73wiki-daily-raw-to-wiki-publish-v1" && payload?.ok !== false,
    status: result.status,
    durationMs: Date.now() - startedAt,
    date: tradeDate,
    requiredNow: Boolean(payload?.requiredNow),
    reviewPublished: Boolean(payload?.review?.ok),
    tradePublished: Boolean(payload?.trade?.ok),
    reviewWiki: payload?.review?.wiki ?? null,
    tradeWiki: payload?.trade?.wiki ?? null,
    audit: payload?.outputs?.audit ?? null,
    payload,
    stderr: tail(result.stderr),
    stdoutTail: result.status === 0 ? "" : tail(result.stdout),
    error: result.error ? String(result.error.message ?? result.error) : null,
    signal: result.signal ?? null,
  }
}

function probeImageOcr() {
  const startedAt = Date.now()
  const result = spawnSync("python3", [
    "-c",
    "import rapidocr_onnxruntime; print('rapidocr_onnxruntime')",
  ], {
    cwd: PROJECT_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    timeout: 10000,
  })
  return {
    ok: result.status === 0,
    status: result.status,
    durationMs: Date.now() - startedAt,
    engine: result.status === 0 ? "rapidocr_onnxruntime" : "",
    message: result.status === 0
      ? "Image OCR engine is available."
      : "Image OCR engine is not installed; image OCR is configured by policy but not active.",
    stderr: tail(result.stderr),
    stdoutTail: tail(result.stdout),
    error: result.error ? String(result.error.message ?? result.error) : null,
    signal: result.signal ?? null,
  }
}

function countMarkdownFiles(dir) {
  return listFilesRecursive(dir).filter((file) => file.endsWith(".md")).length
}

function isFormalMarkdown(file) {
  const name = path.basename(file).toLowerCase()
  return file.endsWith(".md") && name !== "readme.md" && !name.includes("sync-conflict")
}

function countContentMarkdownFiles(dir) {
  return listFilesRecursive(dir).filter(isFormalMarkdown).length
}

function sourceNamesFromUrlSeeds() {
  const seedsPath = path.join(PROJECT_ROOT, ".system/wechat-mp-url-seeds.json")
  const seeds = readJson(seedsPath, [])
  if (!Array.isArray(seeds)) return new Set()
  return new Set(
    seeds
      .filter((item) => item?.enabled !== false && item?.source)
      .map((item) => String(item.source).trim())
      .filter(Boolean),
  )
}

function activeYouziSources(currentMpNames = null) {
  const classesPath = path.join(PROJECT_ROOT, ".system/wechat-mp-source-classes.json")
  const config = readJson(classesPath, {})
  const sourceClasses = config.sources ?? {}
  const currentSources = Array.isArray(currentMpNames) && currentMpNames.length > 0
    ? new Set(currentMpNames.map((name) => String(name).trim()).filter(Boolean))
    : sourceNamesFromUrlSeeds()
  const names = Object.entries(sourceClasses)
    .filter(([, sourceClass]) => sourceClass === "游资心得")
    .map(([name]) => name)
    .filter((name) => currentSources.has(name))
    .sort((a, b) => a.localeCompare(b, "zh-Hans-CN"))
  return names
}

function markdownFilesUnderSources(root, sources) {
  const out = []
  for (const source of sources) {
    const dir = path.join(root, source)
    out.push(...listFilesRecursive(dir).filter(isFormalMarkdown))
  }
  return out
}

function sourceFromRawRel(rawRel) {
  const parts = String(rawRel ?? "").split("/")
  const legacyIdx = parts.findIndex((part, idx) => part === "游资号" && parts[idx - 1] === "公众号")
  if (legacyIdx >= 0 && parts.length > legacyIdx + 1) return parts[legacyIdx + 1]
  const shortlineIdx = parts.findIndex((part, idx) => part === "游资公众号" && parts[idx - 1] === "09-短线知识")
  if (shortlineIdx >= 0 && parts.length > shortlineIdx + 1) return parts[shortlineIdx + 1]
  return ""
}

function probeYouziLearningStatus(currentMpNames = null) {
  const youziSources = activeYouziSources(currentMpNames)
  const legacyRoot = path.join(PROJECT_ROOT, "raw/05-研报新闻/公众号/游资号")
  const shortlineRoot = path.join(PROJECT_ROOT, "raw/09-短线知识")
  const shortlineYouziRoot = path.join(shortlineRoot, "游资公众号")
  const shortlineFeishuRoot = path.join(shortlineRoot, "飞书输入")
  const shortlineOcrRoot = path.join(shortlineRoot, "截图OCR")
  const shortlineManualRoot = path.join(shortlineRoot, "手工摘录")
  const statePath = path.join(PROJECT_ROOT, ".system/youzi-learning-state.json")
  const state = readJson(statePath, { items: [] })
  const stateItems = Array.isArray(state.items) ? state.items : []
  let ocrActiveFiles = 0
  let ocrSectionFiles = 0
  const bySource = {}

  for (const source of youziSources) {
    const dir = path.join(legacyRoot, source)
    const files = listFilesRecursive(dir).filter(isFormalMarkdown)
    let sourceOcrActive = 0
    let sourceOcrSections = 0
    for (const file of files) {
      let text = ""
      try {
        text = fs.readFileSync(file, "utf8")
      } catch {
        continue
      }
      if (text.includes("ocr_policy_active: true") && !text.includes("ocr_image_count: 0")) sourceOcrActive += 1
      if (text.includes("## 图片文字识别")) sourceOcrSections += 1
    }
    ocrActiveFiles += sourceOcrActive
    ocrSectionFiles += sourceOcrSections
    bySource[source] = {
      files: files.length,
      ocrActiveFiles: sourceOcrActive,
      ocrSectionFiles: sourceOcrSections,
    }
  }

  const activeLegacyFiles = markdownFilesUnderSources(legacyRoot, youziSources)
  const activeShortlineFiles = markdownFilesUnderSources(shortlineYouziRoot, youziSources)
  const activeRawRelSet = new Set([...activeLegacyFiles, ...activeShortlineFiles].map((file) => path.relative(PROJECT_ROOT, file)))
  const activeSourceSet = new Set(youziSources)
  const activeStateItems = stateItems.filter((item) => activeRawRelSet.has(item.raw_rel) || activeSourceSet.has(sourceFromRawRel(item.raw_rel)))
  const legacyTotalFiles = countContentMarkdownFiles(legacyRoot)
  const activeCandidateFiles = activeRawRelSet.size
  const activeLearningLag = Math.max(0, activeCandidateFiles - activeStateItems.length)

  return {
    ok: activeLearningLag <= 3 && youziSources.length > 0,
    activeSourceMode: Array.isArray(currentMpNames) && currentMpNames.length > 0
      ? "local_werss_subscriptions_with_youzi_class"
      : "url_seeds_with_youzi_class",
    activeSources: youziSources,
    activeSourceCount: youziSources.length,
    legacyRoot,
    shortlineRoot,
    shortlineYouziRoot,
    raw09Files: countContentMarkdownFiles(shortlineRoot),
    raw09FeishuFiles: countContentMarkdownFiles(shortlineFeishuRoot),
    raw09YouziFiles: countContentMarkdownFiles(shortlineYouziRoot),
    raw09OcrFiles: countContentMarkdownFiles(shortlineOcrRoot),
    raw09ManualFiles: countContentMarkdownFiles(shortlineManualRoot),
    activeLegacyYouziFiles: activeLegacyFiles.length,
    activeShortlineYouziFiles: activeShortlineFiles.length,
    activeCandidateFiles,
    activeStateItems: activeStateItems.length,
    activeLearningLag,
    legacyYouziFiles: legacyTotalFiles,
    legacyInactiveFiles: Math.max(0, legacyTotalFiles - activeLegacyFiles.length),
    ocrActiveFiles,
    ocrSectionFiles,
    stateItems: stateItems.length,
    bySource,
  }
}

function probeLocalWechatBizArticles() {
  const rawMpDir = path.join(PROJECT_ROOT, "raw/05-研报新闻/公众号")
  const recentRawFiles = listFilesRecursive(rawMpDir)
    .filter((file) => file.endsWith(".md"))
    .map((file) => ({ file, mtimeMs: fs.statSync(file).mtimeMs }))
    .sort((a, b) => b.mtimeMs - a.mtimeMs)
    .slice(0, 5)

  const result = spawnSync("wx", ["biz-articles", "--json", "--limit", String(process.env.WX_BIZ_ARTICLES_LIMIT ?? 20)], {
    cwd: PROJECT_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, HOME: process.env.HOME ?? "/Users/qixinchaye" },
    timeout: Number(process.env.WX_BIZ_ARTICLES_TIMEOUT_MS ?? 20000),
  })
  const payload = extractJson(result.stdout)
  const articles = Array.isArray(payload) ? payload : payload?.articles ?? payload?.data ?? []
  const ok = result.status === 0

  return {
    ok,
    status: result.status,
    sourceMode: "local-direct",
    command: "wx biz-articles --json",
    articleCount: Array.isArray(articles) ? articles.length : null,
    latestRawFiles: recentRawFiles.map((item) => ({
      path: path.relative(PROJECT_ROOT, item.file),
      mtime: nowLocalTimestamp(new Date(item.mtimeMs)),
    })),
    message: ok
      ? "Local wx-cli biz article cache is reachable."
      : "Local wx-cli biz article cache is not reachable; check wx-cli config.json, daemon log, and WeChat authorization.",
    stdoutTail: ok ? "" : tail(result.stdout),
    stderr: tail(result.stderr),
    error: result.error ? String(result.error.message ?? result.error) : null,
    signal: result.signal ?? null,
  }
}

function countOk(items) {
  if (!Array.isArray(items)) return null
  return items.filter((item) => item?.ok).length
}

function buildSummary(health) {
  const werssUpdate = health.optionalResults.werssMpsUpdate ?? {}
  const werssIngest = health.optionalResults.werssApiIngest?.ingest ?? {}
  const seedResult = health.optionalResults.wechatMpSeeds ?? {}
  const seedItems = Array.isArray(seedResult.results) ? seedResult.results : []
  const urlSeedOk = seedResult.skipped ? seedResult.lastOkCount ?? null : countOk(seedItems)
  const urlSeedTotal = seedResult.skipped ? seedResult.lastTotal ?? seedResult.seeds ?? seedItems.length : seedResult.seeds ?? seedItems.length
  const moduleOk = {
    csCailian: Boolean(health.results.csCailian?.ok),
    tencentMarket: Boolean(health.results.tencentMarket?.ok),
    thsHotlist: Boolean(health.results.thsHotlist?.ok),
    thsHotlistMovers: Boolean(health.optionalResults.thsHotlistMovers?.ok),
    werssMpsUpdate: Boolean(health.optionalResults.werssMpsUpdate?.ok),
    werssApiIngest: Boolean(health.optionalResults.werssApiIngest?.ok),
    mpHotTop10: Boolean(health.optionalResults.mpHotTop10?.ok),
    wechatMpSeeds: Boolean(health.optionalResults.wechatMpSeeds?.ok),
    rawQueueScan: Boolean(health.optionalResults.rawQueueScan?.ok),
    rawQueueIngest: Boolean(health.optionalResults.rawQueueIngest?.ok),
    catalystRadar: Boolean(health.optionalResults.catalystRadar?.ok),
    warroomValidation: Boolean(health.optionalResults.warroomValidation?.ok),
    dailyWikiPublish: Boolean(health.optionalResults.dailyWikiPublish?.ok),
    dplusAutofill: Boolean(health.optionalResults.dplusAutofill?.ok),
    dplusOverview: Boolean(health.optionalResults.dplusOverview?.ok),
    dplusMonthlyDashboard: Boolean(health.optionalResults.dplusMonthlyDashboard?.ok),
    feishuPendingNotifications: Boolean(health.optionalResults.feishuPendingNotifications?.ok),
    aiContextUpdate: Boolean(health.optionalResults.aiContextUpdate?.ok),
  }
  return {
    subscriptions: werssUpdate.mpCount ?? null,
    updatedSubscriptions: werssUpdate.updatedCount ?? null,
    werssUpdateFailedCount: werssUpdate.failedCount ?? null,
    werssUpdateFailedMps: werssUpdate.failedMps ?? [],
    werssUpdateDegraded: Boolean(werssUpdate.degraded),
    newArticleTotal: werssUpdate.newArticleTotal ?? null,
    new_articles: werssIngest.new_articles ?? null,
    bootstrapped_existing: werssIngest.bootstrapped_existing ?? null,
    fetched_articles: werssIngest.fetched_articles ?? null,
    urlSeedOk,
    urlSeedTotal,
    urlSeedSkipped: Boolean(seedResult.skipped),
    urlSeedRunReason: seedResult.runReason ?? seedResult.skipReason ?? null,
    urlSeedLastRunAt: seedResult.lastRunAt ?? null,
    urlSeedNextDueAt: seedResult.nextDueAt ?? null,
    urlSeedFallbackIntervalHours: seedResult.fallbackIntervalHours ?? null,
    thsHotlistCapturedRows: health.results.thsHotlist?.capturedRows ?? null,
    thsHotlistImportedRows: health.results.thsHotlist?.imported?.rows ?? null,
    thsHotlistComplete: Boolean(health.results.thsHotlist?.imported?.complete),
    thsHotlistSkipped: Boolean(health.results.thsHotlist?.skipped),
    thsHotlistIntervalHours: health.results.thsHotlist?.intervalHours ?? null,
    thsHotlistNextDueAt: health.results.thsHotlist?.nextDueAt ?? null,
    thsHotlistRawJson: health.results.thsHotlist?.rawArchive?.json ?? null,
    thsHotlistRawMd: health.results.thsHotlist?.rawArchive?.md ?? null,
    thsHotlistMoversTracked: health.optionalResults.thsHotlistMovers?.tracked ?? null,
    thsHotlistMoversWithDirectReason: health.optionalResults.thsHotlistMovers?.withDirectReason ?? null,
    thsHotlistMoversWithLocalEvidence: health.optionalResults.thsHotlistMovers?.withLocalEvidence ?? null,
    mpHotTop10Records: health.optionalResults.mpHotTop10?.recordCount ?? null,
    mpHotTop10Platforms: health.optionalResults.mpHotTop10?.platformCount ?? null,
    rawQueueNewFiles: health.optionalResults.rawQueueScan?.payload?.new_files ?? health.optionalResults.rawQueueScan?.queued ?? null,
    rawQueueProcessed: health.optionalResults.rawQueueIngest?.processed ?? null,
    rawQueueRegistryAdded: health.optionalResults.rawQueueIngest?.registryAdded ?? null,
    catalystRadarTopScore: health.optionalResults.catalystRadar?.payload?.topScore ?? null,
    catalystRadarTopAction: health.optionalResults.catalystRadar?.payload?.topAction ?? "",
    catalystRadarRanked: health.optionalResults.catalystRadar?.payload?.ranked ?? null,
    catalystRadarNotifyFresh: health.optionalResults.catalystRadar?.payload?.notify?.fresh ?? null,
    catalystRadarNotifyCreated: health.optionalResults.catalystRadar?.payload?.notify?.created ?? null,
    warroomValidationCandidates: health.optionalResults.warroomValidation?.payload?.candidateCount ?? null,
    warroomValidationAdd: health.optionalResults.warroomValidation?.payload?.summary?.add ?? null,
    warroomValidationKeep: health.optionalResults.warroomValidation?.payload?.summary?.keep ?? null,
    warroomValidationDowngradeWatch: health.optionalResults.warroomValidation?.payload?.summary?.downgradeWatch ?? null,
    warroomValidationPenalty: health.optionalResults.warroomValidation?.payload?.summary?.penalty ?? null,
    warroomValidationMissingData: health.optionalResults.warroomValidation?.payload?.summary?.missingData ?? null,
    warroomValidationAddedPredictions: health.optionalResults.warroomValidation?.payload?.addedPredictions ?? null,
    warroomValidationAddedResults: health.optionalResults.warroomValidation?.payload?.addedResults ?? null,
    dailyWikiPublishRequiredNow: Boolean(health.optionalResults.dailyWikiPublish?.requiredNow),
    dailyWikiReviewPublished: Boolean(health.optionalResults.dailyWikiPublish?.reviewPublished),
    dailyWikiTradePublished: Boolean(health.optionalResults.dailyWikiPublish?.tradePublished),
    dailyWikiReviewPath: health.optionalResults.dailyWikiPublish?.reviewWiki ?? null,
    dailyWikiTradePath: health.optionalResults.dailyWikiPublish?.tradeWiki ?? null,
    dailyWikiAuditPath: health.optionalResults.dailyWikiPublish?.audit ?? null,
    dplusAutofillSkipped: Boolean(health.optionalResults.dplusAutofill?.skipped),
    dplusAutofillPendingChecked: health.optionalResults.dplusAutofill?.pendingChecked ?? null,
    dplusAutofillResolved: health.optionalResults.dplusAutofill?.resolved ?? null,
    dplusAutofillAdded: health.optionalResults.dplusAutofill?.added ?? null,
    dplusAutofillExistingResolvedDue: health.optionalResults.dplusAutofill?.existingResolvedDue ?? null,
    dplusAutofillMissing: health.optionalResults.dplusAutofill?.missing ?? null,
    dplusResolvedCount: health.optionalResults.dplusOverview?.resolvedCount ?? null,
    dplusOverduePendingCount: health.optionalResults.dplusOverview?.overduePendingCount ?? null,
    dplusDueTodayCount: health.optionalResults.dplusOverview?.dueTodayCount ?? null,
    dplusFuturePendingCount: health.optionalResults.dplusOverview?.futurePendingCount ?? null,
    dplusMonthlyPredictionCount: health.optionalResults.dplusMonthlyDashboard?.predictionCount ?? null,
    dplusMonthlyResultCount: health.optionalResults.dplusMonthlyDashboard?.resultCount ?? null,
    dplusMonthlyTotal: health.optionalResults.dplusMonthlyDashboard?.monthTotal ?? null,
    dplusMonthlyStrictHitRate: health.optionalResults.dplusMonthlyDashboard?.strictHitRate ?? null,
    dplusMonthlyUsableRate: health.optionalResults.dplusMonthlyDashboard?.usableRate ?? null,
    dplusMonthlyFailRate: health.optionalResults.dplusMonthlyDashboard?.failRate ?? null,
    dplusMonthlyAvgRelativeToSH: health.optionalResults.dplusMonthlyDashboard?.avgRelativeToSH ?? null,
    dplusMonthlyReport: health.optionalResults.dplusMonthlyDashboard?.outputs?.md ?? null,
    dplusMonthlyChart: health.optionalResults.dplusMonthlyDashboard?.outputs?.svg ?? null,
    feishuNotifyPending: health.optionalResults.feishuPendingNotifications?.payload?.pending ?? null,
    feishuNotifySent: Array.isArray(health.optionalResults.feishuPendingNotifications?.payload?.sent)
      ? health.optionalResults.feishuPendingNotifications.payload.sent.length
      : null,
    aiContextUpdated: Boolean(health.optionalResults.aiContextUpdate?.ok),
    aiContextDate: health.optionalResults.aiContextUpdate?.date ?? null,
    imageOcrReady: Boolean(health.optionalResults.imageOcr?.ok),
    imageOcrEngine: health.optionalResults.imageOcr?.engine ?? "",
    activeYouziSourceCount: health.optionalResults.youziLearningStatus?.activeSourceCount ?? null,
    activeYouziSources: health.optionalResults.youziLearningStatus?.activeSources ?? [],
    activeYouziCandidateFiles: health.optionalResults.youziLearningStatus?.activeCandidateFiles ?? null,
    activeYouziStateItems: health.optionalResults.youziLearningStatus?.activeStateItems ?? null,
    activeYouziLearningLag: health.optionalResults.youziLearningStatus?.activeLearningLag ?? null,
    youziLearningStateItems: health.optionalResults.youziLearningStatus?.stateItems ?? null,
    youziOcrActiveFiles: health.optionalResults.youziLearningStatus?.ocrActiveFiles ?? null,
    youziOcrSectionFiles: health.optionalResults.youziLearningStatus?.ocrSectionFiles ?? null,
    raw09ShortlineFiles: health.optionalResults.youziLearningStatus?.raw09Files ?? null,
    raw09FeishuFiles: health.optionalResults.youziLearningStatus?.raw09FeishuFiles ?? null,
    raw09YouziFiles: health.optionalResults.youziLearningStatus?.raw09YouziFiles ?? null,
    raw09OcrFiles: health.optionalResults.youziLearningStatus?.raw09OcrFiles ?? null,
    raw09ManualFiles: health.optionalResults.youziLearningStatus?.raw09ManualFiles ?? null,
    legacyYouziFiles: health.optionalResults.youziLearningStatus?.legacyYouziFiles ?? null,
    legacyInactiveYouziFiles: health.optionalResults.youziLearningStatus?.legacyInactiveFiles ?? null,
    moduleOk,
  }
}

function finalizeHealth(health, startedAtMs) {
  const previous = readJson(HEALTH_PATH, {})
  health.finishedAt = nowLocalTimestamp()
  health.durationMs = Date.now() - startedAtMs
  health.summary = buildSummary(health)
  health.ok = Object.values(health.summary.moduleOk).every(Boolean)
  health.failureStreak = health.ok ? 0 : Number(previous.failureStreak ?? 0) + 1
  health.alerts = []
  if (health.failureStreak >= 2) {
    health.alerts.push({
      level: "red",
      code: "consecutive_failures",
      message: `Cloud data connector failed ${health.failureStreak} consecutive runs.`,
    })
  }
  if (health.durationMs > 12 * 60 * 1000) {
    health.alerts.push({
      level: "red",
      code: "duration_over_12_minutes",
      message: `Cloud data connector duration ${health.durationMs}ms exceeded 12 minutes.`,
    })
  }
  if ((health.summary.subscriptions ?? 0) > 0 && (health.summary.updatedSubscriptions ?? 0) === 0) {
    health.alerts.push({
      level: "red",
      code: "werss_update_zero",
      message: "WeRSS subscription update touched 0 accounts.",
    })
  }
  if ((health.summary.werssUpdateFailedCount ?? 0) > 0) {
    health.alerts.push({
      level: "yellow",
      code: "werss_partial_mp_update_failed",
      message: `WeRSS ${health.summary.werssUpdateFailedCount} subscriptions failed this round: ${(health.summary.werssUpdateFailedMps ?? []).map((item) => item.mpName || item.mpId).join("、")}`,
    })
  }
  if (!health.summary.imageOcrReady) {
    health.alerts.push({
      level: "yellow",
      code: "image_ocr_engine_missing",
      message: "Image OCR policy is configured, but rapidocr_onnxruntime is not installed.",
    })
  }
  if ((health.summary.activeYouziSourceCount ?? 0) === 0) {
    health.alerts.push({
      level: "yellow",
      code: "active_youzi_source_empty",
      message: "No active local WeRSS/URL-seed sources are classified as 游资心得.",
    })
  }
  if ((health.summary.activeYouziLearningLag ?? 0) > 3) {
    health.alerts.push({
      level: "yellow",
      code: "active_youzi_learning_lag",
      message: `Active Youzi learning state is behind by ${health.summary.activeYouziLearningLag} files.`,
    })
  }
  health.statusColor = health.alerts.some((alert) => alert.level === "red")
    ? "red"
    : health.alerts.length > 0 || !health.ok
      ? "yellow"
      : "green"
  return health
}

function main() {
  const startedAtMs = Date.now()
  const startedAt = nowLocalTimestamp()
  const lock = acquireRunLock()
  if (!lock.acquired) {
    const health = {
      schema: "73wiki-cloud-data-connectors-health-v1",
      projectRoot: PROJECT_ROOT,
      startedAt,
      finishedAt: nowLocalTimestamp(),
      durationMs: 0,
      ok: true,
      skipped: true,
      skipReason: "locked",
      statusColor: "yellow",
      lock: lock.lock,
      lockAgeMs: lock.ageMs,
      alerts: [
        {
          level: "yellow",
          code: "run_locked",
          message: "Previous connector run is still active; this interval was skipped.",
        },
      ],
      results: {},
      optionalResults: {},
      summary: {
        moduleOk: {},
      },
    }
    writeJson(HEALTH_PATH, health)
    appendLog(JSON.stringify({ at: health.finishedAt, ok: true, skipped: true, reason: "locked", lockAgeMs: lock.ageMs }))
    console.log(JSON.stringify(health, null, 2))
    return
  }

  const requiredFiles = checkRequiredFiles()
  const missing = Object.entries(requiredFiles).filter(([, info]) => !info.exists)

  const health = {
    schema: "73wiki-cloud-data-connectors-health-v1",
    projectRoot: PROJECT_ROOT,
    startedAt,
    finishedAt: null,
    ok: false,
    requiredFiles,
    results: {},
    optionalResults: {},
  }

  if (missing.length > 0) {
    health.error = `Missing required files: ${missing.map(([key]) => key).join(", ")}`
    finalizeHealth(health, startedAtMs)
    writeJson(HEALTH_PATH, health)
    appendLog(JSON.stringify({ at: health.finishedAt, ok: false, error: health.error }))
    console.log(JSON.stringify(health, null, 2))
    process.exitCode = 1
    lock.release()
    return
  }

  try {
    health.results.csCailian = runCsCailian()
    health.results.tencentMarket = runTencentMarket()
    health.results.thsHotlist = runThsHotlist()
    health.optionalResults.thsHotlistMovers = runThsHotlistMovers()
    health.optionalResults.werssMpsUpdate = runWerssMpsUpdate()
    health.optionalResults.werssApiIngest = runWerssApiIngest()
    health.optionalResults.mpHotTop10 = runMpHotTop10Extraction()
    health.optionalResults.wechatMpSeeds = runWechatMpSeeds()
    health.optionalResults.rawQueueScan = runRawQueueScan()
    health.optionalResults.rawQueueIngest = runRawQueueIngest()
    health.optionalResults.catalystRadar = runCatalystRadar()
    health.optionalResults.warroomValidation = runWarroomValidation()
    health.optionalResults.dailyWikiPublish = runDailyWikiPublishAudit()
    health.optionalResults.dplusOverviewPrepare = runDplusOverview()
    health.optionalResults.dplusAutofill = runDplusAutofill()
    health.optionalResults.dplusOverview = runDplusOverview()
    health.optionalResults.dplusMonthlyDashboard = runDplusMonthlyDashboard()
    health.optionalResults.feishuPendingNotifications = runFeishuPendingNotifications()
    health.optionalResults.aiContextUpdate = runAiContextUpdate()
    health.optionalResults.imageOcr = probeImageOcr()
    health.optionalResults.youziLearningStatus = probeYouziLearningStatus(health.optionalResults.werssMpsUpdate?.mpNames)
    health.optionalResults.localWechatBizArticles = probeLocalWechatBizArticles()
    finalizeHealth(health, startedAtMs)
  } catch (error) {
    health.error = String(error?.stack ?? error?.message ?? error)
    finalizeHealth(health, startedAtMs)
    health.ok = false
    health.statusColor = "red"
    health.alerts.push({
      level: "red",
      code: "connector_exception",
      message: String(error?.message ?? error),
    })
  } finally {
    writeJson(HEALTH_PATH, health)
    appendLog(JSON.stringify({
      at: health.finishedAt,
      ok: health.ok,
      statusColor: health.statusColor,
      durationMs: health.durationMs,
      subscriptions: health.summary?.subscriptions ?? null,
      werssUpdatedMps: health.summary?.updatedSubscriptions ?? null,
      werssNewArticleTotal: health.summary?.newArticleTotal ?? null,
      werssNewArticles: health.summary?.new_articles ?? null,
      werssFetchedArticles: health.summary?.fetched_articles ?? null,
      urlSeedOk: health.summary?.urlSeedOk ?? null,
      urlSeedTotal: health.summary?.urlSeedTotal ?? null,
      thsHotlistCapturedRows: health.summary?.thsHotlistCapturedRows ?? null,
      thsHotlistImportedRows: health.summary?.thsHotlistImportedRows ?? null,
      thsHotlistComplete: health.summary?.thsHotlistComplete ?? null,
      thsHotlistSkipped: health.summary?.thsHotlistSkipped ?? null,
      thsHotlistNextDueAt: health.summary?.thsHotlistNextDueAt ?? null,
      thsHotlistMoversTracked: health.summary?.thsHotlistMoversTracked ?? null,
      thsHotlistMoversWithDirectReason: health.summary?.thsHotlistMoversWithDirectReason ?? null,
      thsHotlistMoversWithLocalEvidence: health.summary?.thsHotlistMoversWithLocalEvidence ?? null,
      mpHotTop10Records: health.summary?.mpHotTop10Records ?? null,
      mpHotTop10Platforms: health.summary?.mpHotTop10Platforms ?? null,
      rawQueueNewFiles: health.summary?.rawQueueNewFiles ?? null,
      rawQueueProcessed: health.summary?.rawQueueProcessed ?? null,
      rawQueueRegistryAdded: health.summary?.rawQueueRegistryAdded ?? null,
      catalystRadarTopScore: health.summary?.catalystRadarTopScore ?? null,
      catalystRadarNotifyFresh: health.summary?.catalystRadarNotifyFresh ?? null,
      catalystRadarNotifyCreated: health.summary?.catalystRadarNotifyCreated ?? null,
      warroomValidationCandidates: health.summary?.warroomValidationCandidates ?? null,
      warroomValidationPenalty: health.summary?.warroomValidationPenalty ?? null,
      warroomValidationMissingData: health.summary?.warroomValidationMissingData ?? null,
      dplusAutofillAdded: health.summary?.dplusAutofillAdded ?? null,
      dplusAutofillExistingResolvedDue: health.summary?.dplusAutofillExistingResolvedDue ?? null,
      dplusAutofillMissing: health.summary?.dplusAutofillMissing ?? null,
      dplusOverduePendingCount: health.summary?.dplusOverduePendingCount ?? null,
      dplusDueTodayCount: health.summary?.dplusDueTodayCount ?? null,
      dplusMonthlyStrictHitRate: health.summary?.dplusMonthlyStrictHitRate ?? null,
      dplusMonthlyUsableRate: health.summary?.dplusMonthlyUsableRate ?? null,
      dplusMonthlyFailRate: health.summary?.dplusMonthlyFailRate ?? null,
      feishuNotifyPending: health.summary?.feishuNotifyPending ?? null,
      feishuNotifySent: health.summary?.feishuNotifySent ?? null,
      aiContextUpdated: health.summary?.aiContextUpdated ?? null,
      aiContextDate: health.summary?.aiContextDate ?? null,
      activeYouziSourceCount: health.summary?.activeYouziSourceCount ?? null,
      activeYouziCandidateFiles: health.summary?.activeYouziCandidateFiles ?? null,
      activeYouziStateItems: health.summary?.activeYouziStateItems ?? null,
      activeYouziLearningLag: health.summary?.activeYouziLearningLag ?? null,
      youziOcrActiveFiles: health.summary?.youziOcrActiveFiles ?? null,
      youziOcrSectionFiles: health.summary?.youziOcrSectionFiles ?? null,
      raw09FeishuFiles: health.summary?.raw09FeishuFiles ?? null,
      raw09YouziFiles: health.summary?.raw09YouziFiles ?? null,
      raw09OcrFiles: health.summary?.raw09OcrFiles ?? null,
      raw09ManualFiles: health.summary?.raw09ManualFiles ?? null,
      legacyYouziFiles: health.summary?.legacyYouziFiles ?? null,
      legacyInactiveYouziFiles: health.summary?.legacyInactiveYouziFiles ?? null,
      alerts: health.alerts,
    }))
    console.log(JSON.stringify(health, null, 2))
    lock.release()
  }
  if (!health.ok) process.exitCode = 1
}

main()
