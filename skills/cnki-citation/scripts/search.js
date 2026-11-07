#!/usr/bin/env node
/**
 * 知网检索 CLI —— 关键词 → 文献列表 → (可选)批量引文落盘
 *
 * 用法:
 *   node search.js "深度学习"                     # 检索第1页(20条), 打印列表
 *   node search.js "深度学习" 3                   # 检索前3页(60条)
 *   node search.js "深度学习" --json              # 机器可读输出
 *   node search.js "深度学习" --field TKA         # 按篇名检索(SU主题/TKA篇名/KY关键词/AB摘要/AU作者)
 *   node search.js "深度学习" --sort 被引         # 排序: 相关度|发表时间|被引|下载
 *
 * 查论文→引论文 闭环:
 *   node search.js "深度学习" --top 5 --cite 'GB/T 7714' --out refs.txt
 *     → 检索, 取前5篇, 逐篇拉引文(2.5s/篇限速), 追加写入 refs.txt
 *
 * 频控红线(实测): brief/grid 短间隔连续请求必触发图形验证码(且状态粘性,
 * 等待无法解除, 需浏览器人工过验)。翻页间隔内置 20-30 秒随机; 引文
 * 2-3 秒/篇(该接口风控松)。翻多页请保持耐心, 或浏览器翻页+单页爬取交替。
 *
 * 会话: 与 get-citation.js 共用 .cookie 文件(浏览器过验会话); 检索页/接口的
 * Set-Cookie 会话性 cookie(KNS2COOKIE 等)由内置 jar 自动接收合并, 不回写文件。
 */
const https = require('https');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36';
const CLASSID = 'WD0FTY92'; // 总库
const FIELD_MAP = {
  SU: '主题', TKA: '篇名', KY: '关键词', AB: '摘要', AU: '作者',
  LY: '来源', FT: '全文', FI: '基金',
};
const SORT_MAP = { 相关度: ['', ''], 发表时间: ['PT', 'DESC'], 被引: ['CF', 'DESC'], 下载: ['DFR', 'DESC'] };

function loadSessionCookie() {
  const file = path.join(__dirname, '.cookie');
  if (fs.existsSync(file)) return fs.readFileSync(file, 'utf8').trim();
  if (process.env.CNKI_COOKIE) return process.env.CNKI_COOKIE;
  return null;
}
function getClientId(cookieStr) {
  const m = (cookieStr || '').match(/Ecp_ClientId=([^;]+)/);
  if (m) return m[1];
  const file = path.join(__dirname, '.clientid');
  if (fs.existsSync(file)) return fs.readFileSync(file, 'utf8').trim();
  const id = crypto.randomBytes(16).toString('hex') +
    Array.from({ length: 9 }, () => 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'[crypto.randomInt(62)]).join('');
  fs.writeFileSync(file, id);
  return id;
}

// ---- 带 cookie jar 的 http 封装: 收集服务端会话 cookie 并在后续请求回传 ----
function makeSession(baseCookie) {
  const jar = new Map();
  if (baseCookie) for (const kv of baseCookie.split('; ')) {
    const i = kv.indexOf('=');
    if (i > 0) jar.set(kv.slice(0, i), kv.slice(i + 1));
  }
  function cookieHeader() {
    return [...jar.entries()].map(([k, v]) => `${k}=${v}`).join('; ');
  }
  function absorb(res) {
    for (const sc of (res.headers['set-cookie'] || [])) {
      const kv = sc.split(';')[0];
      const i = kv.indexOf('=');
      if (i > 0) jar.set(kv.slice(0, i), kv.slice(i + 1));
    }
  }
  function request(hostname, p, { method = 'GET', body = null, referer = null } = {}) {
    return new Promise((resolve, reject) => {
      const headers = { 'user-agent': UA, cookie: cookieHeader() };
      if (referer) headers.referer = referer;
      if (body) {
        headers['content-type'] = 'application/x-www-form-urlencoded; charset=UTF-8';
        headers['content-length'] = Buffer.byteLength(body);
        headers['x-requested-with'] = 'XMLHttpRequest';
      }
      const req = https.request({ hostname, path: p, method, headers }, res => {
        absorb(res);
        let data = '';
        res.on('data', c => data += c);
        res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body: data }));
      });
      req.on('error', reject);
      if (body) req.write(body);
      req.end();
    });
  }
  return { request, jar };
}

// ---- 检索 ----
function buildQueryJson(kw, field) {
  return JSON.stringify({
    Platform: '', Resource: 'CROSSDB', Classid: CLASSID, Products: '',
    QNode: { QGroup: [{ Key: 'Subject', Title: '', Logic: 0, Items: [{ Field: field, Value: kw, Operator: 'TOPRANK', Logic: 0, Vector: '', Title: FIELD_MAP[field] }], ChildItems: [] }] },
    ExScope: 1, SimpTrad: '0', SearchType: 2, Rlang: 'CHINESE',
    KuaKuCode: 'YSTT4HG0,LSTPFY1C,EMRPGLPA,JUP3MUPD,MPMFIG1A,WQ0UVIAA,BLZOG7CK,PWFIRAGL,NN3FJMUV,NLBO1Z6R',
    Expands: {}, View: 'changeDBCh', SearchFrom: 1,
  });
}

async function search(session, kw, { field = 'SU', page = 1, pageSize = 20, sort = '相关度' } = {}) {
  const searchPath = `/kns8s/defaultresult/index?classid=${CLASSID}&korder=${field}&kw=${encodeURIComponent(kw)}`;
  // 步骤1: 访问检索页建立上下文(服务端种 KNS2COOKIE 等会话 cookie)
  const home = await session.request('kns.cnki.net', searchPath);
  if (home.status >= 300 && home.status < 400 && /verify|captcha/.test(home.headers.location || '')) {
    throw new Error('会话被风控拦截(滑块验证)。请刷新 .cookie: 浏览器打开知网任意页面 → DevTools 复制 document.cookie');
  }
  // 步骤2: POST brief/grid 拿结果(无需签名)
  const [sortField, sortType] = SORT_MAP[sort] || ['', ''];
  const form = new URLSearchParams({
    boolSearch: 'true',
    QueryJson: buildQueryJson(kw, field),
    pageNum: String(page),
    pageSize: String(pageSize),
    sortField, sortType,
    dstyle: 'listmode',
    productStr: '',
    aside: `(${FIELD_MAP[field]}：${kw})`,
    searchFrom: '资源范围：总库',
    subject: '', language: '', uniplatform: '',
    CurPage: String(page),
  });
  const res = await session.request('kns.cnki.net', '/kns8s/brief/grid', {
    method: 'POST', body: form.toString(),
    referer: 'https://kns.cnki.net' + searchPath,
  });
  if (res.body.includes('vericodeForm')) {
    throw new Error('触发知网频控(图形验证码)。请等待几分钟冷却; 或在浏览器里正常翻一页检索结果(人工过验)后重试, 并换新的 .cookie');
  }
  return parseGrid(res.body);
}

// ---- 解析 brief/grid 的 HTML 片段(固定服务端模板, 零依赖解析) ----
const stripTags = h => h
  .replace(/<!--[\s\S]*?-->/g, '')   // 服务端模板注释残留
  .replace(/<[^>]*>/g, '')
  .replace(/&amp;/g, '&').replace(/&nbsp;/g, ' ').trim();

function parseGrid(html) {
  const total = (html.match(/<em>([\d,]+)<\/em>/) || [])[1] || '?';
  const maxPage = (html.match(/data-pagenum="(\d+)"/) || [])[1] || '?';
  const items = [];
  const trRe = /<tr>\s*<td class="seq">([\s\S]*?)<\/td>\s*<\/tr>/g;
  let m;
  while ((m = trRe.exec(html)) !== null) {
    const row = m[0];
    const grab = cls => {
      const r = new RegExp(`<td class=['"]${cls}['"][^>]*>([\\s\\S]*?)</td>`).exec(row);
      return r ? r[1] : '';
    };
    const id = (grab('seq').match(/value="([^"]+)"/) || [])[1] || '';
    const plainId = (grab('operat').match(/data-filename="([^"]+)"/) || [])[1] || '';
    const dbname = (grab('operat').match(/data-dbname="([^"]+)"/) || [])[1] || '';
    const nameCell = grab('name')
      .replace(/<i class="freeIdent[^>]*>[^<]*<\/i>/g, '')   // "免费"角标
      .replace(/<B class="marktip">[^<]*<\/B>/g, '');          // "网络首发"标记
    const title = stripTags(nameCell);
    const abstractUrl = (nameCell.match(/href="([^"]+kcms2[^"]+)"/) || [])[1] || '';
    const authors = [...row.matchAll(/<td class=['"]author['"][^>]*>([\s\S]*?)<\/td>/g)]
      .flatMap(mm => [...mm[1].matchAll(/>([^<>]+)<\/a>/g)].map(a => a[1].trim()));
    const source = stripTags(grab('source'));
    const date = stripTags(grab('date'));
    const dbtype = stripTags(grab('data'));
    const quoted = stripTags(grab('quote')).replace(/[^0-9]/g, '') || '0';
    const downloaded = stripTags(grab('download')).replace(/[^0-9]/g, '') || '0';
    if (id || plainId) items.push({ id, plainId, dbname, title, authors, source, date, dbtype, cited: quoted, downloads: downloaded, abstractUrl });
  }
  return { total, maxPage, items };
}

// ---- 闭环: 批量取引文(与 get-citation.js 同款逻辑, 内联避免重构) ----
const { createSign } = require('./sign');
function getExport(filename, modes, cookie) {
  const payload = Buffer.from(new URLSearchParams({ filename, displaymode: modes, uniplatform: 'NZKPT', language: 'CHS' }).toString());
  return new Promise((resolve, reject) => {
    const req = https.request({
      hostname: 'kns.cnki.net', path: '/dm8/API/GetExport', method: 'POST',
      headers: {
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'content-length': payload.length,
        'x-requested-with': 'XMLHttpRequest',
        'origin': 'https://kns.cnki.net',
        'referer': 'https://kns.cnki.net/',
        'user-agent': UA,
        ...(cookie ? { cookie } : {}),
        ...createSign({}),
      },
    }, res => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        try {
          const j = JSON.parse(data);
          j.code === 1 ? resolve(j.data) : reject(new Error(`code=${j.code} ${j.msg || ''}`));
        } catch { reject(new Error('响应非JSON: ' + data.slice(0, 100))); }
      });
    });
    req.on('error', reject);
    req.write(payload);
    req.end();
  });
}
const sleep = ms => new Promise(r => setTimeout(r, ms));

// ---- main ----
async function main() {
  const argv = process.argv.slice(2);
  const bools = ['--json'].filter(f => argv.includes(f));
  const getArg = (name) => { const i = argv.indexOf(name); return i > -1 ? argv[i + 1] : null; };
  const kw = argv.find(a => !a.startsWith('--') && isNaN(Number(a)));
  if (!kw) { console.error('用法: node search.js "关键词" [页数] [--json] [--field SU] [--sort 被引]\n       node search.js "关键词" --top 5 --cite \'GB/T 7714\' --out refs.txt'); process.exit(1); }
  const valuedOpts = ['--field', '--sort', '--top', '--cite', '--out'];
  const pageCandidate = argv.find((a, i) => /^\d+$/.test(a) && !(valuedOpts.includes(argv[i - 1])));
  const pages = Math.min(Number(pageCandidate || 1), 15);
  const field = (getArg('--field') || 'SU').toUpperCase();
  const sort = getArg('--sort') || '相关度';
  const topN = Number(getArg('--top') || 0);
  const citeFmt = getArg('--cite');
  const outFile = getArg('--out');

  const cookie = loadSessionCookie();
  process.env.CNKI_CLIENT_ID = getClientId(cookie);
  const session = makeSession(cookie);

  console.error(`检索: ${FIELD_MAP[field]}="${kw}" 第1-${pages}页 排序:${sort} ...`);
  let all = [];
  let meta = { total: '?', maxPage: '?' };
  for (let p = 1; p <= pages; p++) {
    const { total, maxPage, items } = await search(session, kw, { field, page: p, sort });
    meta = { total, maxPage };
    all = all.concat(items);
    if (items.length === 0) break;
    if (p < pages) await sleep(20000 + Math.random() * 10000);
  }
  console.error(`共 ${meta.total} 条结果(可翻 ${meta.maxPage} 页), 本次取得 ${all.length} 条\n`);

  if (bools.includes('--json')) {
    console.log(JSON.stringify({ total: meta.total, maxPage: meta.maxPage, items: all }, null, 2));
  } else {
    all.forEach((it, i) => {
      console.log(`${String(i + 1).padStart(3)}. ${it.title}`);
      console.log(`     ${it.authors.join(', ')} | ${it.source} | ${it.date} | ${it.dbtype} | 被引:${it.cited}`);
      console.log(`     id: ${it.plainId || it.id}`);
    });
  }

  // 闭环: 检索 → top N → 引文落盘
  if (citeFmt && topN > 0) {
    const fmtMap = { 'GB/T 7714': 'GBTREFER', gbt: 'GBTREFER', APA: 'APA', MLA: 'MLA', BibTex: 'BibTex', EndNote: 'EndNote', NoteExpress: 'NoteExpress', Refworks: 'Refworks' };
    const mode = fmtMap[citeFmt] || citeFmt;
    const picked = all.slice(0, topN);
    console.error(`\n拉取前 ${picked.length} 篇引文(${mode})...`);
    const lines = [];
    for (const [i, it] of picked.entries()) {
      try {
        const data = await getExport(it.id, mode, cookie);
        for (const d of data) for (const v of d.value) {
          const line = v.replace(/<br>/g, '').trim().replace(/^\[\d+\]\s*/, '');
          lines.push(`[${i + 1}] ${line}`);
          console.error(`  ${i + 1}/${picked.length} ✓ ${it.title.slice(0, 30)}...`);
        }
      } catch (e) {
        console.error(`  ${i + 1}/${picked.length} ✗ ${it.title.slice(0, 30)}... (${e.message})`);
      }
      await sleep(2000 + Math.random() * 1000);
    }
    const output = lines.join('\n') + '\n';
    if (outFile) {
      fs.appendFileSync(outFile, output);
      console.error(`\n已追加写入 ${outFile} (${lines.length} 行)`);
    } else {
      console.log('\n' + output);
    }
  }
}

main().catch(e => { console.error('出错:', e.message); process.exit(1); });
