#!/Users/zhaoruizhe/miniconda3/bin/python3
"""pt.py — 远程场景·Mac 端遥控器：发一条驱动命令、轮询 gui.log、上传脚本、拉回截图。
（名字沿用首次实战项目；本质与 Packet Tracer 无关。本机直跑场景用不到本文件。）

用法:
  pt.py step <local.py> [shot]         # ★原子步进一轮: push 脚本 → send 执行 → pull 截图
                                       #   触发前自动删远端同名旧图 + 落地校验 PNG（拉旧图防住）
  pt.py send <cmd> [args...]           # 经计划任务桥跑一条驱动命令，等 DONE/FAIL
  pt.py push <local.py>                # 上传脚本到 PC 的 <auto>/scripts/
  pt.py pushdir <local_dir>            # 上传整个目录（保留相对路径，跳过 __pycache__/.pyc/点文件）
  pt.py pull <shotname> [shotname...]  # 下载 <auto>/shots/*.png 到本地截图目录（校验 PNG 完整性）
  pt.py gc                             # 手动归档截图目录（超 200MB 打包 tar.gz，证据不丢）
  pt.py log [n]                        # tail gui.log

截图默认落 ~/.zcode/window-use/shots（skill 外；WGUI_MAC_SHOTS 可换）。
每轮 pull 后自动归档：目录超 200MB（WGUI_SHOTS_MAX_MB 可调）就把最旧的打包进
shots-archive/*.tar.gz 并删原图；skill 目录内一律拒绝落图（172MB 实付教训）。

全局选项必须放子命令之前（子命令后的 -xxx 会被 REMAINDER 吞成位置参数，已改为直接报错）:
  --host <ssh主机名>  --task <计划任务名>  --auto <PC端工作目录>
  --remote-base <Git Bash路径>  --shots <本地截图目录>  --timeout <秒>

默认参数对准当前已部署的 PC（windowpc / PtGuiBridge / ptauto），换机器时覆盖。

可靠性契约（2026-11-05 强化，配套新版 win_gui_driver）:
  - 同一台 Mac 同时只跑一个 pt.py（本地锁 /tmp/window-use-pt.lock）
  - 触发前清空 gui.log 并回读确认为空，清不空直接 FAIL（陈旧 DONE 假成功堵死在源头）
  - schtasks /run 本身的失败会被检测（exit code），不再静默空轮询 240s
  - 触发命令不重试（远端可能已执行，重试=二次点击）
  - 参数经 shlex.quote 转义，含引号/反斜杠路径安全
  - 驱动被占（上个实例没退）时立刻报 "FAIL busy"，不再干等超时
"""
import sys, os, time, subprocess, json, argparse, shlex, atexit

if any(x in ("-h", "--help", "help") for x in sys.argv[1:]):
    print(__doc__); sys.exit(0)

SKILL = os.path.expanduser("~/.zcode/skills/ssh-skill/scripts/ssh_skill.py")
PY = os.path.expanduser("~/miniconda3/bin/python3")
SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(os.path.join(SKILL_ROOT, "scripts")):
    sys.path.insert(0, os.path.join(SKILL_ROOT, "scripts"))
try:
    import shots_gc                          # scripts/shots_gc.py，截图自动归档
except Exception:
    shots_gc = None                          # 脚本不在时 GC 静默跳过，不影响遥控

ap = argparse.ArgumentParser(add_help=False)
ap.add_argument("--host", default="windowpc")
ap.add_argument("--task", default="PtGuiBridge")
ap.add_argument("--auto", default="ptauto")                      # PC 端 home 相对路径
ap.add_argument("--remote-base", default="/c/Users/master/ptauto")
ap.add_argument("--shots", default=None)
ap.add_argument("--timeout", type=int, default=240,
                help="send 轮询预算(秒)。任务启动延迟 20~25s + 命令时长; "
                     "慢命令(服务启停/软件冷启动/大 UIA 查询)请加大")
ap.add_argument("cmd", nargs=argparse.REMAINDER)
a = ap.parse_args()
# 截图默认落 skill 外的固定目录。老版默认 cwd/shots，而 agent 干活总在 skill 根目录
# （文档让 cd 进去 grep），172MB 证据图因此沉淀进知识库（2026-11-05 实付）。
# 即便显式传 --shots，落在 skill 目录内也一律重定向——skill 只存代码与文档。
DEFAULT_SHOTS = os.environ.get("WGUI_MAC_SHOTS") or os.path.expanduser(
    "~/.zcode/window-use/shots")
MAC_SHOTS = a.shots or DEFAULT_SHOTS
try:
    _root = os.path.realpath(SKILL_ROOT)
    _shots = os.path.realpath(MAC_SHOTS)
    if _shots == _root or _shots.startswith(_root + os.sep):
        print("WARN: 截图目录 %s 在 skill 目录内 → 重定向到 %s"
              "（超 200MB 自动归档，见 scripts/shots_gc.py）" % (MAC_SHOTS, DEFAULT_SHOTS))
        MAC_SHOTS = DEFAULT_SHOTS
except OSError:
    pass
AUTO = a.auto
BASE = a.remote_base
HOST = a.host
TASK = a.task
TIMEOUT = a.timeout

argv = a.cmd
if argv and argv[0] == "--":
    argv = argv[1:]
if not argv:
    print(__doc__); sys.exit(1)

SUB = argv[0]
for tok in argv[1:]:
    if tok.startswith("-") and tok != "--":
        print("ARG-ERROR: %r 出现在子命令 %s 之后 —— REMAINDER 会把它当位置参数吞掉"
              "（实付事故: step x.py --timeout 400 把 --timeout 当截图名）。"
              "全局选项必须放在子命令之前。" % (tok, SUB))
        sys.exit(2)

# ---- 本地锁：同一台 Mac 同时只允许一个 pt.py ----
LOCK = "/tmp/window-use-pt.lock"


def _lock_release():
    try:
        if os.path.exists(LOCK) and open(LOCK).read().strip() == str(os.getpid()):
            os.remove(LOCK)
    except OSError:
        pass


def _lock_acquire():
    if os.path.exists(LOCK):
        try:
            opid = int(open(LOCK).read().strip())
        except (ValueError, OSError):
            opid = None
        if opid is not None:
            try:
                os.kill(opid, 0)
            except ProcessLookupError:
                pass                      # 残留锁，进程已死，接管
            except PermissionError:
                print("另一个 pt.py(pid=%d) 还在跑（同用户锁检测）。并发会互相覆盖 "
                      "next_cmd/截断日志，等它退或 rm %s" % (opid, LOCK))
                sys.exit(2)
            else:
                print("另一个 pt.py(pid=%d) 还在跑。并发会互相覆盖 next_cmd/截断日志，"
                      "等它退；确信是残留锁就 rm %s" % (opid, LOCK))
                sys.exit(2)
    with open(LOCK, "w") as f:
        f.write(str(os.getpid()))
    atexit.register(_lock_release)


def ssh(*args, timeout=120, retries=2):
    """SSH exec，瞬断（kex timeout / 复位）自动重试。全部失败才退出。
    返回 (stdout, exit_code)——调用方必须检查 exit_code，别再解析输出子串判成败。"""
    last = None
    for i in range(retries + 1):
        try:
            r = subprocess.run([PY, SKILL, "exec", HOST, *args],
                               capture_output=True, text=True, timeout=timeout)
            if r.returncode == 0:
                d = json.loads(r.stdout)
                data = d.get("data") or {}
                return data.get("stdout", ""), data.get("exit_code", 0)
            last = "rc=%s %s" % (r.returncode, (r.stderr or r.stdout or "")[:200])
        except Exception as e:
            last = repr(e)
        if i < retries:
            time.sleep(4)
    print("SSH-FAIL:", last)
    sys.exit(2)


def up(local, remote, retries=2, timeout=180):
    last = None
    for i in range(retries + 1):
        try:
            r = subprocess.run([PY, SKILL, "upload", HOST, local, remote],
                               capture_output=True, text=True, timeout=timeout)
            if '"success":true' in r.stdout:
                return
            last = (r.stdout[:200] or r.stderr[:200])
        except Exception as e:
            last = repr(e)
        if i < retries:
            time.sleep(4)
    print("UPLOAD-FAIL:", last, "\n兜底: ssh exec + printf %s <b64> | base64 -d > 远端路径")
    sys.exit(2)


def down(remote, local, retries=2, timeout=180):
    last = None
    for i in range(retries + 1):
        try:
            r = subprocess.run([PY, SKILL, "download", HOST, remote, local],
                               capture_output=True, text=True, timeout=timeout)
            if '"success":true' in r.stdout:
                return
            last = (r.stdout[:200] or r.stderr[:200])
        except Exception as e:
            last = repr(e)
        if i < retries:
            time.sleep(4)
    print("DOWNLOAD-FAIL:", last)
    sys.exit(2)


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _verify_png(lp, label):
    """落地的截图必须存在、非零、是真 PNG——半张/旧文件在这里被拦下，不再假成功。"""
    if not os.path.isfile(lp) or os.path.getsize(lp) == 0:
        print("FAIL: %s 空/缺失 —— 驱动可能没执行到 shot 行，先 `pt.py log 30` 看主线" % label)
        sys.exit(3)
    with open(lp, "rb") as f:
        if f.read(8) != PNG_MAGIC:
            print("FAIL: %s 不是完整 PNG（半张/写坏）——净场后重试本轮" % label)
            sys.exit(3)


def _auto_gc():
    """每轮 pull 后顺手归档：目录超 200MB 才动手（WGUI_SHOTS_MAX_MB 可调），
    平时零开销零输出。归档失败只提示，绝不影响本轮结果。"""
    if shots_gc is None:
        return
    try:
        shots_gc.gc_dir(MAC_SHOTS,
                        max_mb=float(os.environ.get("WGUI_SHOTS_MAX_MB", "200")))
    except Exception as e:
        print("shots GC 跳过: %r（手动跑 python3 scripts/shots_gc.py 看详情）" % e)


def send(cmd, *args, timeout=None):
    if not cmd:
        print("send: 空命令被拒绝（空 next_cmd.txt 会让驱动 FAIL parse）")
        sys.exit(2)
    line = " ".join(shlex.quote(x) for x in [cmd] + list(args))
    tmp = "/tmp/next_cmd.%d.txt" % os.getpid()      # pid 后缀：并发时互不覆盖
    with open(tmp, "w") as f:
        f.write(line + "\n")
    up(tmp, AUTO + "/next_cmd.txt")
    # 触发前清空日志并回读确认——残留 DONE 是假成功之源，清不空就 FAIL，别赌
    ssh("> %s/gui.log" % BASE, retries=1)
    chk, _ = ssh("wc -c < %s/gui.log 2>/dev/null" % BASE, retries=1)
    chk = chk.strip().splitlines()[-1] if chk.strip() else ""
    if chk != "0":
        print("TRIGGER-ABORT: gui.log 截断后非空(%r) —— 路径不对或旧进程仍在写。"
              "核对 --remote-base，必要时 taskkill pythonw 后重试" % chk)
        sys.exit(2)
    # 触发不重试：远端可能已执行而回包丢失，重发 = 二次点击（远§3）
    out, rc = ssh("MSYS_NO_PATHCONV=1 schtasks /run /tn %s 2>&1" % TASK, retries=0)
    if rc != 0 or "ERROR" in out.upper():
        print("TRIGGER-FAIL(rc=%s): %s" % (rc, out.strip()))
        print("触发失败已就此终止（不再空轮询）——查任务名/状态: "
              "ssh %s 'schtasks /query /tn %s'" % (HOST, TASK))
        sys.exit(2)
    cmdword = cmd.split()[0]
    want = args[0] if args else None        # 首个参数（script 文件名 / shot 名）
    started = False                          # 本轮 START 出现后 DONE/FAIL 才算数
    t0 = time.time()
    deadline = t0 + (timeout or TIMEOUT)
    while time.time() < deadline:
        time.sleep(2.5)
        # 读整份本轮 log（触发前已清空并回读确认为空）。START 守卫仍保留：
        # 驱动端万一旧实例还握着文件句柄追加写入，START 守卫是第二道保险。
        out, _ = ssh("cat %s/gui.log 2>/dev/null" % BASE)
        lines = out.splitlines()
        if any("] FAIL busy" in ln for ln in lines):
            print("FAIL busy: 上一个驱动实例还在运行（新版驱动会显式记录，不再静默跳过）")
            print("恢复: taskkill /F /IM pythonw.exe 后重新 schtasks /run —— "
                  "next_cmd.txt 未被消费，重跑执行同一条命令")
            sys.exit(5)
        if want and not started:
            started = any(("] START %s" % cmdword) in ln and want in ln for ln in lines)
        if want and not started and time.time() > t0 + 30:
            # 退化：无参命令不回显参数。触发前已确认 log 为空，此处匹配到的必是本轮 START
            started = any(("] START %s" % cmdword) in ln for ln in lines)
        verdict = None
        for ln in lines:
            if "] DONE %s" % cmdword in ln:
                verdict = ("OK", ln.strip())
            elif "] FAIL %s" % cmdword in ln:
                verdict = ("FAIL", ln.strip())
        if verdict and (started or not want):
            tag, ln = verdict
            print("%s: %s" % (tag, ln))
            if tag == "FAIL":
                tb, _ = ssh("cat %s/gui.log" % BASE)
                print(tb)
                print("错误现场截图: %s/shots/error_%s_<HHMMSS>.png（时间戳命名不互相覆盖）"
                      % (AUTO, cmdword))
                sys.exit(3)
            return 0
        if verdict and not started:
            print("... 忽略陈旧 verdict（本轮 START 未出现）: %s" % verdict[1])
    print("TIMEOUT waiting for", cmdword)
    print("排查: ① 残留 pythonw 实例（新版驱动会记 FAIL busy，没记到再看 tasklist）-> "
          "ssh 时跑 MSYS_NO_PATHCONV=1 cmd /c \"taskkill /F /IM pythonw.exe\"")
    print("      ② 驱动是否在做全树 UIA 遍历(大列表要走几分钟, 改定向 descendants)")
    print("      ③ 命令可能实际已生效 —— 先 send shot 看现场, 别盲目重发(二次点击)")
    sys.exit(4)


def step(local_script, shotname=None):
    """原子步进一轮（踩坑清单 公#21 的落地命令）: push 脚本 → send 执行 → pull 截图。
    约定: 脚本最后一张截图与脚本同名（脚本末尾 ptlib.shot("<脚本名>)")），shot 可省略。
    触发前删远端同名旧图 + 落地校验 PNG —— 拉旧图的两起实付事故（公#29/A7）在工具层防住。
    FAIL 时 send 直接退出 —— 不拉图、不重发，先看 error_*.png 现场再净场重试同一动作。"""
    bn = os.path.basename(local_script)
    stem = os.path.splitext(bn)[0]
    name = (shotname or stem)
    up(local_script, AUTO + "/scripts/" + bn)
    print("pushed", bn)
    ssh("rm -f %s/shots/%s" % (BASE, shlex.quote(name + ".png")), retries=1)
    send("script", bn)
    lp = os.path.join(MAC_SHOTS, name + ".png")
    down(AUTO + "/shots/" + name + ".png", lp)
    _verify_png(lp, name + ".png")
    print("pulled", name + ".png  <- 看图确认通过后，才 step 下一个动作")
    _auto_gc()


def pushdir(local_dir):
    for root, dirs, files in os.walk(local_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__" and not d.startswith(".")]
        for fn in files:
            if fn.startswith(".") or fn.endswith(".pyc"):
                continue                  # 别把 __pycache__/.DS_Store 推上 PC
            lp = os.path.join(root, fn)
            rel = os.path.relpath(lp, local_dir).replace(os.sep, "/")
            up(lp, "%s/%s" % (AUTO, rel))
            print("pushed", rel)


def main():
    _lock_acquire()
    os.makedirs(MAC_SHOTS, exist_ok=True)
    if SUB == "send":
        send(*argv[1:])
    elif SUB == "step":
        if len(argv) < 2:
            print(__doc__); sys.exit(1)
        step(argv[1], argv[2] if len(argv) > 2 else None)
    elif SUB == "push":
        up(argv[1], AUTO + "/scripts/" + os.path.basename(argv[1]))
        print("pushed", os.path.basename(argv[1]))
    elif SUB == "pushdir":
        pushdir(argv[1])
    elif SUB == "pull":
        for name in argv[1:]:
            fn = name if name.endswith(".png") else name + ".png"
            lp = os.path.join(MAC_SHOTS, fn)
            down(AUTO + "/shots/" + fn, lp)
            _verify_png(lp, fn)
            print("pulled", fn)
        _auto_gc()
    elif SUB == "gc":
        if shots_gc is None:
            print("shots_gc 不可用：scripts/shots_gc.py 不在预期位置"); sys.exit(1)
        print(shots_gc.gc_dir(MAC_SHOTS))
    elif SUB == "log":
        out, _ = ssh("tail -%s %s/gui.log" % (argv[1] if len(argv) > 1 else "10", BASE))
        print(out)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
