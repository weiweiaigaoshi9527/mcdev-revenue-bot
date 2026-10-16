# 多平台部署总览

同一套代码可在 **Windows / Linux / Android** 三种环境下作为服务端运行。
三者的差异**仅在于「用哪个程序把 QQ 接入 OneBot v11 协议」以及「如何守护进程」**，
机器人的配置、指令、图表、定时推送完全一致。

| 平台 | 机器人服务端 | QQ 接入（OneBot 实现） | 进程守护 |
| --- | --- | --- | --- |
| Windows | Python（`bot.py`） | **NapCat**（QQ 客户端注入） | 计划任务（开机自启 + 崩溃重启） |
| Linux | Python（`bot.py`） | **NapCat** / Lagrange.OneBot | systemd |
| Android | Python（Termux） | **NapCat.Termux（免 root，推荐）** / OpenShamrock | nohup + 唤醒锁 / Termux:Boot |

三者统一通过**反向 WebSocket** 通信，地址均为：

```
ws://127.0.0.1:8080/onebot/v11/ws
```

---

## 目录说明

```
deploy/
├── README.md                     # 本文件（多平台总览）
├── windows/
│   ├── install-service.ps1       # 注册开机自启计划任务（管理员运行）
│   └── uninstall-service.ps1     # 卸载计划任务
├── linux/
│   ├── install.sh                # 一键部署（系统依赖 + venv + systemd）
│   ├── mcdev-bot.service         # systemd 单元模板
│   └── start.sh                  # 前台调试启动
└── android/
    ├── install.sh                # Termux 一键部署
    ├── start.sh                  # 前台调试启动
    ├── service.sh                # 后台常驻管理（start/stop/status/log）
    ├── watchdog.sh               # 保活守护（唤醒锁 + 崩溃自动重启，推荐）
    ├── keepalive.sh              # 系统侧保活设置（电池优化白名单 + 开机自启）
    ├── setup-all.sh              # 一键部署：机器人 + NapCat.Termux + 保活
    └── README.md                 # Termux + 免 root 接入详细指南（NapCat.Termux / OpenShamrock）
```

---

## 一、Windows 部署

### 前台运行（最简单）

双击项目根目录的 **`start.bat`**：自动检查依赖并启动机器人。

### 注册为开机自启服务（推荐长期挂机）

以**管理员身份**打开 PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File deploy\windows\install-service.ps1
```

脚本会：创建 `.venv` 虚拟环境 → 生成 `.env` → 注册名为 `MCDEV-RevenueBot`
的计划任务（开机延迟 30 秒启动，崩溃自动重启）。

```powershell
Start-ScheduledTask -TaskName MCDEV-RevenueBot   # 立即启动
Get-ScheduledTask   -TaskName MCDEV-RevenueBot   # 查看状态
Stop-ScheduledTask  -TaskName MCDEV-RevenueBot   # 停止
```

卸载：

```powershell
powershell -ExecutionPolicy Bypass -File deploy\windows\uninstall-service.ps1
```

QQ 接入用 **NapCat**，详见主 [README](../README.md) 第三节。

---

## 二、Linux 部署

支持 Debian/Ubuntu（apt）、CentOS/RHEL（dnf/yum）、Alpine（apk）。

```bash
chmod +x deploy/linux/install.sh
./deploy/linux/install.sh
```

脚本会：安装系统依赖（含中文字体）→ 创建 `.venv` → 生成 `.env` →
注册并开机自启 systemd 服务 `mcdev-bot`。

```bash
sudo systemctl start mcdev-bot      # 启动
systemctl status mcdev-bot          # 状态
journalctl -u mcdev-bot -f          # 实时日志
sudo systemctl stop mcdev-bot       # 停止
sudo systemctl disable mcdev-bot    # 取消自启
```

前台调试：`./deploy/linux/start.sh`

QQ 接入推荐用 **NapCat**（支持 Linux）或 **Lagrange.OneBot**，
在 `.env` 中把反向 WS 地址指向 `ws://127.0.0.1:8080/onebot/v11/ws`。

---

## 三、Android 部署

由 Termux 承载机器人服务端。**无需 root**，QQ 接入有两种方式：
**NapCat.Termux**（推荐，免 root，与 Windows 版同款 NapCat）或
**OpenShamrock + LSPatch**（免 root 注入手机 QQ，稳定性稍差）。

```bash
cp -r /sdcard/qqbot ~/qqbot && cd ~/qqbot
chmod +x deploy/android/setup-all.sh
./deploy/android/setup-all.sh     # 机器人 + NapCat.Termux 一次装好
```

详细步骤（含 NapCat.Termux 一键安装、扫码登录、OpenShamrock 方案、开机自启）见
**[deploy/android/README.md](android/README.md)**。

---

## 四、跨平台注意事项

1. **配置文件**：三者共用同一份 `.env`（格式相同），但 `HOST` 需按需调整 ——
   同一台机器上跑就用 `127.0.0.1`；QQ 实现与机器人不在同一台机器时，
   改成 `0.0.0.0` 并用对方能访问到的 IP。
2. **中文字体**：Windows 自带微软雅黑；Linux 需装 `fonts-noto-cjk`（install.sh 已处理）；
   Android 需自行放入 CJK 字体，否则图表中文显示为方框。
3. **matplotlib**：Windows/Linux 正常安装即可；Android 上编译较慢，
   失败时图表指令自动降级为文字，不影响其它功能。
4. **文件路径**：代码已做跨平台处理（`bot.py` 会 `os.chdir` 到项目根目录，
   `.env` 按脚本绝对路径加载），因此在任意平台、任意启动方式下路径都一致。
5. **定时推送**：使用 APScheduler 的小时列表，三平台行为一致
   （`MCDEV_PUSH_HOURS=10,12,14,16,18,20,22,0`）。
6. **保活（仅 Android）**：安卓会杀后台，必须用 `watchdog.sh` 起进程守护
   （唤醒锁 + 崩溃自动重启），并用 `keepalive.sh` 把 Termux 加入电池优化白名单、
   允许自启动。Windows/Linux 由计划任务、systemd 负责，无需额外操作。
