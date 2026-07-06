#!/usr/bin/env node
import crypto from "node:crypto"
import fs from "node:fs"
import https from "node:https"
import path from "node:path"
import { fileURLToPath } from "node:url"

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url))
const PROJECT_ROOT = path.resolve(process.env.WIKI_PROJECT_PATH ?? path.join(SCRIPT_DIR, "../.."))
const SEEDS_PATH = path.resolve(process.env.WECHAT_MP_SEEDS_PATH ?? path.join(PROJECT_ROOT, ".system/wechat-mp-url-seeds.json"))
const STATE_PATH = path.resolve(process.env.WECHAT_MP_STATE_PATH ?? path.join(PROJECT_ROOT, ".system/wechat-mp-url-seeds-state.json"))
const RAW_MP_ROOT = path.join(PROJECT_ROOT, "raw/05-研报新闻/公众号")
const RAW_ROOT = path.join(RAW_MP_ROOT, "URL直抓")
const HTML_BACKUP_ROOT = path.join(PROJECT_ROOT, ".system/raw-html-backup/公众号-url直抓")
const SOURCE_CLASS_PATH = path.join(PROJECT_ROOT, ".system/wechat-mp-source-classes.json")

const DROP_QUERY_KEYS = new Set([
  "scene",
  "subscene",
  "sessionid",
  "clicktime",
  "enterid",
  "chksm",
  "from",
  "source",
  "share",
  "sharer_shareinfo",
  "sharer_shareinfo_first",
  "mpshare",
  "mpshare1",
  "mpshare2",
  "mpshare3",
  "wx_header",
  "exportkey",
  "acctmode",
])

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true })
}

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"))
  } catch {
    return fallback
  }
}

function writeJson(file, value) {
  ensureDir(path.dirname(file))
  fs.writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`, "utf8")
}

function sha256(text) {
  return crypto.createHash("sha256").update(String(text ?? ""), "utf8").digest("hex")
}

function sha1(text) {
  return crypto.createHash("sha1").update(String(text ?? ""), "utf8").digest("hex")
}

function canonicalizeMpUrl(url) {
  const text = decodeHtml(String(url ?? "").trim())
  if (!/^https?:\/\//i.test(text)) return text
  try {
    const parsed = new URL(text)
    for (const key of [...parsed.searchParams.keys()]) {
      if (DROP_QUERY_KEYS.has(key)) parsed.searchParams.delete(key)
    }
    parsed.hash = ""
    parsed.protocol = parsed.protocol.toLowerCase()
    parsed.hostname = parsed.hostname.toLowerCase()
    parsed.pathname = parsed.pathname.replace(/\/{2,}/g, "/").replace(/\/$/, "") || "/"
    return parsed.toString()
  } catch {
    return text
  }
}

function parseFrontmatter(text) {
  const match = String(text ?? "").match(/^---\n([\s\S]*?)\n---\n?([\s\S]*)$/)
  if (!match) return [{}, String(text ?? "")]
  const meta = {}
  for (const line of match[1].split(/\r?\n/)) {
    const pair = line.match(/^([A-Za-z0-9_-]+):\s*(.*)$/)
    if (!pair) continue
    let value = pair[2].trim()
    try {
      if ((value.startsWith("\"") && value.endsWith("\"")) || (value.startsWith("'") && value.endsWith("'"))) {
        value = JSON.parse(value)
      }
    } catch {}
    meta[pair[1]] = String(value ?? "")
  }
  return [meta, match[2] ?? ""]
}

function listMarkdownFiles(dir, out = []) {
  if (!fs.existsSync(dir)) return out
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (!entry.name.endsWith("_assets")) listMarkdownFiles(full, out)
    } else if (entry.isFile() && entry.name.endsWith(".md")) {
      out.push(full)
    }
  }
  return out
}

function markdownContentHash(title, source, publishDate, body) {
  return sha256(JSON.stringify({
    title,
    source,
    publishDate,
    contentText: String(body ?? "").trim(),
  }))
}

function dedupeCompositeKey(title, source, publishDate, contentHash) {
  return [
    String(source ?? "").trim().toLowerCase(),
    String(title ?? "").replace(/\s+/g, " ").trim().toLowerCase(),
    String(publishDate ?? "").trim(),
    String(contentHash ?? "").trim(),
  ].join("|")
}

function loadExistingRawArticles() {
  const byUrl = new Map()
  const byComposite = new Map()
  for (const file of listMarkdownFiles(RAW_MP_ROOT)) {
    try {
      const text = fs.readFileSync(file, "utf8")
      const [meta, body] = parseFrontmatter(text)
      const sourceUrl = canonicalizeMpUrl(meta.source_url ?? "")
      const title = meta.title ?? ""
      const source = meta.source ?? path.basename(path.dirname(file))
      const publishDate = meta.created ?? meta.date ?? ""
      const contentHash = meta.content_hash || meta.source_hash || markdownContentHash(title, source, publishDate, body)
      const item = {
        path: file,
        relPath: path.relative(PROJECT_ROOT, file),
        sourceUrl,
        title,
        source,
        publishDate,
        contentHash,
      }
      if (sourceUrl && !byUrl.has(sourceUrl)) byUrl.set(sourceUrl, item)
      const composite = dedupeCompositeKey(title, source, publishDate, contentHash)
      if (!byComposite.has(composite)) byComposite.set(composite, item)
    } catch {}
  }
  return { byUrl, byComposite }
}

function markdownQuality(file) {
  try {
    const text = fs.readFileSync(file, "utf8")
    const [meta, body] = parseFrontmatter(text)
    const cleanBody = String(body ?? "")
      .replace(/^# .+$/m, "")
      .replace(/^- .+$/gm, "")
      .replace(/\s+/g, "")
    return {
      exists: true,
      title: meta.title ?? "",
      bodyLength: cleanBody.length,
      contentHash: meta.content_hash ?? "",
    }
  } catch {
    return { exists: false, title: "", bodyLength: 0, contentHash: "" }
  }
}

function articleQuality(article) {
  const title = String(article?.title ?? "").trim()
  const bodyLength = String(article?.contentText ?? "").replace(/\s+/g, "").length
  const titleMissing = !title || title === "未命名公众号文章"
  const bodyMissing = bodyLength < 80
  return { titleMissing, bodyMissing, bodyLength }
}

function shouldKeepExistingRaw(article, rawPath) {
  const incoming = articleQuality(article)
  if (!incoming.titleMissing && !incoming.bodyMissing) return false
  const existing = markdownQuality(rawPath)
  if (!existing.exists) return false
  if (existing.bodyLength >= 80 && !["", "未命名公众号文章"].includes(existing.title)) return true
  return Boolean(existing.contentHash && (incoming.titleMissing || incoming.bodyMissing))
}

function loadSourceProfiles() {
  const config = readJson(SOURCE_CLASS_PATH, {})
  const defaults = config.default ?? {}
  const classes = config.classes ?? {}
  const sources = config.sources ?? {}
  return { defaults, classes, sources }
}

function sourceProfile(sourceName, profiles) {
  const sourceClass = profiles.sources?.[sourceName] ?? profiles.defaults?.source_class ?? "市场情绪"
  return {
    source_class: sourceClass,
    ...(profiles.defaults ?? {}),
    ...(profiles.classes?.[sourceClass] ?? {}),
  }
}

function nowText(date = new Date()) {
  const pad = (n) => String(n).padStart(2, "0")
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

function dateText(date = new Date()) {
  const pad = (n) => String(n).padStart(2, "0")
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function decodeHtml(text) {
  return String(text ?? "")
    .replace(/&#x([0-9a-fA-F]+);/g, (_, hex) => String.fromCodePoint(Number.parseInt(hex, 16)))
    .replace(/&#(\d+);/g, (_, dec) => String.fromCodePoint(Number.parseInt(dec, 10)))
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, "\"")
    .replace(/&#39;/g, "'")
}

function decodeJsString(text) {
  return decodeHtml(String(text ?? "")
    .replace(/\\x([0-9a-fA-F]{2})/g, (_, hex) => String.fromCharCode(Number.parseInt(hex, 16)))
    .replace(/\\u([0-9a-fA-F]{4})/g, (_, hex) => String.fromCodePoint(Number.parseInt(hex, 16)))
    .replace(/\\'/g, "'")
    .replace(/\\"/g, "\"")
    .replace(/\\\\/g, "\\"))
}

function stripTagsToText(html) {
  return decodeHtml(String(html ?? "")
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(p|div|section|article|h\d|li|tr|blockquote)>/gi, "\n")
    .replace(/<(h1|h2|h3)[^>]*>/gi, "\n## ")
    .replace(/<li[^>]*>/gi, "\n- ")
    .replace(/<[^>]+>/g, ""))
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
}

function safeName(value, fallback = "未命名公众号") {
  const text = String(value || fallback)
    .replace(/[<>:"/\\|?*\x00-\x1F]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
  return (text || fallback).slice(0, 80)
}

function pick(html, patterns, decoder = decodeHtml) {
  for (const pattern of patterns) {
    const match = html.match(pattern)
    if (match) return decoder(match[1]).replace(/\s+/g, " ").trim()
  }
  return ""
}

function extractArticle(html, url, seed = {}) {
  const title = pick(html, [
    /<meta\s+property=["']og:title["']\s+content=["']([\s\S]*?)["']\s*\/?>/i,
    /<h1[^>]*id=["']activity-name["'][^>]*>([\s\S]*?)<\/h1>/i,
    /var\s+msg_title\s*=\s*'([\s\S]*?)'\.html/i,
    /var\s+msg_title\s*=\s*"([\s\S]*?)"/i,
  ], (value) => stripTagsToText(decodeJsString(value)))
  const nickname = pick(html, [
    /var\s+nickname\s*=\s*htmlDecode\("([\s\S]*?)"\)/i,
    /id=["']js_name["'][^>]*>([\s\S]*?)<\/a>/i,
    /class=["'][^"']*profile_nickname[^"']*["'][^>]*>([\s\S]*?)<\/strong>/i,
  ], (value) => stripTagsToText(decodeJsString(value))) || seed.source || ""
  const userName = pick(html, [/var\s+user_name\s*=\s*"([\s\S]*?)"/i], decodeJsString)
  const biz = pick(html, [/var\s+biz\s*=\s*"([\s\S]*?)"/i, /biz:\s*"([^"]+)"/i], decodeJsString)
  const mid = pick(html, [/var\s+mid\s*=\s*"([^"]*)"/i, /mid:\s*"([^"]+)"/i], decodeJsString)
  const idx = pick(html, [/var\s+idx\s*=\s*"([^"]*)"/i, /idx:\s*"([^"]+)"/i], decodeJsString)
  const sn = pick(html, [/var\s+sn\s*=\s*"([\s\S]*?)"/i, /sn:\s*"([^"]+)"/i], decodeJsString)
  const ct = pick(html, [/var\s+ct\s*=\s*"?(.*?)"?;/i], decodeJsString)
  const publishDate = /^\d+$/.test(ct) ? dateText(new Date(Number(ct) * 1000)) : dateText()
  const contentHtml = html.match(/<div[^>]+id=["']js_content["'][\s\S]*?<\/div>/i)?.[0]
    ?? html.match(/content_noencode:\s*'([\s\S]*?)'\s*,/i)?.[1]
    ?? ""
  const contentText = stripTagsToText(decodeJsString(contentHtml))
  const sourceUrl = url
  return {
    title: title || "未命名公众号文章",
    nickname: nickname || "未命名公众号",
    userName,
    biz,
    mid,
    idx,
    sn,
    ct,
    publishDate,
    sourceUrl,
    contentText,
  }
}

function fetchText(url, redirects = 0) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
      },
      timeout: 30000,
    }, (res) => {
      const location = res.headers.location
      if ([301, 302, 303, 307, 308].includes(res.statusCode) && location && redirects < 5) {
        res.resume()
        resolve(fetchText(new URL(location, url).toString(), redirects + 1))
        return
      }
      const chunks = []
      res.on("data", (chunk) => chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)))
      res.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")))
    })
    req.on("timeout", () => req.destroy(new Error("request timeout")))
    req.on("error", reject)
  })
}

function articleKey(article, url) {
  return [article.biz, article.mid, article.idx, article.sn].filter(Boolean).join(":") || sha1(url)
}

function findPreviousByUrl(state, url) {
  return Object.values(state?.seen ?? {}).find((item) => item?.url === url) ?? null
}

function articleMarkdown(article, htmlHash, contentHash, htmlBackupPath, profile) {
  return `---
title: ${JSON.stringify(article.title)}
created: ${article.publishDate}
updated: ${dateText()}
type: 公众号原文
source: ${JSON.stringify(article.nickname)}
source_url: ${JSON.stringify(article.sourceUrl)}
source_hash: ${htmlHash}
content_hash: ${contentHash}
preferred_ingestor: codex
ingested_by: codex
capture_pipeline: wechat_mp_url_seed
source_class: ${JSON.stringify(profile.source_class ?? "市场情绪")}
truth_grade: ${profile.truth_grade ?? "S3"}
use_grade: ${profile.use_grade ?? "reference"}
trade_impact: ${profile.trade_impact ?? "medium"}
ocr_policy: ${profile.ocr_policy ?? "text_first"}
deepseek_action: skip
fate: C
---

# ${article.title}

- 来源：${article.nickname}
- 公众号ID：${article.userName || "未知"}
- biz：${article.biz || "未知"}
- 原链接：${article.sourceUrl}
- 发布时间：${article.publishDate}
- 来源分层：${profile.source_class ?? "市场情绪"}
- 使用等级：${profile.use_grade ?? "reference"}
- 交易影响：${profile.trade_impact ?? "medium"}
- OCR策略：${profile.ocr_policy ?? "text_first"}
- RAW HTML 备份：${htmlBackupPath}
- 内容 hash：${htmlHash}
- 正文 hash：${contentHash}

---

${article.contentText || "未提取到正文。"}
`
}

async function main() {
  const seeds = readJson(SEEDS_PATH, []).filter((item) => item?.enabled !== false && item?.url)
  const state = readJson(STATE_PATH, { seen: {}, runs: [] })
  const sourceProfiles = loadSourceProfiles()
  const existingRaw = loadExistingRawArticles()
  const results = []

  for (const seed of seeds) {
    try {
      const html = await fetchText(seed.url)
      const article = extractArticle(html, seed.url, seed)
      const key = articleKey(article, seed.url)
      const htmlHash = sha256(html)
      const contentHash = sha256(JSON.stringify({
        title: article.title,
        source: article.nickname,
        publishDate: article.publishDate,
        contentText: article.contentText,
      }))
      const profile = sourceProfile(article.nickname, sourceProfiles)
      const sourceDir = path.join(RAW_ROOT, safeName(article.nickname, safeName(seed.source, "未命名公众号")))
      const fileName = `${article.publishDate}_${sha1(key).slice(0, 12)}.md`
      const legacyPrevious = state.seen[key] ? null : findPreviousByUrl(state, seed.url)
      const previous = state.seen[key] ?? legacyPrevious
      let rawPath = previous?.rawPath ? path.join(PROJECT_ROOT, previous.rawPath) : path.join(sourceDir, fileName)
      const htmlBackupPath = path.join(HTML_BACKUP_ROOT, `${article.publishDate}_${sha1(key).slice(0, 12)}.html`)
      const canonicalSourceUrl = canonicalizeMpUrl(article.sourceUrl)
      const duplicateByUrl = canonicalSourceUrl ? existingRaw.byUrl.get(canonicalSourceUrl) : null
      const duplicateByComposite = existingRaw.byComposite.get(dedupeCompositeKey(
        article.title,
        article.nickname,
        article.publishDate,
        contentHash,
      ))
      const duplicate = duplicateByUrl || duplicateByComposite || null
      const duplicateElsewhere = Boolean(duplicate?.path && path.resolve(duplicate.path) !== path.resolve(rawPath))
      const dedupeReason = duplicate
        ? duplicateByUrl
          ? "source_url"
          : "source_title_publish_date_content_hash"
        : ""
      if (!previous && duplicateElsewhere) {
        rawPath = duplicate.path
      }
      if (shouldKeepExistingRaw(article, rawPath)) {
        const previousState = previous ?? {
          title: article.title,
          source: article.nickname,
          url: seed.url,
          rawPath: path.relative(PROJECT_ROOT, rawPath),
          htmlHash,
          contentHash,
        }
        state.seen[key] = {
          ...previousState,
          lastFetchedAt: nowText(),
          qualitySkippedAt: nowText(),
          qualitySkipReason: "incoming_article_low_quality",
        }
        results.push({
          ok: true,
          url: seed.url,
          title: previousState.title,
          source: previousState.source ?? article.nickname,
          key,
          written: false,
          changed: false,
          dedupe: duplicateElsewhere ? dedupeReason : null,
          qualitySkipped: true,
          rawPath: path.relative(PROJECT_ROOT, rawPath),
        })
        continue
      }
      const changed = Boolean(previous?.contentHash && previous.contentHash !== contentHash)
      const shouldWrite = !duplicateElsewhere && (!fs.existsSync(rawPath) || changed)

      if (shouldWrite) {
        ensureDir(path.dirname(rawPath))
        ensureDir(path.dirname(htmlBackupPath))
        fs.writeFileSync(htmlBackupPath, html, "utf8")
        fs.writeFileSync(rawPath, articleMarkdown(article, htmlHash, contentHash, path.relative(PROJECT_ROOT, htmlBackupPath), profile), "utf8")
        const item = {
          path: rawPath,
          relPath: path.relative(PROJECT_ROOT, rawPath),
          sourceUrl: canonicalSourceUrl,
          title: article.title,
          source: article.nickname,
          publishDate: article.publishDate,
          contentHash,
        }
        if (canonicalSourceUrl) existingRaw.byUrl.set(canonicalSourceUrl, item)
        existingRaw.byComposite.set(dedupeCompositeKey(article.title, article.nickname, article.publishDate, contentHash), item)
      }

      state.seen[key] = {
        title: article.title,
        source: article.nickname,
        url: seed.url,
        rawPath: path.relative(PROJECT_ROOT, rawPath),
        htmlHash,
        contentHash,
        dedupe: duplicateElsewhere ? dedupeReason : undefined,
        lastFetchedAt: nowText(),
      }
      results.push({
        ok: true,
        url: seed.url,
        title: article.title,
        source: article.nickname,
        key,
        written: shouldWrite,
        changed,
        dedupe: duplicateElsewhere ? dedupeReason : null,
        rawPath: path.relative(PROJECT_ROOT, rawPath),
      })
    } catch (error) {
      results.push({
        ok: false,
        url: seed.url,
        error: String(error?.message ?? error),
      })
    }
  }

  state.runs = [...(state.runs ?? []), { at: nowText(), results }].slice(-30)
  writeJson(STATE_PATH, state)
  const ok = results.every((item) => item.ok)
  console.log(JSON.stringify({ ok, seeds: seeds.length, results }, null, 2))
  if (!ok) process.exitCode = 1
}

main()
