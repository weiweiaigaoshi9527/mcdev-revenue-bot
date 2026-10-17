# Android 部署指南（Termux · 免 root · 不挂电脑）

把官方 QQ 机器人跑在一台闲置安卓手机上：**不需要电脑、不需要 root、
不需要挂 QQ 客户端**。手机只跑一个 Python 进程，通过出站 WebSocket
连腾讯网关即可，不用开放任何端口。

```
┌──────────── 安卓手机 ────────────┐
│  Termux                          │
│   └── bot_qq.py                  │
│         │ 出站 WSS               │
└─────────┼────────────────────────┘
          ▼
     腾讯 QQ 机器人网关
```

> 传统 NapCat 方案要在手机上跑官方 QQ 客户端 + proot 环境，又重又容易掉。
> 官方机器人模式只需要 `qq-botpy`，手机上占用极小，是「不挂电脑」的最优解。

---

## 一、准备

1. 从 [F-Droid](https://f-droid.org/packages/com.termux/) 安装 **Termux**
   （**不要**用 Google Play 上的旧版，那个已停止更新且装不了新包）。
2. 建议同时装 [Termux:Boot](https://f-droid.org/packages/com.termux.boot/)，
   用于开机自启。
3. 在 [q.qq.com](https://q.qq.com/) 创建机器人，拿到 **AppID** 与 **AppSecret**。

---

## 二、一键部署

把 `qqbot` 目录传到手机（数据线 / 网盘均可），然后在 Termux 中：

```bash
termux-setup-storage            # 授权访问手机存储
cp -r /sdcard/qqbot ~/qqbot     # 路径按实际存放位置调整
cd ~/qqbot
chmod +x deploy/android/*.sh
./deploy/android/setup-all.sh
```

脚本会自动完成：安装 Python 与依赖 → 创建虚拟环境 → 安装 `qq-botpy`
→ 生成 `.env` → 写入开机自启脚本 → 打开电池优化设置页。

---

## 三、填写配置

```bash
nano ~/qqbot/.env
```

至少填三项：

```ini
QQ_BOT_APPID=你的AppID
QQ_BOT_SECRET=你的AppSecret
MCDEV_COOKIE=开发者平台复制的完整 Cookie
```

自检（确认 Cookie 有效、接口能通）：

```bash
~/qqbot/.venv/bin/python ~/qqbot/tools/probe.py
```

---

## 四、启动

**先前台试跑一次**，确认能连上腾讯网关：

```bash
cd ~/qqbot
./deploy/android/start.sh
```

看到下面这行说明成功，按 `Ctrl+C` 停掉：

```
[mcdev-qqbot] 机器人已就绪：虹小轩我的世界机器人
```

**再转后台常驻**（推荐，带唤醒锁 + 崩溃自动重启）：

```bash
./deploy/android/watchdog.sh start
./deploy/android/watchdog.sh status
./deploy/android/watchdog.sh log      # 实时日志
```

然后在 QQ 群里 **@机器人** 发 `帮助` 即可。

---

## 五、手机 App（控制台）

除了在 Termux 里敲命令，也可以装一个 App 当图形界面。
App 只是控制台的壳：机器人本身仍跑在 Termux，App 通过
`http://127.0.0.1:8770` 与它通信（只监听回环，局域网内其它设备访问不到）。

**安装**

```bash
adb install dist/mcdev-console.apk
```

或把 `dist/mcdev-console.apk` 传到手机，点击安装（需允许「安装未知来源应用」）。

**首次使用前，Termux 里要做两件事**

1. 允许外部应用执行命令：

   ```bash
   mkdir -p ~/.termux
   echo "allow-external-apps=true" >> ~/.termux/termux.properties
   termux-reload-settings
   ```

2. 启动一次守护（会同时拉起控制台服务）：

   ```bash
   cd ~/qqbot && ./deploy/android/watchdog.sh start
   ```

   首次启动后，系统会给 App 授权「Termux: RUN_COMMAND」权限，
   在 **系统设置 → 应用 → MC收益 → 权限** 里允许即可。

**App 能做什么**

| 页面 | 功能 |
| --- | --- |
| 首页 | 机器人 / 守护的实时状态，一键启动、重启、停止 |
| 查询 | 快捷指令 + 输入框，直接看收益、地图、余额、图表 |
| 日志 | 查看机器人日志，每 3 秒自动刷新 |
| 配置 | 直接编辑 `.env` 并保存 |

连不上控制台时，App 会显示离线页，里面有一键启动按钮和排查步骤。

> 「停止」只会停机器人和守护，**控制台保持运行**，方便随时再启动；
> 要连控制台一起停，用 `./deploy/android/watchdog.sh shutdown`。

**自己重新构建 APK**

```powershell
python deploy\android\app\build_apk.py
```

需要 Android build-tools 34、platform android-35 和 **JDK 17**
（d8 在 JDK 21+ 上会崩），脚本会读取环境变量 `ANDROID_SDK`（默认 `C:\Android\sdk`）
与 `JDK17_HOME`（默认 `C:\Android\jdk17`）。产物在 `dist/mcdev-console.apk`。

---

## 六、保活设置（关键）

安卓对后台进程管得很严，不做下面几步，息屏后大概率被杀。

```bash
./deploy/android/keepalive.sh
```

脚本会自动写入 `~/.termux/boot/mcdev-watchdog.sh`（开机拉起守护）
并打开系统设置页。**剩下 4 项必须手动确认**：

| 设置 | 位置 | 目的 |
| --- | --- | --- |
| 电池优化 → 不优化 / 无限制 | 系统设置 → 电池 → 电池优化 → Termux | 防止息屏后被冻结 |
| 省电策略 → 无限制 | 应用详情 → 耗电管理 | 同上 |
| 允许自启动 / 后台活动 | 应用详情（各品牌叫法不同） | 防止被一键清理 |
| 最近任务里给 Termux 加锁 | 多任务界面下拉卡片 | 避免「一键清理」误杀 |

各品牌额外注意：

- **小米 / 红米**：设置 → 应用设置 → Termux → 省电策略「无限制」，
  并在「自启动管理」里打开。
- **华为 / 荣耀**：应用启动管理 → Termux → 改为「手动管理」，三项全开。
- **OPPO / vivo**：允许后台运行 + 关闭「智能省电」对 Termux 的限制。

> 手机插着充电线常开即可。机器人进程本身很轻，CPU 占用几乎为 0，
> 只在收到指令时才会请求接口并渲染图表。

---

## 七、常用命令

```bash
./deploy/android/watchdog.sh start     # 启动守护（同时拉起控制台）
./deploy/android/watchdog.sh status    # 查看状态
./deploy/android/watchdog.sh log       # 实时日志
./deploy/android/watchdog.sh stop      # 停止机器人（保留控制台）
./deploy/android/watchdog.sh shutdown  # 全部停止
./deploy/android/service.sh start      # 无守护的后台启动（临时调试用）
```

> `watchdog.sh` 与 `service.sh` 管理同一个 `bot.pid`，**不要同时运行**。
> 长期挂机用 `watchdog.sh`。

---

## 八、常见问题

**Q：需要 root 吗？**
不需要。整个方案只用到 Termux 普通权限。

**Q：需要电脑配合吗？**
不需要。部署完成后手机独立运行，电脑关机不影响。

**Q：需要公网 IP 或端口映射吗？**
不需要。官方机器人是**出站长连接**，路由器不用做任何设置。

**Q：耗电和流量大吗？**
待机时进程基本空闲，仅维持一条 WebSocket 心跳。流量以 KB 计。
收到指令时才请求开发者平台并渲染图表。

**Q：图表中文变成方框？**
Termux 缺少 CJK 字体。可执行 `pkg install -y fontconfig` 后把中文字体
放进 `~/.fonts`；或直接在 `.env` 里设 `MCDEV_CHART_ENABLED=false` 关闭图表。

**Q：matplotlib 装不上？**
Termux 上需要现场编译，可能失败。不影响机器人运行——图表指令会自动降级为文字。
可先 `pkg install -y python-numpy` 再重试：
`~/qqbot/.venv/bin/pip install --no-build-isolation matplotlib`

**Q：定时推送会执行吗？**
会，但官方群聊主动消息有硬限（**每群每月 4 条**），且群主需在群设置里
打开「机器人主动在群聊内发言」。详见主 README。

**Q：挂一段时间就掉线？**
按第五节做保活：`watchdog.sh start`（唤醒锁 + 自动重启）+
电池优化白名单 + 允许自启动。这三样缺一不可。

**Q：想换手机 / 迁移？**
把整个 `qqbot` 目录拷过去，重跑 `install.sh` 即可，`.env` 会保留。
