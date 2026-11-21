'use strict';
/*
 * hook_common_apis.js — Windows 用户态 API 行为探针（Frida）
 *
 * 用法（在 Windows 靶场内，frida 位数须与样本一致）：
 *   spawn  模式: frida -f sample.exe -l hook_common_apis.js
 *   attach 模式: frida -n <进程名> -l hook_common_apis.js
 *   frida-server 远程模式: 宿主 frida -H <靶场IP> -f sample.exe -l hook_common_apis.js
 *
 * 说明：
 *  - 输出经 send() 送达 frida CLI 控制台
 *  - ws2_32/winhttp/wininet 等库可能滞后加载：初始未命中的 hook 会挂起，
 *    每次 LoadLibrary 后自动补挂（installPending）
 *  - 遵循 Frida 官方 JS API（Module.findExportByName / Interceptor.attach）
 *    已通过 node --check 语法校验；端到端行为需在靶场验证
 */

const MAX_STR = 120;
const hooked = {};          // 已挂成功的 API 名集合
const pending = [];         // 库未加载而挂起的钩子

function wstr(p) { try { return p.readUtf16String(MAX_STR); } catch (e) { return null; } }
function astr(p) { try { return p.readCString(MAX_STR); } catch (e) { return null; } }
function hex(n) { return '0x' + (n >>> 0).toString(16); }

// sockaddr_in -> "a.b.c.d:port"（端口为网络序）
function sockaddrToIPv4(p) {
  try {
    const fam = p.readU16();
    if (fam !== 2) return 'af=' + fam;
    const port = (p.add(2).readU8() << 8) | p.add(3).readU8();
    return p.add(4).readU8() + '.' + p.add(5).readU8() + '.' +
           p.add(6).readU8() + '.' + p.add(7).readU8() + ':' + port;
  } catch (e) { return null; }
}

function log(api, detail) { send('[' + api + '] ' + detail); }

/* ---- 各 API 的 onEnter 处理器（args 下标与 MSDN 参数序一致，从 0 起） ---- */
const HOOKS = [
  // 文件
  ['kernel32.dll', 'CreateFileW', function (args) {
    log('CreateFileW', 'path=' + wstr(args[0]) + ' access=' + hex(args[1].toInt32()));
  }],
  ['kernel32.dll', 'WriteFile', function (args) {
    log('WriteFile', 'hFile=' + hex(args[0].toInt32()) + ' bytes=' + args[2].toInt32());
  }],

  // 注册表（持久化观测）
  ['advapi32.dll', 'RegSetValueExW', function (args) {
    log('RegSetValueExW', 'value=' + wstr(args[1]) + ' type=' + args[3].toInt32() +
        ' data=' + astr(args[4]));
  }],
  ['advapi32.dll', 'RegCreateKeyExW', function (args) {
    log('RegCreateKeyExW', 'subkey=' + wstr(args[1]));
  }],

  // 进程（执行/注入观测）
  ['kernel32.dll', 'CreateProcessW', function (args) {
    log('CreateProcessW', 'app=' + wstr(args[0]) + ' cmd=' + wstr(args[1]));
  }],
  ['kernel32.dll', 'WinExec', function (args) {
    log('WinExec', 'cmd=' + astr(args[0]));
  }],
  ['kernel32.dll', 'WriteProcessMemory', function (args) {
    log('WriteProcessMemory', 'hProc=' + hex(args[0].toInt32()) +
        ' base=' + args[1] + ' bytes=' + args[3].toInt32());
  }],
  ['kernel32.dll', 'VirtualAllocEx', function (args) {
    log('VirtualAllocEx', 'hProc=' + hex(args[0].toInt32()) + ' size=' + args[2].toInt32() +
        ' protect=' + hex(args[4].toInt32()));
  }],
  ['kernel32.dll', 'CreateRemoteThread', function (args) {
    log('CreateRemoteThread', 'hProc=' + hex(args[0].toInt32()) +
        ' start=' + args[4]);
  }],
  ['kernel32.dll', 'LoadLibraryExW', function (args) {
    log('LoadLibraryExW', 'dll=' + wstr(args[0]));
  }],
  ['kernel32.dll', 'LoadLibraryW', function (args) {
    log('LoadLibraryW', 'dll=' + wstr(args[0]));
  }],

  // 网络
  ['ws2_32.dll', 'connect', function (args) {
    log('connect', 'dest=' + sockaddrToIPv4(args[1]));
  }],
  ['ws2_32.dll', 'send', function (args) {
    log('send', 'sock=' + hex(args[0].toInt32()) + ' bytes=' + args[2].toInt32());
  }],
  ['winhttp.dll', 'WinHttpConnect', function (args) {
    log('WinHttpConnect', 'host=' + wstr(args[1]) + ' port=' + args[2].toInt32());
  }],
  ['wininet.dll', 'InternetOpenUrlW', function (args) {
    log('InternetOpenUrlW', 'url=' + wstr(args[1]));
  }],

  // 用户态钩子/键盘记录
  ['user32.dll', 'SetWindowsHookExW', function (args) {
    log('SetWindowsHookExW', 'idHook=' + args[0].toInt32() + ' mod=' + hex(args[2].toInt32()));
  }],
  ['user32.dll', 'GetAsyncKeyState', function (args) {
    log('GetAsyncKeyState', 'vk=' + hex(args[0].toInt32()));
  }],

  // 外壳执行
  ['shell32.dll', 'ShellExecuteW', function (args) {
    log('ShellExecuteW', 'op=' + wstr(args[1]) + ' file=' + wstr(args[2]) + ' arg=' + wstr(args[3]));
  }],

  // 加密（勒索行为观测；只记录尺寸不记录内容）
  ['advapi32.dll', 'CryptEncrypt', function (args) {
    log('CryptEncrypt', 'hKey=' + hex(args[0].toInt32()) + ' inlen=' + args[5].toInt32());
  }],
];

/* ---- 安装逻辑：命中的记入 hooked，未命中的进 pending 等库加载后补挂 ---- */
function tryInstall(hook) {
  const lib = hook[0], name = hook[1], onEnter = hook[2];
  if (hooked[name]) return;
  const addr = Module.findExportByName(lib, name) || Module.findExportByName(null, name);
  if (addr) {
    try {
      Interceptor.attach(addr, { onEnter: onEnter });
      hooked[name] = true;
      send('[probe] hooked ' + name + ' @ ' + addr);
    } catch (e) {
      send('[probe] FAILED hook ' + name + ': ' + e);
    }
  } else {
    pending.push(hook);   // 库还没加载
  }
}

function installAll() {
  const rest = pending.splice(0, pending.length);
  rest.forEach(tryInstall);
}

HOOKS.forEach(tryInstall);
send('[probe] initial hooks=' + Object.keys(hooked).length +
     ' pending=' + pending.length + ' total=' + HOOKS.length);
