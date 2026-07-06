#!/usr/bin/env node
import { createRequire } from 'module';

const require = createRequire(import.meta.url);
const { chromium } = require('/Users/qixinchaye/.codex/skills/playwright-ths-hotlist/node_modules/playwright');

function parseRows(text, code, name) {
  const rows = [];
  const lines = text.split(/\n+/).map((x) => x.trim()).filter(Boolean);
  const marker = new RegExp(`${name || ''}\\s*\\[${code}\\].*?(\\d{4}-\\d{2}-\\d{2})`);
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const match = line.match(marker);
    if (!match) continue;
    const question = lines[i + 1] || '';
    if (!question || question.length < 8) continue;
    rows.push({
      平台: '深交所互动易',
      股票代码: code,
      股票名称: name,
      问答ID: '',
      问题时间: match[1],
      回复时间: '',
      投资者问题: question,
      公司回复原文: '',
      原始链接: `https://irm.cninfo.com.cn/ircs/search?keyword=${encodeURIComponent(name || code)}`,
    });
  }
  return rows;
}

async function main() {
  if (process.argv[2] === '--batch') {
    const input = await new Promise((resolve) => {
      let data = '';
      process.stdin.setEncoding('utf8');
      process.stdin.on('data', (chunk) => { data += chunk; });
      process.stdin.on('end', () => resolve(data));
    });
    const stocks = JSON.parse(input || '[]');
    const browser = await chromium.launch({ headless: true });
    const results = [];
    try {
      const page = await browser.newPage({
        userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36',
      });
      for (const stock of stocks) {
        const code = stock['股票代码'] || stock.code || '';
        const name = stock['股票名称'] || stock.name || code;
        if (!code) continue;
        try {
          const url = `https://irm.cninfo.com.cn/ircs/search?keyword=${encodeURIComponent(name || code)}`;
          await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
          await page.waitForTimeout(1200);
          const text = await page.locator('body').innerText({ timeout: 10000 });
          const rows = parseRows(text, code, name).slice(0, Number(stock.limit || 20));
          results.push({ code, name, ok: true, rows, url });
        } catch (error) {
          results.push({ code, name, ok: false, rows: [], error: String(error && error.message || error) });
        }
      }
      console.log(JSON.stringify({ ok: true, results }, null, 2));
    } finally {
      await browser.close();
    }
    return;
  }

  const code = process.argv[2] || '';
  const name = process.argv[3] || code;
  const limit = Number(process.argv[4] || 20);
  if (!code) {
    console.log(JSON.stringify({ ok: false, rows: [], error: 'missing code' }));
    return;
  }
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({
      userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36',
    });
    const url = `https://irm.cninfo.com.cn/ircs/search?keyword=${encodeURIComponent(name || code)}`;
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1800);
    const text = await page.locator('body').innerText({ timeout: 10000 });
    const rows = parseRows(text, code, name).slice(0, limit);
    console.log(JSON.stringify({ ok: true, rows, url }, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.log(JSON.stringify({ ok: false, rows: [], error: String(error && error.message || error) }, null, 2));
  process.exit(0);
});
