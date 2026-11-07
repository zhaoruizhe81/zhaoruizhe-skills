# window-use

Windows 桌面 GUI 自动化 skill（ZCode/agent 用）：把 agent 变成 Windows 桌面的手和眼——
点击、输入、粘贴、截图、闭环验证任意桌面软件。PC 本机直跑，或从 macOS 经 SSH 遥控 Windows。

> 详细文档见 [SKILL.md](SKILL.md)（工作流 + 坑点速查表）。

## 组成

| 部分 | 说明 |
|---|---|
| `scripts/win_gui_driver.py` | 核心驱动（唯一必须部署到 PC 的通用件） |
| `scripts/shots_gc.py` | 截图自动归档（超阈值打包 tar.gz，证据不丢、知识库不胖） |
| `remote/` | Mac 端遥控器 pt.py + 计划任务桥（session-0 桌面会话投递） |
| `apps/` | 14 个应用包：Packet Tracer、eNSP、Wireshark、Navicat、SQL Developer、Oracle、WPS、Excel、MS Project、Spyder、Quartus/ModelSim、Access、SPSS、Dev-C++——坐标表 + 配方 + 私有坑 |
| `踩坑清单.md` | 70 条公共坑（症状 → 原因 → 解法，全部实战实付） |
| `脚本用法.md` / `remote/远程坑.md` | 驱动命令表 / 远程场景坑（§1-§11） |

## 设计要点

- **原子步进**：一次触发 = 一个原子动作 + 一次截图验证，失败走"失败处理阶梯"
- **坑点速查表**：按"你看到的现象"分 9 桶索引，报错串可直接 grep 到编号坑
- **自优化闭环**：每轮任务的学费回写成带编号的坑，索引同步更新
- **产物不入库**：截图默认落 `~/.zcode/window-use/shots`（skill 外），超 200MB 自动归档

## 部署

```bash
# PC 端：把驱动放到固定目录，装依赖（pywinauto pyautogui mss pywin32）
# Mac 端：
python3 remote/pt.py send shot verify1    # 投递+触发+轮询+拉图，一条命令验证全链路
```

---

个人课程自动化实战沉淀（2026-10 ~ 2026-11），仅供学习交流。
