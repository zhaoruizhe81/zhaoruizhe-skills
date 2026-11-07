#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shots_gc.py — 截图目录自动归档（Mac 端）。

背景（2026-11-05 实付）：pt.py 老版默认把截图拉到 cwd/shots，而 agent 干活时总在
skill 根目录里，172MB 证据图沉淀进知识库。修复后截图默认落 ~/.zcode/window-use/shots
（skill 外），本脚本负责"只进不出"问题的另一半：目录超过阈值就把最旧的截图打包成
带时间戳的 tar.gz 并删除原图——证据不丢（归档可查），知识库不胖。

触发方式（三选一，不必配 cron）:
  1. 自动：pt.py 每次 step/pull 成功后顺手跑一次（默认开，阈值 200MB，
     可用环境变量 WGUI_SHOTS_MAX_MB 调）
  2. 手动：python3 scripts/shots_gc.py [--dry-run]
  3. 定时：crontab 一天一次（可选）

策略：按 mtime 从新到旧保住最新 --keep 张；超出预算（--max-mb）与超龄
（--max-age-days）的部分打包进一个 tar.gz；先归档、后校验（回读计数一致）、
再删原图——任何一步失败都不动原图。永不碰保住名单内的文件。

用法:
  python3 scripts/shots_gc.py                            # 默认目录/阈值，超了才动手
  python3 scripts/shots_gc.py --dry-run                  # 只报告不动手
  python3 scripts/shots_gc.py --dir ~/shots --max-mb 100 --keep 50
"""
import argparse
import os
import sys
import tarfile
import time


def gc_dir(d, archive_dir=None, max_mb=200.0, keep=100, max_age_days=None,
           dry_run=False, log=print):
    """把目录 d 超出预算/超龄的旧截图归档成 tar.gz 并删除。返回摘要 dict；
    目录不超预算时不动任何文件（status=ok）。"""
    d = os.path.abspath(os.path.expanduser(d))
    if not os.path.isdir(d):
        return {"status": "empty", "dir": d}
    files = []
    for root, _dirs, names in os.walk(d):
        for n in names:
            p = os.path.join(root, n)
            try:
                files.append((os.path.getmtime(p), os.path.getsize(p), p))
            except OSError:
                continue
    if not files:
        return {"status": "empty", "dir": d}
    total_mb = sum(s for _, s, _ in files) / (1024.0 * 1024.0)
    excess_mb = total_mb - float(max_mb)
    over_age = set()
    if max_age_days:
        cutoff = time.time() - max_age_days * 86400
        over_age = {p for mt, _, p in files if mt < cutoff}
    # 保住名单：最新 keep 张（mtime 降序取前 keep）
    files.sort(reverse=True)
    protected = {p for _, _, p in files[:max(0, keep)]}
    # 受害名单：从最旧开始收，收够补上超额即止；超龄无条件进
    victims = []
    freed = 0.0
    for mt, s, p in sorted(files):          # 升序 = 最旧在前
        if p in protected:
            continue
        if p in over_age or freed < excess_mb:
            victims.append(p)
            freed += s / (1024.0 * 1024.0)
    if not victims:
        return {"status": "ok", "dir": d, "total_mb": round(total_mb, 1),
                "archived": 0}
    if archive_dir:
        archive_dir = os.path.abspath(os.path.expanduser(archive_dir))
    else:
        base = d.rstrip(os.sep)
        archive_dir = os.path.join(os.path.dirname(base),
                                   os.path.basename(base) + "-archive")
    os.makedirs(archive_dir, exist_ok=True)
    tar_path = os.path.join(archive_dir,
                            "shots-%s.tar.gz" % time.strftime("%Y%m%d-%H%M%S"))
    if dry_run:
        log("[dry-run] 会归档 %d 张 (%.1fMB) -> %s；目录将剩 %.1fMB"
            % (len(victims), freed, tar_path, total_mb - freed))
        return {"status": "dry-run", "archived": len(victims),
                "freed_mb": round(freed, 1), "tar": tar_path}
    n = 0
    with tarfile.open(tar_path, "w:gz") as tf:
        for p in victims:
            tf.add(p, arcname=os.path.relpath(p, d))
            n += 1
    # 回读校验张数一致才删原图——归档写坏时宁可不清理也不丢证据
    with tarfile.open(tar_path, "r:gz") as tf:
        got = sum(1 for m in tf.getmembers() if m.isfile())
    if got != n:
        return {"status": "verify-failed", "tar": tar_path,
                "want": n, "got": got}
    removed = 0
    for p in victims:
        try:
            os.remove(p)
            removed += 1
        except OSError:
            continue
    log("shots GC: 归档 %d 张 (%.1fMB) -> %s；目录剩 %.1fMB"
        % (removed, freed, tar_path, total_mb - freed))
    return {"status": "done", "archived": removed,
            "freed_mb": round(freed, 1), "tar": tar_path}


def main():
    ap = argparse.ArgumentParser(description="截图目录自动归档（超阈值打包 tar.gz）")
    ap.add_argument("--dir", default=os.environ.get(
        "WGUI_MAC_SHOTS", "~/.zcode/window-use/shots"))
    ap.add_argument("--archive-dir", default=None,
                    help="归档 tar.gz 存放目录（默认 <dir> 同级的 <dir>-archive）")
    ap.add_argument("--max-mb", type=float, default=200.0,
                    help="目录总大小预算 MB，超出才归档（默认 200）")
    ap.add_argument("--keep", type=int, default=100,
                    help="无论超不超额都保住最新的 N 张（默认 100）")
    ap.add_argument("--max-age-days", type=float, default=None,
                    help="超过 N 天的截图无条件归档（可选）")
    ap.add_argument("--dry-run", action="store_true", help="只报告不动手")
    a = ap.parse_args()
    print(gc_dir(a.dir, a.archive_dir, a.max_mb, a.keep, a.max_age_days, a.dry_run))


if __name__ == "__main__":
    sys.exit(main())
