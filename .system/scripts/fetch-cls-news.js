// fetch-cls-news.js - Fetch 财联社 telegraph news
const https = require('https');
const fs = require('fs');
const path = require('path');

const PROJECT_ROOT = process.env.WIKI_PROJECT_PATH || '/Users/qixinchaye/wiki/73神话';

function fetch(url, encoding, postData) {
  return new Promise((resolve, reject) => {
    const options = {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.cls.cn/telegraph',
      }
    };
    if (postData) {
      options.method = 'POST';
      options.headers['Content-Type'] = 'application/json';
    }
    
    const req = https.request(url, options, (res) => {
      const chunks = [];
      res.on('data', (d) => chunks.push(d));
      res.on('end', () => {
        const buf = Buffer.concat(chunks);
        try { resolve(buf.toString(encoding || 'utf8')); } catch(e) { resolve(buf.toString('utf8')); }
      });
      res.on('error', reject);
    }).on('error', reject);

    if (postData) req.write(typeof postData === 'string' ? postData : JSON.stringify(postData));
    req.end();
  });
}

async function main() {
  const ts = new Date().toISOString().replace(/[:.]/g, '-').substring(0, 16);
  const lines = [];
  lines.push('# 财联社电报 ' + ts);
  lines.push('');

  // Try the API
  try {
    const apiResp = await fetch('https://www.cls.cn/v1/roll/get_roll_list', 'utf8', {
      app: 'CailianpressWeb',
      os: 'web',
      sv: '8.4.6',
      type: 'telegraph'
    });

    const data = JSON.parse(apiResp);
    if (data.data && data.data.roll_data) {
      const items = data.data.roll_data;
      lines.push('> 共 ' + items.length + ' 条电报 | 显示前 25 条');
      lines.push('');
      
      items.slice(0, 25).forEach((item, i) => {
        const time = item.ctime ? new Date(item.ctime * 1000).toTimeString().substring(0, 8) : '';
        const title = (item.title || '').replace(/<[^>]+>/g, '');
        const brief = (item.brief || '').replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ');

        lines.push('### ' + (i+1) + '. [' + time + '] ' + title);
        lines.push('');
        if (brief && brief !== title) {
          lines.push(brief);
          lines.push('');
        }
        if (item.shareurl) {
          lines.push('> [原文链接](https://www.cls.cn' + item.shareurl + ')');
        }
        lines.push('');
        lines.push('---');
        lines.push('');
      });
    } else {
      throw new Error('Unexpected API format');
    }
  } catch (e) {
    // Fallback: scrape HTML page
    lines.push('> API 不可用，使用HTML抓取');
    lines.push('');
    
    try {
      const html = await fetch('https://www.cls.cn/telegraph', 'utf8');
      const text = html.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
                       .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
                       .replace(/<[^>]+>/g, ' ')
                       .replace(/&nbsp;/g, ' ')
                       .replace(/\s+/g, ' ')
                       .substring(0, 4000);
      lines.push('```');
      lines.push(text);
      lines.push('```');
    } catch (e2) {
      lines.push('Both API and HTML failed');
    }
  }

  lines.push('');
  lines.push('---');
  lines.push('> Source: cls.cn | Generated: ' + new Date().toISOString());

  const outDir = path.join(PROJECT_ROOT, 'raw', '市场快报');
  fs.mkdirSync(outDir, { recursive: true });
  const outPath = path.join(outDir, 'cailian-' + ts.replace(/[:]/g, '') + '.md');
  fs.writeFileSync(outPath, lines.join('\n'), 'utf8');
  console.log('OK: ' + outPath);
}

main().catch(e => console.error(e));
