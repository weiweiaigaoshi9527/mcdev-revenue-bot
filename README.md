# 我的世界开发者收益 QQ 机器人

基于 **NoneBot2 + OneBot v11** 的 QQ 机器人，接入《我的世界》中国版**开发者平台**
（https://mcdev.webapp.163.com/ ，接口基址 `mc-launcher.webapp.163.com`），可在 QQ 里
随时查询开发者账号下**各个地图（作品）的钻石收益、销量**，以及**日均 / 昨日 / 各月钻石收益**。

> 未配置登录 Cookie 时会自动进入**演示模式**，用示例数据跑通全部指令，方便先看效果。

---

## 一、功能一览

### 文字查询

| 指令 | 作用 |
| --- | --- |
| `收益 [天数]` | 最近 N 天总览：总钻石收益、总销量、付费人数、日均 |
| `地图 [天数]` | **各地图（作品）钻石收益与销量排行** |
| `昨日` | **昨日**钻石收益、销量与各地图明细 |
| `日均 [天数]` | **日均**钻石收益与销量，以及各地图日均 |
| `月报 [月数]` | **各月钻石收益**（总流水 / 开发者分成 / 销量） |
| `趋势 [天数]` | 最近 N 天每日收益明细 |
| `分成 [月数]` | **官方结算（真实）+ 团队贡献值分成（@ 成员）+ 规则推算（参考）** |
| `结算` | **查看平台官方结算单**（当月收益 / 鼓励金额 / 税费等真实数值） |
| `成员` | 列出当前群成员与 QQ 号，并标出命中 `MCDEV_PARTNERS` 的成员 |
| `推送测试 [目标]` | **立即执行一次推送**（预览效果），不传目标则用配置的 `MCDEV_PUSH_TARGETS` |
| `状态` | 检查开发者平台登录态 |
| `帮助` | 使用说明 |

消息署名与图表 logo 会自动带上**开发者账号的昵称与头像**（取自平台 `users/me`）。

### 图表推送（直接返回图片）

| 指令 | 作用 |
| --- | --- |
| `图表 [天数]` | **收益看板**：各地图收益排行 + 每日趋势（默认 14 天） |
| `排行图 [天数]` | 各地图钻石收益**横向条形图**，含销量标注 |
| `趋势图 [天数]` | 每日钻石收益**折线图**（**默认展示「起始日 → 现在」的完整趋势**，带天数则只看最近 N 天，叠加销量虚线） |
| `月报图 [月数]` | 各月**总流水 / 开发者分成**对比柱状图 |

支持别名，例如 `总览 / overview / sy`、`图表 / 收益图 / 看板`、`月报图 / 月度图` 等。
定时推送可通过 `.env` 开启，支持**每天多个时间点**（`MCDEV_PUSH_HOURS=10,12,14,16,18,20,22,0`），并可附带看板图片（`MCDEV_PUSH_CHART=true`）。
若运行环境未安装 matplotlib，图表指令会自动降级为文字输出，不影响机器人运行。

钻石与人民币约 **1 元 = 100 钻石**，消息中会同时给出钻石数与折算金额。

---

## 二、目录结构

```
qqbot/
├── bot.py                     # 机器人启动入口
├── requirements.txt
├── .env.example               # 配置模板（复制为 .env）
├── mcdev_bot/
│   ├── config.py              # 配置 + 平台/接口映射
│   ├── models.py              # 数据模型（对应平台真实字段）
│   ├── client.py              # 开发者平台接口客户端（真实数据）
│   ├── mock.py                # 演示数据源（无 Cookie 时使用）
│   ├── service.py             # 聚合：各地图/昨日/日均/月度
│   ├── revenue.py             # 2026 新版分成规则 + 团队贡献值拆分
│   ├── profile.py             # 开发者昵称 / 头像（图表 logo）
│   ├── chart.py               # 图表渲染（收益图片）
│   ├── formatter.py           # QQ 文本排版
│   └── plugins/revenue/       # NoneBot 指令插件
├── preview/                   # 运行时生成的图片（自动创建，已 gitignore）
└── .cache/                    # 头像等运行缓存（自动创建，已 gitignore）
```

---

## 三、快速开始

### 1. 安装依赖

```powershell
cd C:\Users\weiwei\Documents\qqbot
python -m pip install -r requirements.txt
```

### 2. 部署 OneBot 实现（QQ 接入）

本机器人通过 **OneBot v11** 协议与 QQ 通信，使用 **NapCatQQ**。

**本机已完成的配置**（NapCat v4.18.28）：

- 程序目录：`F:\NapCat`（解压自官方 `NapCat.Shell.zip`，SHA256 已校验）
- 反向 WS 配置：`F:\NapCat\config\onebot11.json`
  已预置指向 `ws://127.0.0.1:8080/onebot/v11/ws`，`enable: true`
- 本机为 **Windows 10**，因此启动脚本用 `launcher-win10.bat`

**接下来只需三步：**

1. **退出当前已登录的 QQ**（NapCat 要自己拉起 QQ 进程，同时运行会冲突）。
2. 双击 `F:\NapCat\launcher-win10.bat`（会请求管理员权限，允许即可）。
3. 弹出的 QQ 登录窗口扫码登录 —— **建议用专门的 QQ 小号，不要用主号**。

登录成功后，NapCat 会读取 `config/onebot11.json` 自动连上机器人，机器人日志会出现
OneBot V11 的连接记录（含 bot 的 QQ 号）。

> 备用入口：NapCat 控制台会打印 WebUI 地址与 token（默认 `http://127.0.0.1:6099/webui?token=xxx`），
> 若自动配置没生效，可在 WebUI 的「网络配置」里手动新建 **WebSocket 客户端（反向）**。
>
> 若注入失败（QQ 版本过新），按官方提示换用 NapCat 推荐的 QQ 版本
> （v4.18.28 说明中给出的是 `QQ9.9.26.44343_x64.exe`）。
>
> 机器人默认使用 `~fastapi` 驱动，**只支持反向连接**（NapCat 主动连机器人）。
> 若 NapCat 与机器人不在同一台机器，请把 `.env` 的 `HOST` 改为 `0.0.0.0`，
> 并在 URL 中使用机器人所在机器的局域网 IP。

### 3. 获取开发者平台 Cookie

1. 浏览器登录开发者平台：https://mcdev.webapp.163.com/
2. 按 `F12` 打开开发者工具 → **Network（网络）** 面板，刷新页面。
3. 点击任意一个 `mc-launcher.webapp.163.com` 的请求 → **Headers → Request Headers → Cookie**。
4. 复制 Cookie 的**完整值**（形如 `NTES_SESS=...; S_INFO=...; ...`）。

### 4. 配置 `.env`

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，至少填写：

```ini
# 反向 WebSocket：NapCat 主动连本机器人
HOST=127.0.0.1
PORT=8080
# 开发者平台凭证
MCDEV_COOKIE=粘贴上一步复制的 Cookie
MCDEV_PLATFORM=pe
MCDEV_CHART_ENABLED=true
# 暂无有效 Cookie 时，先用演示数据跑通
# MCDEV_MOCK=true
```

`MCDEV_PLATFORM` 可选值：

| 值 | 含义 |
| --- | --- |
| `pe` | 手机版组件（默认） |
| `pc` | 电脑版组件 |
| `jpe` / `jpc` | 手机版 / 电脑版联机 |

只想统计「地图」类作品时，可设置 `MCDEV_ITEM_KEYWORD=地图` 做名称筛选。

### 5. 启动

```powershell
python bot.py                  # 启动机器人
```

在 QQ 里私聊机器人或 @机器人 发送 `收益`、`地图`、`月报` 等指令即可。

---

## 四、接口说明（数据来源）

开发者平台**未提供公开 API**。本项目所用接口是通过分析平台前端打包资源还原，并已用真实开发者账号逐项验证：

| 方法 | 接口路径 | 说明 |
| --- | --- | --- |
| `get_user_info` | `users/me` | 当前登录开发者，用于校验 Cookie |
| `get_items` | `items/categories/{cate}/` | 名下作品列表（**必须先取到 `item_id`**） |
| `get_overview` | `data_analysis/overview/` | 平台账号级总览（官方口径） |
| `get_day_detail` | `data_analysis/day_detail/` | 按天明细（**本项目权威口径**） |
| `get_month_detail` | `data_analysis/month_detail/` | 按月明细（口径与 overview 不一致，仅备用） |
| `get_income_periods` | `incomes/?platform=` | 收益结算周期 |
| `get_item_incomes` | `items/categories/{cate}/{id}/incomes/` | 单作品收益明细 |

`{cate}` 取值：`pe`（手机版组件）/ `comp`（电脑版组件）/ `pe_multi` / `multi`。

### 调用要点（实测踩坑记录）

- `start_date` / `end_date` 必须是 **`YYYYMMDD`**（不带横线）。
- `order` 必须大写 **`ASC` / `DESC`**，写成小写会返回 `params error`。
- `item_list_str` **必填**，且必须传具体作品 ID（逗号分隔），否则返回空数据。

### 返回字段

- 按天：`dateid`、`iid`、`res_name`、`diamond`（钻石收益）、`cnt_buy`（销量）、`download_num`（下载量）、`DAU`、`refund_rate`
- 按月：`monthid`、`total_diamond`、`sharable_flow`、`developer_share`、`cnt_buy`、`avg_day_buy`、`mau`

### 统计口径

以 `day_detail` 逐日数据聚合，并与平台 `overview` 官方口径做过一致性校验（近 14 天合计、
日均、本月、上月均逐项吻合）。因此：

- 「今天」不计入统计 —— 平台只出到**昨天**，本项目保持一致。
- 日均 = 区间收益 ÷ 区间自然天数（与平台 14 天日均算法一致）。
- 月报按**逐月单独查询再聚合**实现，避免超长区间返回不全；`month_detail` 的按月拆分与
  `overview` 对不上（合计相同、月界不同），故不作为月报来源。

鉴权方式为 **Cookie**（浏览器登录态），`MCDEV_COOKIE` 过期后需重新获取。
由于是平台内部接口，官方未承诺稳定性；若平台改版，只需调整 `mcdev_bot/client.py` 中的路径。

---

## 五、收益分成规则（2026 新版）

2026-01-01 生效的新版《开发者协议》重构了分成体系，本项目按该规则推算实际到账金额：

- **单作品独立核算**：不再看账号总流水，改为按**单个作品的自然月钻石流水**分别计算
- **阶梯递增**（流水越高比例越高）：

| 单个作品月钻石流水 | 分成比例 |
| --- | --- |
| < 100 万钻石 | 50% |
| 100 万 ~ 1000 万钻石 | 52.5% |
| ≥ 1000 万钻石 | 55% |

- **取消技术服务费**（旧版高流水作品最高被抽 30%）
- **计算公式**：`开发者收益 = 单作品可分成钻石流水 × 分成比例 + 专项补贴 − 违约金`
- **货币换算**：100 钻石 = 1 元

其中「可分成钻石流水」= 作品当月钻石流水 − 需分摊的生态成本。
生态成本比例会**自动按官方结算反推校准**（本项目实测 **33.88%**）；
如需固定值，可用 `MCDEV_ECOSYSTEM_COST_RATE` 覆盖。

> 官方 FAQ 示例校验：可分成流水 2200 万钻石 → 属 ≥1000万档 → 2200万 × 55% = **1210 万钻石**，
> 与本项目 `mcdev_bot/revenue.py` 的计算结果完全一致。

### 团队贡献值分成

`MCDEV_PARTNERS` 用于按贡献值把开发者收益拆分给团队成员：

```ini
MCDEV_PARTNERS=十方:10:QQ号,炜炜爱搞事:30:QQ号,hisuperwan:60:QQ号
```

格式为 `名字:占比:QQ号`，多项用逗号分隔。QQ 号用于在群里 **@ 成员**，留空则只显示名字。
拆分采用「最后一位吃余数」的方式，保证各份之和精确等于总额。

**分成基准**为「**预计实际收益合计**」= 官方已结算收益 + 未结算月份的规则推算预估，
回溯月份由 `MCDEV_SPLIT_MONTHS` 控制（默认 12）。推送里会给出合计金额与每人所得。

**怎么查成员的 QQ 号？** 在群里发送 `成员` 指令，机器人会列出群成员及 QQ 号，
并自动标出命中 `MCDEV_PARTNERS` 的成员（匹配群名片 / 昵称，忽略大小写）。
也可以在 `.env` 里临时设置 `MCDEV_MEMBER_SCAN=群号`，机器人启动时会把成员列表打到日志。

### 官方结算（真实数值）

除「规则推算」外，机器人还会通过 `incomes/?platform=xxx` 读取**平台官方结算单**，
即开发者平台「收益结算」页的真实数值，`结算` 指令可单独查看：

| 字段 | 含义 |
| --- | --- |
| `income` | 当月收益（元） |
| `available_income` | 累计可结算收益（元） |
| `total_diamond` | 累计消耗钻石 |
| `sharable_flow` | 可分成钻石流水 |
| `developer_share` | 开发者分成（钻石） |
| `incentive_income` | 鼓励金额（元） |
| `pay_punish_fee` | 罚款金额（元） |
| `play_plan_income` | 畅玩计划收益（元） |
| `total_usage_price` | 网络服估计用量成本（元） |
| `tax` | 税费（元） |

平台结算通常**次月 10 日左右出账**，因此最新月份可能还没结算记录。

> ⚠ 注意：官方结算的「累计消耗钻石」与按 `day_detail` 逐日累加的结果可能不一致
> （官方口径更小），所以「规则推算」只作参考，**以官方结算为准**。
> 官方结算里还能反推出真实的**生态成本分摊比例**与**分成比例**，可用于校准
> `MCDEV_ECOSYSTEM_COST_RATE`。

---

## 六、图表推送说明

图表由 `mcdev_bot/chart.py` 用 matplotlib（Agg 无界面后端）渲染，直接以 PNG 字节流发送，
**不落盘、不依赖浏览器或外部截图服务**，渲染在线程池中执行，不会阻塞机器人事件循环。

相关配置：

| 配置项 | 默认 | 说明 |
| --- | --- | --- |
| `MCDEV_CHART_ENABLED` | `true` | 关闭后所有图表指令自动降级为文字输出 |
| `MCDEV_CHART_TOP_N` | `8` | 排行图 / 看板中展示的作品数量上限 |
| `MCDEV_TREND_START` | 空 | 趋势图起始日期（如 `2026-08-11`）；留空则默认最近 90 天 |
| `MCDEV_PUSH_CHART` | `true` | 定时推送时是否附带看板图片 |

**中文字体**：程序会自动探测并注册中文字体，顺序为

1. Windows：`微软雅黑（msyh.ttc）` → `黑体（simhei.ttf）` → `宋体（simsun.ttc）`
2. Linux：`Noto Sans CJK` → `文泉驿微米黑（wqy-microhei）` → `文泉驿正黑`

Linux 服务器若出现方块字，安装任一 CJK 字体即可：

```bash
# Ubuntu / Debian
sudo apt install -y fonts-noto-cjk
# CentOS / RHEL
sudo yum install -y google-noto-sans-cjk-fonts
```

---

## 七、常见问题

**Q：不填 Cookie 能用吗？**
可以。会进入演示模式，用示例数据返回结果，用于验证机器人链路。
也可手动在 `.env` 中设置 `MCDEV_MOCK=true` 强制使用演示数据。

**Q：怎么从演示数据切换到真实数据？**
把 `.env` 中的 `MCDEV_MOCK` 改为 `false`（或删除该行），并填写有效的 `MCDEV_COOKIE`，然后重启机器人。

**Q：机器人收不到消息？**
按顺序检查：NapCat 是否登录成功；反向 WS 地址是否为 `ws://127.0.0.1:8080/onebot/v11/ws`；`.env` 的 `PORT` 与之一致；若设了 Token 两边是否相同。另外命令需带 `/` 前缀，或直接 @机器人。

**Q：怎么更换 NapCat 登录的 QQ 号？**
1. 以**管理员身份**结束进程：`taskkill /f /im QQ.exe` 与 `taskkill /f /im NapCatWinBootMain.exe`
   （NapCat 以管理员权限运行，普通权限会提示 Access is denied）
2. 删除登录缓存：`Remove-Item F:\NapCat\cache -Recurse -Force`（强制重新出二维码）
3. 重新运行 `F:\NapCat\launcher-win10.bat`，用**新号**扫码
4. 若 QQ 登录窗默认显示旧号的一键登录，务必先点「切换账号」

新号首次登录时，NapCat 会自动把 `config/onebot11.json` 复制为 `onebot11_<新QQ号>.json`，
因此反向 WS 配置会被自动继承，无需重新配置。旧号的配置文件可以安全删除。

**Q：`状态` 显示登录异常？**
Cookie 已过期，重新按第三节步骤获取并更新 `.env`，然后重启 `bot.py`。

**Q：想改推送时间？**
在 `.env` 中设置：

```ini
MCDEV_PUSH_ENABLED=true
MCDEV_PUSH_TARGETS=群号或QQ号        # 多个用逗号分隔
MCDEV_PUSH_HOURS=10,12,14,16,18,20,22,0   # 每天推送的小时，可填多个
MCDEV_PUSH_MINUTE=0                  # 分钟，对所有小时生效
MCDEV_PUSH_CHART=true                # 是否附带收益看板图片
```

`MCDEV_PUSH_HOURS` 支持任意多个时间点，例如只推早晚两次就填 `9,21`。
旧的单值写法 `MCDEV_PUSH_HOUR=9` 仍然兼容。

**Q：图表发出来是文字？**
说明当前环境未安装 matplotlib，或 `MCDEV_CHART_ENABLED=false`。执行 `python -m pip install matplotlib` 即可。

**Q：图表中文变成方框？**
运行环境缺少中文字体，参考第五节的字体安装说明。

---

## 八、免责声明

本项目仅用于开发者查看**自己的**账号收益数据，请勿用于抓取他人数据或任何商业用途。
接口为分析平台前端所得，使用时请遵守《我的世界》开发者协议与平台相关规定。
