# Android 部署指南（Termux + 免 root 方案）

本目录让机器人**服务端本身跑在安卓手机上**（Termux 里的 Python 进程），
再把手机上的 QQ 接入 OneBot v11 协议。

**安卓不 root 也能跑**，有两条免 root 路线，推荐第一种：

| 方案 | 需要 Root | 原理 | 稳定性 |
| --- | --- | --- | --- |
| **A. NapCat.Termux**（推荐） | **不需要** | 在 Termux 里用 proot 跑官方 QQ Linux 客户端 + NapCat | 高，与 Windows 版同款 NapCat |
| **B. OpenShamrock + LSPatch** | 不需要（但需修补 QQ） | 把 Xposed 模块注入手机 QQ | 一般，回调受限、QQ 版本敏感 |

> 方案 B 若用 **LSPosed**（需 Root）则稳定性更好，但既然要免 root，就走 LSPatch。

---

## 一、方案 A：NapCat.Termux（免 root，推荐）

```
┌──────────────────────── 安卓手机 ────────────────────────┐
│  Termux                                                   │
│   ├── proot Linux ── QQ Linux 客户端 + NapCat             │
│   │                        │                              │
│   │                   反向 WS                            │
│   │                        ▼                              │
│   └── bot.py（本机器人服务端）  127.0.0.1:8080             │
└───────────────────────────────────────────────────────────┘
```

NapCat 官方提供了 **NapCat.Termux**，脚本会在 Termux 内自动搭好
proot Linux 环境并安装官方 QQ 与 NapCat，**全程无需 root**。
好处是它和 Windows 版是同一个 NapCat，配置、行为完全一致。

### 0. 一键部署（最快）

把 `qqbot` 目录放进手机后，在 Termux 里只跑一条命令，机器人 + NapCat 一起装好：

```bash
cd ~/qqbot
chmod +x deploy/android/setup-all.sh
./deploy/android/setup-all.sh
```

装完按脚本结尾的「后续 3 步」操作即可（填 Cookie → 启动机器人 → 启动 NapCat 扫码）。
下面 1~4 步是分步说明，便于排查问题。

### 1. 部署机器人服务端

1. 从 [F-Droid](https://f-droid.org/packages/com.termux/) 安装 Termux
   （不要用 Google Play 上的旧版本）。
2. 把 `qqbot` 目录放进手机，再复制进 Termux 家目录：

   ```bash
   termux-setup-storage          # 授权访问手机存储
   cp -r /sdcard/qqbot ~/qqbot
   cd ~/qqbot
   ```

3. 一键部署：

   ```bash
   chmod +x deploy/android/install.sh
   ./deploy/android/install.sh
   ```

   编辑 `.env` 填写 `MCDEV_COOKIE`（获取方式同主 README 第三节）。

4. 启动机器人（保活守护，自动持有唤醒锁并崩溃重启）：

   ```bash
   ./deploy/android/watchdog.sh start     # 启动守护
   ./deploy/android/watchdog.sh status    # 查看状态
   ./deploy/android/watchdog.sh log       # 实时日志
   ```

### 2. 安装并启动 NapCat

在 Termux 中执行官方一键脚本：

```bash
curl -o napcat.termux.sh https://nclatest.znin.net/NapNeko/NapCat-Installer/main/script/install.termux.sh && bash napcat.termux.sh
```

> 脚本会下载 proot 环境、官方 QQ 与 NapCat，耗时较长，中途失败重新执行即可。

安装完成后，用 NapCat 的 CLI 启动（把 `QQ号` 换成机器人小号）：

```bash
napcat start QQ号        # 启动
napcat log QQ号          # 查看日志 / 二维码
```

### 3. 扫码登录

启动后 NapCat 会在日志里打印登录二维码。因为二维码在手机自己的屏幕上，
可以这样扫：

- **截图法**：`napcat log QQ号` 看到二维码 → 截屏 → 用 QQ 的「扫一扫 → 相册」识别；
- **另一台设备法**：用另一台手机的 QQ 扫这块屏幕；
- **WebUI 法**：直接进下一步的 WebUI（`http://localhost:6099/webui`）里点扫码登录。

> 请务必用**机器人小号**扫码，不要用主号。

### 4. 配置反向 WebSocket

浏览器打开 NapCat 的 WebUI：

```
http://localhost:6099/webui
```

首次登录 token 可在终端查看：

```bash
cat ~/Napcat/opt/QQ/resources/app/app_launcher/napcat/config/webui.json | grep token
```

登录后在 **网络配置** 中新建 **WebSocket 客户端（反向）**：

| 配置项 | 值 |
| --- | --- |
| URL | `ws://127.0.0.1:8080/onebot/v11/ws` |
| 消息格式 | `Array` |
| 心跳间隔 / 重连间隔 | `5000` |

保存并启用后，回到 Termux 用 `./deploy/android/service.sh log` 看机器人日志，
出现 OneBot V11 连接记录（含 bot 的 QQ 号）即接入成功。

> NapCat 与机器人都跑在同一台手机的 Termux 里，proot 共享网络，
> 所以 `127.0.0.1` 可以直连，无需改成局域网 IP。

---

## 二、方案 B：OpenShamrock + LSPatch（免 root，注入式）

不想在手机上跑 QQ Linux 客户端、想直接用**手机版 QQ** 时选这个。
用 LSPatch 免 root 把 OpenShamrock 模块注入 QQ。

> 官方 Shamrock 文档明确把「**无 Root 环境 → 使用 LSPatch**」列为受支持方案。

1. 从 OpenShamrock 官方发布页下载 **带 `all` 字样**的安装包并安装。
2. 打开 **LSPatch** → `管理` → `+` 新建修补 → 选择已安装的 QQ。
3. 修补模式选 **本地模式**（方便更新模块，缺点是 LSPatch 要保持后台运行）；
   其他保持默认，点「开始修补」，完成后按提示安装。
4. 回到 LSPatch `管理`，点修补好的 QQ → `模块作用域` → 勾选 Shamrock → 保存。
5. 启动 Shamrock，**重启 QQ 客户端**，Shamrock 显示「已激活」即成功。
6. 在 Shamrock 设置页配置：

| 配置项 | 值 |
| --- | --- |
| 消息格式为 CQ 码 | 开启 |
| 被动 WebSocket（反向 WS） | 开启 |
| 被动 WS 监听地址 | `ws://127.0.0.1:8080/onebot/v11/ws` |

**局限**：LSPatch 方式下**回调能力受限**，且对 QQ 版本较敏感（版本过新可能注入失败），
长期挂机稳定性不如方案 A。若手机已 root，用 LSPosed 代替 LSPatch 会明显更稳。

---

## 三、保活设置（重要）

安卓系统对后台进程管得很严，息屏后很容易把 Termux 连同机器人一起杀掉。
本项目提供了两层保活：**进程守护**（watchdog.sh）+ **系统侧设置**（keepalive.sh）。

### 1. 进程守护 watchdog.sh

```bash
./deploy/android/watchdog.sh start     # 启动守护
./deploy/android/watchdog.sh status    # 查看状态
./deploy/android/watchdog.sh log       # 实时日志
./deploy/android/watchdog.sh stop      # 停止守护（连同机器人）
```

它会做三件事：

- 持有 `termux-wake-lock` 唤醒锁，避免息屏后 CPU 休眠导致掉线；
- 每 30 秒检查一次机器人进程，崩溃或被系统杀掉后**自动拉起**；
- 可选看护 NapCat：在 `.env` 里加 `MCDEV_WATCHDOG_QQ=机器人QQ号` 即可，
  检测到 NapCat 不在就跑 `napcat start`。

检查间隔可用 `MCDEV_WATCHDOG_INTERVAL` 调整（默认 30 秒）。

> `watchdog.sh` 与 `service.sh` 管理同一个 `bot.pid`，**请勿同时运行**。
> 长期挂机用 `watchdog.sh`，临时调试用 `service.sh`。

### 2. 系统侧设置 keepalive.sh

```bash
./deploy/android/keepalive.sh
```

脚本会自动完成能自动的部分，并打开设置页引导你完成手动部分：

- 写入 **Termux:Boot 开机自启**脚本（`~/.termux/boot/mcdev-watchdog.sh`），
  开机后自动拉起守护；需安装 [Termux:Boot](https://f-droid.org/packages/com.termux.boot/) 才生效；
- 打开**电池优化白名单**设置页；
- 打开 **Termux 应用详情**页。

### 3. 必须手动确认的项

| 设置 | 位置 | 目的 |
| --- | --- | --- |
| 电池优化 → 不优化 / 无限制 | 系统设置 → 电池 → 电池优化 → Termux | 防止息屏后被冻结 |
| 省电策略 → 无限制 | 应用详情 → 耗电管理 | 同上 |
| 允许自启动 / 后台活动 | 应用详情（各品牌叫法不同） | 防止被一键清理 |
| 最近任务里给 Termux 加锁 | 多任务界面下拉卡片 | 避免「一键清理」误杀 |

> NapCat 侧可在其 WebUI「登录配置」里保存 bot QQ，之后无需再扫码；
> 重启后用 `napcat start QQ号` 拉起（也可交由 watchdog 看护）。

---

## 四、常见问题

**Q：安卓到底要不要 root？**
不要。走 **NapCat.Termux**（方案 A）完全免 root；走 OpenShamrock 时用
**LSPatch** 也能免 root，只是稳定性差一些。

**Q：机器人日志里没有连接记录？**
依次检查：NapCat 是否已启动并登录成功；WebUI 里反向 WS 是否已「启用」；
URL 是否为 `ws://127.0.0.1:8080/onebot/v11/ws`；`.env` 的 `PORT` 是否一致；
机器人是否在运行（`service.sh status`）。

**Q：手机耗电/发热？**
机器人本身很轻量，主要开销来自 proot 里的 QQ、图表渲染与定时推送。
可把 `MCDEV_CHART_ENABLED` 设为 `false`、减少 `MCDEV_PUSH_HOURS` 来降低负载。

**Q：和 Windows 版能同时用吗？**
可以。两端用**不同的 QQ 号**登录即可（同一个 QQ 号不能同时登录）。

**Q：图表中文显示为方框？**
缺少 CJK 字体，执行 `pkg install -y fontconfig` 后把中文字体放进 `~/.fonts`；
或直接在 `.env` 中设置 `MCDEV_CHART_ENABLED=false` 关闭图表。

**Q：挂一段时间就掉线 / 进程消失了？**
说明被安卓系统杀了后台。按第三节做两层保活：`watchdog.sh start` 起进程守护
（唤醒锁 + 崩溃自动重启），再用 `keepalive.sh` 打开设置页把 Termux 加进
**电池优化白名单**并允许自启动。这两步缺一不可。
