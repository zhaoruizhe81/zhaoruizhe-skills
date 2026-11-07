/**
 * 知网 GetExport 签名算法 — 逆向自 createSign (my.cnki.net/realNameOauthDialog/js/common.js, 运行时真身)
 *
 * signature = md5( timestamp + nonce + SALT + sortedParams + Ecp_ClientId ).replace(/ /g,'')
 *   - timestamp : Date.now() 毫秒
 *   - nonce     : Math.sin(timestamp).toString().substr(6)
 *   - SALT      : t8b52yrsoyx66f35tk0p4nubrmrcglv5
 *   - sortedParams : URL query 参数按 key 小写序排序后 key=value 直接拼接(无分隔符, 值 decodeURIComponent)
 *   - Ecp_ClientId : cookie 原值
 */
const crypto = require('crypto');
const md5 = s => crypto.createHash('md5').update(s, 'binary').digest('hex');
const SALT = 't8b52yrsoyx66f35tk0p4nubrmrcglv5';

function buildSortedParams(queryObj) {
  const keys = Object.keys(queryObj).sort((a, b) => {
    const la = a.toLowerCase(), lb = b.toLowerCase();
    return la > lb ? 1 : (la < lb ? -1 : 0);
  });
  let out = '';
  for (const k of keys) out += k + '=' + decodeURIComponent(queryObj[k]);
  return out;
}

function createSign(queryObj) {
  const timestamp = Date.now();
  const nonce = Math.sin(timestamp).toString().substr(6);
  const paramStr = buildSortedParams(queryObj);
  const signature = md5((timestamp + nonce + SALT + paramStr + process.env.CNKI_CLIENT_ID).replace(/ /g, ''));
  return {
    timestamp: String(timestamp),
    nonce,
    signature,
    appID: 'LoginWap',
    ClientID: process.env.CNKI_CLIENT_ID,
  };
}

module.exports = { createSign, buildSortedParams, md5, SALT };

// 自验: 已知向量
if (require.main === module) {
  process.env.CNKI_CLIENT_ID = '050d739758cfed64030bc099ba2f552b0VHhoyTYfe';
  const { buildSortedParams: b, md5: m } = module.exports;
  const input = ('17914805320008639184792063' + 't8b52yrsoyx66f35tk0p4nubrmrcglv5' +
    b({ lid: 'TESTLID123', page: '1', pageSize: '1', sendType: '1', messageType: '1' }) +
    '050d739758cfed64030bc099ba2f552b0VHhoyTYfe').replace(/ /g, '');
  console.log('自验:', m(input) === 'e91fe1cd44ba56b00bc88e1e9e9d8a5f' ? 'PASS ✅' : 'FAIL ❌');
}
