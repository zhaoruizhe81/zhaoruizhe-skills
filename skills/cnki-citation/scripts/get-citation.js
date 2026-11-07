#!/usr/bin/env node
/**
 * 知网引文获取 CLI（纯 HTTP，无需浏览器）
 *
 * 用法:
 *   node get-citation.js <文献filename或CNKI文章链接> [格式...]
 *
 * 示例:
 *   node get-citation.js kd9kqNkOM8Xyu_MccKCQ5AM1UHjV0uMR_icN4IXwgif...
 *   node get-citation.js "https://kns.cnki.net/kcms2/article/abstract?v=..." GB/T 7714
 *
 * 格式可选: GBTREFER(GB/T 7714-2025) REFER(CAJ-CD) MLA APA BibTex EndNote NoteExpress Refworks
 * 默认: GBTREFER,MLA,APA
 *
 * filename 来源: 检索结果页 kns.cnki.net/kns8s/... 每条结果 checkbox 的 value,
 * 或 "CNKI AI阅读" 链接里 cid= 参数的值。
 */
const https = require('https');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { createSign } = require('./sign');

/*
 * 会话策略(实测结论):
 *  - GetExport 不要求登录(LID 可缺),但要求"已过风控的会话"
 *  - 首选: CNKI_COOKIE 环境变量 或 --cookie "<完整document.cookie>"
 *    (从已登录/已过验证的浏览器 DevTools 里复制, Playwright 流程可自动导出)
 *  - 次选: 本地 .clientid + 首页预热 —— 仅在 IP 未被盯上时有效,
 *    裸新会话会被 302 到 blockPuzzle 滑块验证, 那一步需要真浏览器
 */
function getSessionCookie() {
  const argIdx = process.argv.indexOf('--cookie');
  if (argIdx > -1 && process.argv[argIdx + 1]) return process.argv[argIdx + 1];
  if (process.env.CNKI_COOKIE) return process.env.CNKI_COOKIE;
  const file = path.join(__dirname, '.cookie');
  if (fs.existsSync(file)) return fs.readFileSync(file, 'utf8').trim();
  return null;
}

// Ecp_ClientId 是签名组成部分; 优先从会话 cookie 里取, 否则用本地持久化值
function getClientId(cookieStr) {
  const fromCookie = (cookieStr || '').match(/Ecp_ClientId=([^;]+)/);
  if (fromCookie) return fromCookie[1];
  const file = path.join(__dirname, '.clientid');
  if (fs.existsSync(file)) return fs.readFileSync(file, 'utf8').trim();
  const id = crypto.randomBytes(16).toString('hex') +
    Array.from({ length: 9 }, () => 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'[crypto.randomInt(62)]).join('');
  fs.writeFileSync(file, id);
  return id;
}

const COOKIE = getSessionCookie();
process.env.CNKI_CLIENT_ID = getClientId(COOKIE);

const FORMAT_MAP = {
  'GB/T 7714': 'GBTREFER', 'gbt': 'GBTREFER', 'GBTREFER': 'GBTREFER',
  'CAJ-CD': 'REFER', 'REFER': 'REFER',
  'MLA': 'MLA', 'APA': 'APA',
  'BibTex': 'BibTex', 'bibtex': 'BibTex',
  'EndNote': 'EndNote', 'NoteExpress': 'NoteExpress', 'Refworks': 'Refworks',
};

function extractFilename(input) {
  if (!input.includes('/')) return input.trim();
  const m = input.match(/[?&](?:cid|filename)=([A-Za-z0-9_\-]+)/);
  if (m) return m[1];
  throw new Error('无法从链接中提取 filename，请直接传入文献 ID');
}

function getExport(filename, modes) {
  const body = new URLSearchParams({ filename, displaymode: modes, uniplatform: 'NZKPT', language: 'CHS' }).toString();
  const headers = createSign({});
  const payload = Buffer.from(body, 'utf8');
  return new Promise((resolve, reject) => {
    const req = https.request({
      hostname: 'kns.cnki.net', path: '/dm8/API/GetExport', method: 'POST',
      headers: {
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'content-length': payload.length,
        'x-requested-with': 'XMLHttpRequest',
        'origin': 'https://kns.cnki.net',
        'referer': 'https://kns.cnki.net/',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36',
        ...(COOKIE ? { cookie: COOKIE } : {}),
        ...headers,
      },
    }, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        try {
          const j = JSON.parse(data);
          j.code === 1 ? resolve(j.data) : reject(new Error(`接口返回 code=${j.code}: ${j.msg}`));
        } catch { reject(new Error('响应非 JSON: ' + data.slice(0, 200))); }
      });
    });
    req.on('error', reject);
    req.write(payload);
    req.end();
  });
}

async function main() {
  const input = process.argv[2];
  if (!input) { console.error(require('fs').readFileSync(__filename, 'utf8').split('*/')[0]); process.exit(1); }
  const modes = (process.argv.slice(3).length ? process.argv.slice(3) : ['GBTREFER', 'MLA', 'APA'])
    .map(f => FORMAT_MAP[f] || f).join(',');
  const filename = extractFilename(input);
  const results = await getExport(filename, modes);
  for (const r of results) {
    console.log(`【${r.key}】`);
    for (const v of r.value) console.log(v.replace(/<br>/g, '').trim(), '\n');
  }
}

main().catch(e => { console.error('出错:', e.message); process.exit(1); });
