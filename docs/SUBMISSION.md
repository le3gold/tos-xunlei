# 应用中心提审稿 — 迅雷 for TOS 7

直接把本文件里的字段照抄进 https://developer.terra-master.com/#/home/dashboard 即可。
依据：《TOS 7 Application Development Guide》第 15 章（发布流程）、第 16 章（审核标准）。

---

## 1. 平台表单要填的字段

### Step 4：[My Applications] → [Add Application]

| 字段 | 填写内容 |
|---|---|
| Application ID | `le3gold-xunlei` |
| Application Package Type | **Deb** |
| Repository URL | `https://github.com/le3gold/tos-xunlei` |

> 应用 ID 一旦发布**不可修改**，改名只能重新作为新应用提审。

### Step 5：提交一个版本

> 依据 2026-09-23 的指南更新（第 04 章 `7be7310`、第 03 章 `a024516`）：
> **平台已取消手工填写的版本号字段**（原 `Version To List`）。提交动作 = 在该页面
> **选中你仓库 Releases 里的一个 tag**，平台从该 Release 下载包来审。版本号由平台
> 从包内的 `config.ini` 读取，`config.ini.version` 是唯一权威来源；`DEBIAN/control`
> 的 `Version` 仍会被校验，必须与它一致。

| 项 | 当前值 | 说明 |
|---|---|---|
| `config.ini` 的 `version` | `1.0.0` | **权威**：平台以此为准 |
| `DEBIAN/control` 的 `Version` | `1.0.0` | 仍被校验，必须与上一致 |
| GitHub Release tag | `v1.0.0` | 新规则下**不参与版本判定**，仅用于挑选包 |

> ⚠️ 指南目前**自相矛盾**，提审时按下面的稳妥做法处理：
> 第 04 章已改为"tag 不必等于 `config.ini.version`、版本不由 tag 决定"，但第 15 章
> 的 Step 3 / Step 5 / Step 6 仍是旧规则（"tag 必须与 `config.ini.version` 完全
> 一致，否则自动驳回"），第 15 章 Step 3 的资源命名也仍写成强制。本包让 tag 与
> 版本**同名**、资源名用推荐格式，因此两套说法下都合规。建议同步反馈文档组把
> 第 15 章对齐到第 04 章。

---

## 2. Release 核对

| 要求 | 状态 |
|---|---|
| 仓库公开 | ✅ `https://github.com/le3gold/tos-xunlei`（public） |
| 包放 Release 资源，不放仓库根目录 | ✅ 仓库根目录无任何 `.deb`（`.gitignore` 已排除） |
| Release tag | ✅ `v1.0.0`（新规则下 tag 自由，取与版本同名只为可读） |
| 资源命名（新规则为"推荐名"，平台实际只按扩展名 `.deb` 判定包型） | ✅ `le3gold-xunlei_x86_64.deb` |
| 每个二进制资源附 SHA-256 | ✅ `le3gold-xunlei_x86_64.deb.sha256` |
| 一个 Release 只有一个架构、一种包格式 | ✅ 仅 `x86_64` 的单一 deb |
| 资源长期可用、不删除 | ⚠️ 需保持仓库与 Release 长期不删（已发布资源不得删除） |

Release 地址：
`https://github.com/le3gold/tos-xunlei/releases/tag/v1.0.0`

资源直链：
`https://github.com/le3gold/tos-xunlei/releases/download/v1.0.0/le3gold-xunlei_x86_64.deb`

---

## 3. 包内自述信息（审核会与仓库逐项比对）

| 项 | 值 |
|---|---|
| 应用名称 | 迅雷 |
| 应用 ID | `le3gold-xunlei` |
| 版本 | `1.0.0` |
| 平台 | `x86_64` |
| 架构 | `amd64` |
| 发布者 | `le3gold` |
| 分类 | `["Download"]` |
| 打开方式 | iframe 小窗（`type: iframe`，`path: /le3gold-xunlei/`，窗口 1180×680，可缩放/最大化） |
| 运行用户 | `le3gold-xunlei`（专用非 root 用户） |
| 共享文件夹 | `XunLeiPlus` |
| 依赖 | `systemd, bash`（均为 TOS 自带） |
| 主页 / 帮助 | `https://github.com/le3gold/tos-xunlei` |

## 4. 提审用文案

**中文（app.lang `[zh-cn].descript`）**

> 迅雷远程下载：支持磁力链（thunder://）、FTP、HTTP 等下载链接，使用迅雷官方
> 3.23.7 引擎。在 TOS 应用中心点开即用小窗打开迅雷官方界面，扫码登录后可远程
> 添加与管理下载任务；下载内容保存在共享文件夹 XunLeiPlus 中，可直接通过
> SMB/NFS 取用。

**English（`[en-us].descript`）**

> Xunlei remote download station for TerraMaster TOS 7, built on the official
> Xunlei 3.23.7 engine. Open it from App Center and the official Xunlei UI
> appears in an embedded window; sign in by QR code to add and manage remote
> download tasks. Finished downloads are stored in the shared folder
> XunLeiPlus and stay reachable over SMB/NFS.

**Release note（`release_note`）**

> 首次发布：使用迅雷官方 3.23.7 引擎，功能与迅雷官方 NAS 版保持一致。

> ⚠️ 合规提醒：`descript` 只描述**实际可用**的功能，不要写"加速""私有云盘"等
> 夸大表述（审核标准 16.2「描述与实际功能一致」）。

---

## 5. 权限声明（对应指南 10.8）

| 权限 | 用途 |
|---|---|
| 网络：端口 `18889` | 迅雷引擎提供本机 WebUI，由平台 nginx 反向代理 |
| 网络：端口 `18890` | 迅雷引擎对外通报的公开端口 |
| 网络：出站连接 | 登录迅雷账号、拉取云端配置、传输下载数据 |
| 文件系统：`/var/lib/le3gold-xunlei` | 运行态数据、日志、登录态、引擎自更新副本 |
| 文件系统：`/usr/local/le3gold-xunlei` | 程序本体（服务只读） |
| 共享文件夹：`XunLeiPlus` | 用户可见的下载内容（SMB/NFS） |
| 共享文件夹 ACL：所载卷根的**穿越**权限 | TOS 7 的 tmacl 默认拒绝所有非 root 用户穿越卷根，文件夹自身的 ACL 因此不可达。`postinst` 为**本应用自己的用户**补一条 `r-x`（仅穿越、不继承）。这是对平台缺陷的最小修复，见 `docs/PLATFORM-DEFECT.md`；`postrm` 卸载时删除 |
| 系统用户：`le3gold-xunlei` | 非 root 身份隔离运行 |
| root 权限 | **无** |
| 系统目录写入 | **无**（生命周期脚本安装 systemd 单元与 nginx 片段属平台既有模型，见官方模板 `DEBIAN/postinst`；另见下方第 7 节 `/etc/os-release` 特例） |

不声明、也不使用：特权模式、`network_mode: host`、跨应用数据目录、多余端口。

---

## 6. 运行期文件清单（指南 12.9.6 必填）

完整表格见仓库 `README.md` 同名小节，摘要：

| 路径 | 用途 | 卸载时 |
|---|---|---|
| `/usr/local/le3gold-xunlei/**` | 程序、引擎、nginx 片段、systemd 单元、`webui.bz2` | 删除 |
| `/usr/local/le3gold-xunlei/webui/**` | iframe 小窗加载页 | 删除 |
| `/var/lib/le3gold-xunlei/{bin,.drive,download}/`、`pan-cli.log`、`pan-cli.pid*` | 运行态、登录态、引擎日志、PID、下载回退目录 | 删除 |
| `/Volume1/XunLeiPlus/download/**` | **用户数据**：下载完成的文件 | **保留** |
| `/etc/nginx/conf.d/le3gold-xunlei.conf` | 反代 `/le3gold-xunlei/app/` → `127.0.0.1:18889` | 删除 |
| `/etc/systemd/system/le3gold-xunlei.service` | 服务单元 | 删除 |
| `/var/log/le3gold-xunlei-maint.log` | 生命周期脚本日志 | 删除 |
| `/etc/os-release` | 仅在缺失或运行用户不可读时修复，见第 7 节 | 不改内容 |

---

## 7. 需要向审核员主动说明的几点

### 7.1 `/etc/os-release` 修复

旧版迅雷应用会把它换成运行用户不可读的符号链接、停服时还会删除；迅雷引擎读不到
就 `panic: platform not suport`。`postinst` 只在**缺失或运行用户不可读**时修复，
内容取自包内 `os-release`，并**从不修改已有可读文件的内容**。

### 7.2 应用从系统盘的运行时副本启动（说明，非权限申请）

TOS 会把应用文件迁移到 `/Volume*/@apps/<appid>/`（指南 10.7）。
实测该路径对非 root 运行用户不可访问：`/Volume1/@apps` 起全部 `EACCES`，
`tmacltool` 授权后也不生效（连 TOS 自带应用的用户访问自己的应用目录同样被拒）。
服务因此连 `WorkingDirectory` 都设不进去，systemd 报 `200/CHDIR`，页面 502。

本包的处理是：`postinst` 把入口脚本、启动器、引擎复制到
`/var/lib/le3gold-xunlei/runtime/`（系统盘，属主为应用用户），systemd 从该副本启动。
包内原始文件仍完整保留在应用目录中，只是服务运行时不依赖它。
这是**读取自己的文件**，不涉及任何额外系统权限；见运行期文件清单。
### 7.2 共享文件夹 ACL（平台缺陷 + 最小绕过）

`postinst` 按指南 10.6 调用 `ter_share_add -name XunLeiPlus -owner le3gold-xunlei`，
并在文件夹本体上给应用用户授权；这一步是标准做法，但**只做这一步，文件夹依然不可用**。

原因在卷根：`/Volume*` 以 `tmacl` 挂载，这套 TerraMaster 富 ACL 是**默认拒绝**，
且**不回落到 POSIX mode 位**。真机实测（TOS 7，内核 6.12.63）：

| 观测 | 结果 |
|---|---|
| `ls -ld /Volume1` | `drwxr-xr-x+`（755，别的用户本应可穿越） |
| `tmacltool get /Volume1` | **空**（全机所有卷根都没有任何 ACL 条目） |
| `tmacltool get-perm /Volume1 <应用 uid>` | `max_permission: -------------` |
| 以应用用户 `ls /Volume1` | `Permission denied` |
| 以内置 `qbittorrent`/`transmission`、以及普通 TOS 用户身份 | 同样 `Permission denied` |

穿越一个路径需要**每一层**都有权限。共享文件夹自身的条目是对的，但上方卷根一个
条目都没有，于是它永远不可达 —— 这正是 `ter_share_add -owner` 单独用不够的原因。

本包的处理：`postinst` 为**本应用自己的用户**、在**承载该文件夹的那个卷**上补一条
`r-x`（仅穿越，无继承）。读写权限仍全部来自文件夹本体的条目，这条只解决"够得着"。
这是对平台缺陷的最小修复，完整取证、构造方法、以及平台该怎么修见
`docs/PLATFORM-DEFECT.md`；`postrm` 会在卸载时删掉它。平台修好后本包应立即删除
这段代码。

启动脚本不再尝试改 ACL（它以应用用户身份运行，本来就改不动），改为实测下载目录
可写性；只有在授权仍然缺失时才回退到 `/var/lib/le3gold-xunlei/download` 并**明确告警**
（系统盘仅剩约 3.2 GB，这个回退绝不应该是常态）。

### 7.3 标题栏是应用自己画的

TOS 桌面不给 `type: "iframe"` 的应用渲染标题栏，而是把一条 40px 高的
`.tos-dialog-menu.micro`（拖拽区 + 帮助/最小化/最大化/关闭按钮）覆盖在窗口顶部，并吃掉
这一条的鼠标事件。迅雷自身的工具栏正好在那里，会被桌面的关闭按钮压住。因此入口页在顶部
自绘了一条 41px 的标题栏（样式对齐原生 `.tos-dialog-header`），把迅雷界面推到覆盖层下方。
这不涉及任何额外权限，只是页面内的布局。

---

## 8. 提交前自查

### 8.1 一票否决项（16.4）

| 项 | 本包 |
|---|---|
| 以 root 运行 | 否 ✅ |
| 特权模式 | 不适用（Deb） ✅ |
| 恶意代码 / 数据窃取 | 无 ✅ |
| 应用 ID 重复 | 已确认平台与 App Center 无 `le3gold-xunlei` ✅ |
| 校验和不匹配 | 与 Release 资源一致 ✅ |
| `app.lang` 任一语言 `name`/`descript` 为空 | 14 种语言全部填写 ✅ |
| `config.ini` 单引号或注释 | 严格 JSON，无注释 ✅ |
| 包架构与 `platform` 不一致 | 均为 x86_64/amd64 ✅ |

### 8.2 自动校验项（16.1）

| 项 | 本包 |
|---|---|
| `config.ini` JSON 合法、无注释、无尾逗号 | ✅（用 `tools/verify_deb.py` 复验） |
| `type` 与 `open_path` 互斥 | ✅ 只用 `type: iframe` |
| 版本号四处一致、格式 `xx.yy.zzz` | ✅ `1.0.0` |
| `app.lang` 14 种语言齐全、UTF-8 无 BOM、LF 换行 | ✅ |
| 图标为 SVG、含 `viewBox`、路径与 `icon` 一致 | ✅ `/images/icons/le3gold-xunlei.svg` |
| 目录名全小写、与 `config.ini` 声明一致 | ✅ |
| SHA-256 与上传资源一致 | ✅ |

### 8.3 四维度（16.2）

| 维度 | 本包情况 |
|---|---|
| 配置完整性 | 官方单包模板的同款目录结构（`config.ini` / `<id>.lang` / `bin/` / `images/` / `init.d/` / `nginx/` / `webui.bz2` / `DEBIAN/`）；单元含 `User/Group` 非 root、`StartLimitBurst=5`、`StartLimitIntervalSec=60`、`ProtectSystem=strict`、`NoNewPrivileges=true` |
| 功能可用 | 真机验证：安装/启动/停止/卸载、端口监听、nginx 反代 200、API 可达、覆盖安装幂等（见 `docs/HARDWARE-VERIFICATION.md`） |
| 安全 | 无硬编码凭据、无网络型生命周期脚本（不 `apt/pip install`、不 `curl \| bash`）、无 `/etc/hosts` 等敏感写入、`ProtectSystem=strict`、日志不含敏感信息、二进制 `sha256` 逐字节校验 |
| 合规 | 仓库公开、README 完整、目录结构符合 8.2、`descript` 与实际功能一致 |

> 包结构由 `python build.py` 内置的 **独立验证器（230 项断言）** 复核：
> 重新解析 `ar` 与两个 tar，逐项检查 `config.ini`、14 语言、systemd 单元、
> nginx 片段、生命周期脚本、二进制 sha256。验证不通过则构建失败。

---

## 9. 已知风险（提审前需要决策）

1. **知识产权 / V6 红线（最大风险）**：包内是迅雷闭源商业引擎，从迅雷官方 CDN 与
   官方 SPK 取得。审核标准 16.2「合规」要求"不侵犯第三方著作权"，一票否决项之外
   仍可能在初审判 IP 时被拒。本包按**厂商渠道构建**定位；若以第三方身份提审，
   建议先取得迅雷的再分发授权，或在提审说明中附上合作背景。
2. **再分发授权**：TerraMaster 是迅雷 NAS 官方合作伙伴（迅雷官网合作伙伴列表已含
   TerraMaster），但公开再分发仍需授权确认。
3. **自动更新不受覆盖**：迅雷云端的 `versions.info.amd64` 过滤条件是
   `platform in [synology, linux]`，**不含 terramaster**（本应用日志里可见
   `filter not match ... ["platform","in","synology","linux"]`）。因此引擎不会自动
   升级到新版本，换版本要重新打包；也正因为这个过滤条件，TOS 上的迅雷一直停在
   2.9.1 —— 建议同步推动迅雷把 `terramaster` 加进该名单，那样存量设备可自动升级。

---

## 10. 提交后流程与时间线

1. 自动校验（实时）→ 通过后生成工单
2. 初审：信息一致性、仓库合规、知识产权
3. 安全审核（技术支持）→ 功能与兼容性测试（测试支持）→ 综合审核
4. 通过后 1–2 个工作日内上架应用中心；开发者后台 [My Applications] 状态变为 Published

审核结果通过**平台站内消息**与**注册邮箱**双通道通知。

---

## 11. 本机已完成的验证（可直接引用于提审说明）

- 应用 ID / 版本 / 平台 / 资源名 / sha256：
  `le3gold-xunlei` / `1.0.0` / `x86_64` / `le3gold-xunlei_x86_64.deb` /
  `fc6f9b9e2bdf54eb5307257067d652a72856f6efb78a589570305ed2b4fe2ce8`
- 真机：TOS 7（内核 6.12.63）安装后服务 `active` + `enabled`，引擎上报
  `download_paths: ["/Volume1/XunLeiPlus/download/"]`，且以应用用户身份实测可写该目录；
  `http://<NAS>:8181/le3gold-xunlei/app/` 返回 200，静态资源 200（1,527,665 字节），
  `POST …/device/info/watch` 返回 403 JSON 鉴权响应（说明请求真实到达迅雷 API）。
- 引擎与启动器的来源、大小、`sha256`/`md5` 记录在包内
  `/usr/local/le3gold-xunlei/PROVENANCE.md`。