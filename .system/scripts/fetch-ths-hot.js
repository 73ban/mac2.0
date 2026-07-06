// fetch-ths-hot.js - Fetch 同花顺 concept board hot data
const https = require('https');
const fs = require('fs');
const path = require('path');

const PROJECT_ROOT = process.env.WIKI_PROJECT_PATH || '/Users/qixinchaye/wiki/73神话';

function fetch(url, encoding) {
  return new Promise((resolve, reject) => {
    https.get(url, {headers: {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}}, (res) => {
      const chunks = [];
      res.on('data', (d) => chunks.push(d));
      res.on('end', () => {
        const buf = Buffer.concat(chunks);
        try { resolve(buf.toString(encoding || 'utf8')); } catch(e) { resolve(buf.toString('utf8')); }
      });
      res.on('error', reject);
    }).on('error', reject);
  });
}

async function main() {
  const ts = new Date().toISOString().replace(/[:.]/g, '-').substring(0, 16);
  const lines = [];
  lines.push('# 同花顺市场热点 ' + ts);
  lines.push('');

  // 1. Fetch concept board page
  const gnHtml = await fetch('https://q.10jqka.com.cn/gn/', 'gbk');
  
  // Extract concept board links and changes
  // Pattern: concept items with name, code, change%
  const itemPattern = /<tr[^>]*>[\s\S]*?<td[^>]*>[\s\S]*?<a[^>]*href="\/gn\/detail\/(\d+)\/"[^>]*>([^<]+)<\/a>[\s\S]*?<td[^>]*class="[^"]*c-rise[^"]*"[^>]*>([^<]+)<\/td>[\s\S]*?<\/tr>/gi;
  const items = [];
  let match;
  
  // Alternative: simpler extraction
  const linkPattern = /<a[^>]*href="\/gn\/detail\/(\d+)\/"[^>]*>([^<]+)<\/a>/g;
  const links = [];
  while ((match = linkPattern.exec(gnHtml)) !== null) {
    links.push({code: match[1], name: match[2].trim()});
  }
  
  // Get market overview from main page
  const mainHtml = await fetch('https://q.10jqka.com.cn/', 'gbk');
  
  // Extract stock count data from the main page
  lines.push('## 概念板块列表');
  lines.push('');
  lines.push('| # | 板块名称 | 代码 |');
  lines.push('|---|---|---|');
  
  const uniqueLinks = links.filter((l, i, arr) => arr.findIndex(x => x.code === l.code) === i).slice(0, 20);
  uniqueLinks.forEach((l, i) => {
    lines.push('| ' + (i+1) + ' | ' + l.name + ' | ' + l.code + ' |');
  });

  // Also try to get the board data page
  lines.push('');
  lines.push('## 热门概念板块 (涨幅榜)');
  lines.push('');
  
  const boardHtml = await fetch('https://q.10jqka.com.cn/index/index/board/all/field/zdf/order/desc/page/1/ajax/1/', 'gbk');
  
  // Parse the board table - it has tr/td structure
  const trPattern = /<tr[^>]*>([\s\S]*?)<\/tr>/gi;
  const rows = [];
  while ((match = trPattern.exec(boardHtml)) !== null) {
    const row = match[1];
    const tdPattern = /<td[^>]*>([\s\S]*?)<\/td>/gi;
    const cells = [];
    let tdMatch;
    while ((tdMatch = tdPattern.exec(row)) !== null) {
      cells.push(tdMatch[1].replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim());
    }
    if (cells.length >= 3 && cells[1] && /\d/.test(cells[1])) {
      rows.push(cells);
    }
  }
  
  if (rows.length > 0) {
    lines.push('| # | 代码 | 名称 | 现价 | 涨幅% | 涨跌 | 换手% | 量比 | 振幅% | 成交额 | 流通市值 | 市盈率 |');
    lines.push('|---|---|---|---|---|---|---|---|---|---|---|');
    rows.slice(0, 15).forEach((cells, i) => {
      const display = cells.slice(0, 11);
      while (display.length < 11) display.push('-');
      lines.push('| ' + (i+1) + ' | ' + display.join(' | ') + ' |');
    });
  } else {
    // Fallback: show raw snippet
    lines.push('(Table parsing returned 0 rows - showing raw snippet)');
    lines.push('');
    lines.push('```');
    lines.push(boardHtml.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').substring(0, 1000));
    lines.push('```');
  }

  lines.push('');
  lines.push('---');
  lines.push('> Source: 10jqka.com.cn | Generated: ' + new Date().toISOString());

  const outDir = path.join(PROJECT_ROOT, 'raw', '市场快报');
  fs.mkdirSync(outDir, { recursive: true });
  const outPath = path.join(outDir, 'tonghuashun-' + ts.replace(/[:]/g, '') + '.md');
  fs.writeFileSync(outPath, lines.join('\n'), 'utf8');
  console.log('OK: ' + outPath);
  console.log('Concept boards: ' + uniqueLinks.length + ', Market rows: ' + rows.length);
}

main().catch(e => console.error(e));
