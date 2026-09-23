# 迅雷 for TOS 7 应用中心

把迅雷官方的下载引擎 **3.23.7** 封装成 TOS 7 的应用（`deb` + `iframe` 小窗），
在应用中心里点开就是**迅雷官方 WebUI**，以独立小窗形式打开。

- 提审稿（要填进开发者后台的字段、自查清单）：`docs/SUBMISSION.md`
- 调研过程与结论：`docs/RECON.md`
- 真机实测记录：`docs/HARDWARE-VERIFICATION.md`
- 上游来源与校验值：包内 `/usr/local/<应用ID>/PROVENANCE.md`

## 产物一览

| 项 | 值 |
|---|---|
| 应用 ID | `le3gold-xunlei` |
| 应用名称 | 迅雷 |
| 版本 | `1.0.0`（发布 tag `v1.0.0`） |
| 平台 / 架构 | `x86_64` / `amd64` |
| 打开方式 | **iframe 小窗**（`type: iframe`、`path: /le3gold-xunlei/`、可缩放、可最大化/最小化） |
| 发布包名 | `le3gold-xunlei_x86_64.deb`（**文件名不带版本号**，版本由 tag 决定） |
| 下载引擎 | `xunlei-pan-cli 3.23.7`（上游 linux 构建） |
| 启动器 | `xunlei-pan-cli-launcher.amd64` |
| 端口 | `18889`（引擎 WebUI，本机/内网）、`18890`（对外映射端口） |
| 共享文件夹 | `XunLeiPlus`，下载落到 `XunLeiPlus/download/` |
| 运行用户 | 平台按 `config.ini.user` 创建的 `le3gold-xunlei`（非 root） |

## 构建

```bash
python build.py
```

- 首次构建会联网下载引擎（迅雷官方 CDN）与启动器（迅雷官方 SPK），
  之后使用 `build/` 缓存。
- 输出：
  - `out/le3gold-xunlei_1.0.0_amd64.deb` — 本地安装用
  - `out/le3gold-xunlei_x86_64.deb` — **提交应用中心用**（文件名不带版本）
  - `out/le3gold-xunlei_x86_64.deb.sha256`
- 构建结束会自动运行 `tools/verify_deb.py`：它独立解析 `ar` 与两个 tar，
  对包结构、`config.ini`、14 种语言文案、systemd 单元、nginx 片段、
  生命周期脚本、二进制 sha256 做 222 项断言。**验证不通过则构建失败。**

## 安装

应用中心安装时，平台会根据 `config.ini.user` 创建运行用户并创建共享文件夹。

手动 `dpkg -i` 验证（平台不参与，需自己补一步建用户）：

```bash
sudo useradd -r -M -s /usr/sbin/nologin le3gold-xunlei
sudo dpkg -i le3gold-xunlei_x86_64.deb
systemctl status le3gold-xunlei
```

打开：`http://<NAS>:8181/le3gold-xunlei/`

## 提交应用中心需要的信息

| 字段 | 值 |
|---|---|
| 应用 ID | `le3gold-xunlei` |
| 仓库地址 | https://github.com/le3gold/tos-xunlei |
| 版本 | `1.0.0`（tag `v1.0.0`） |
| Release 资源 | `le3gold-xunlei_x86_64.deb`（+ `.sha256`） |
| 发布者 | `le3gold` |

平台按 `<应用ID>_<平台>.deb` 从仓库 Release 取包，所以资源名必须正好是
`le3gold-xunlei_x86_64.deb`，不带版本号。

## 权限声明（指南 10.8）

| 权限 | 用途 |
|---|---|
| 网络：端口 `18889` | 迅雷引擎在本机/内网提供 WebUI，由平台 nginx 反向代理 |
| 网络：端口 `18890` | 迅雷引擎对外通报的公开端口（P2P/加速通道） |
| 网络：出站连接 | 登录迅雷账号、拉取云端配置、下载任务数据 |
| 文件系统：`/var/lib/le3gold-xunlei` | 引擎运行态数据、日志、登录态、引擎自更新副本 |
| 文件系统：`/usr/local/le3gold-xunlei` | 程序本体（服务只读） |
| 共享文件夹：`XunLeiPlus` | 用户可见的下载内容，SMB/NFS 可取 |
| 用户：`le3gold-xunlei`（系统用户） | 以非 root 身份隔离运行服务 |
| 系统目录写入 | **无**（唯一例外见下方 `/etc/os-release` 修复） |
| root 权限 | **无**（`User=root` 被审核红线禁止，本包不使用） |

## 运行期文件清单（指南 12.9.6，必填）

| 路径 | 何时创建 | 用途 | 卸载时 |
|---|---|---|---|
| `/usr/local/le3gold-xunlei/**` | 安装解包 | 程序、启动器、引擎、nginx 片段、systemd 单元、`webui.bz2`、`PROVENANCE.md` | 删除 |
| `/usr/local/le3gold-xunlei/webui/**` | `postinst` 解开 `webui.bz2` | iframe 小窗的加载页（`index.html` 里嵌 `<iframe src="./app/">`） | 删除 |
| `/var/lib/le3gold-xunlei/bin/` | 首次启动 | 启动器 unix socket 目录 | 删除 |
| `/var/lib/le3gold-xunlei/.drive/**` | 首次启动 | 登录态、下载进度、引擎自更新后的副本 | 删除 |
| `/var/lib/le3gold-xunlei/download/` | `postinst` / 首次启动 | 下载回退目录（共享目录不可写时使用） | 删除 |
| `/var/lib/le3gold-xunlei/runtime/**` | `postinst`，每次安装/升级刷新 | 运行用户可读的**可执行文件副本**（入口脚本 + 启动器 + 引擎） | 删除 |
| `/var/lib/le3gold-xunlei/{CidStore.DB,seq_id,setting.cfg}` | 首次启动 | 引擎写在其工作目录下的状态文件 | 删除 |
| `/var/lib/le3gold-xunlei/pan-cli.log` | 首次启动 | 引擎日志（10MB 轮转） | 删除 |
| `/var/lib/le3gold-xunlei/pan-cli.pid`、`pan-cli.pid.child` | 首次启动 | 启动器与引擎 PID | 删除 |
| `/Volume1/XunLeiPlus/download/**` | `postinst` | **用户数据**：下载完成的文件，SMB/NFS 可见 | **保留** |
| `/etc/nginx/conf.d/le3gold-xunlei.conf` | `postinst` | 把 `/le3gold-xunlei/app/` 反代到 `127.0.0.1:18889` | 删除 |
| `/etc/systemd/system/le3gold-xunlei.service` | `postinst` | 服务单元 | 删除 |
| `/var/log/le3gold-xunlei-maint.log` | `postinst` | 生命周期脚本日志 | 删除 |
| `/etc/os-release` | `postinst`，**仅当缺失或运行用户不可读时** | 修复被旧版迅雷破坏的发行版标识 | **不修改发行版内容**，见下节 |

## 三处需要知道的行为

### 1. `/etc/os-release` 修复

迅雷引擎在识别运行平台时会读 `/etc/os-release`，**读不到就直接 `panic: platform not suport`**。

TOS 上旧版迅雷应用（`xunleipan 2.9.1`）把 `/etc/os-release` 换成了指向自己目录的符号链接
（且停止服务时会直接 `unlink` 掉），该文件对普通用户不可读。旧版迅雷以 uid 0 运行所以没暴露，
本包以非 root 运行就会踩到。

`postinst` 的处理：

- 文件不存在 → 用包内自带的 `os-release` 恢复一份 `0644`；
- 文件存在但运行用户读不了 → 复制内容到临时文件、`chmod 0644` 后替换（**不动发行版内容**）；
- 已经可读 → **完全不碰**。

`bin/le3gold-xunlei` 启动时也会再检查一次并给出明确告警，可用
`sudo dpkg-reconfigure le3gold-xunlei` 重跑修复。

### 2. 共享文件夹权限与下载回退

`/Volume*` 以 `tmacl` 选项挂载，由 TerraMaster 的 Rich ACL（内核模块 `tmacl_vfs`）管控：
**非 root 用户默认无法在其中写入**，必须对该用户显式授权。本包按官方指南 10.6 与
一方应用（qBittorrent / Transmission）完全一致的做法处理：

```bash
ter_share_add -name XunLeiPlus -owner le3gold-xunlei
tmacltool modify /Volume1/XunLeiPlus "user:le3gold-xunlei:allow:rwxpdDaARWc:fd"
```

如果平台没有（或还没）授好权，`bin/le3gold-xunlei` 会**实测共享目录是否可写**：
不可写时自动把下载目录回退到 `/var/lib/le3gold-xunlei/download` 并在日志里明确告警，
而不是让每个任务都失败。

> 实测备注：测试机（TOS 7，内核 6.12.63）上即使是 TOS 自带应用的运行用户，
> 也无法写入 `/Volume1` 下任何目录（含 777 目录），ACL 已授权的情况下依然 `EACCES`。
> 这属于该机器的 ACL 层状态，不是本包引入的问题；本包因此必须带这个回退。

### 3. 应用文件被平台放到存储卷上，运行用户可能读不到

TOS 会把第三方应用安装到存储卷：`/Volume1/@apps/le3gold-xunlei/`，
并把 `/usr/local/le3gold-xunlei` 做成指向它的符号链接（指南 10.7）。

问题在于 `/Volume*` 以 `tmacl` 挂载，而**运行用户对 `/Volume1/@apps` 及其下任何
目录都没有访问权**（权限位是 755，是 ACL 层拒绝的；`tmacltool` 授权后依然 `EACCES`）。
后果是 systemd 连 `WorkingDirectory` 都设不进去，服务以
`status=200/CHDIR` 失败，nginx 反代 502。

因此 `postinst` 会把入口脚本、启动器、引擎复制一份到
`/var/lib/le3gold-xunlei/runtime/`（系统盘，无 tmacl），属主为该应用用户；
systemd 从这份副本启动，`WorkingDirectory` 用应用状态目录。
这样服务完全不依赖 `/Volume1`，每次安装/升级都会刷新副本。

> 实测：真机上在装上该修复前，服务反复以 200/CHDIR 重启，页面上就是 502；
> 修复后服务 `active`、18889/18890 在听、`/le3gold-xunlei/`、
> `/le3gold-xunlei/app/` 均返回 200。
## 与《TOS 7 应用开发指南》的符合性

| 条目 | 做法 |
|---|---|
| 7 应用类型 | `iframe` 小窗：`type: iframe` + `path`，**未同时使用 `open_path`**（二者互斥） |
| 8.3 iframe 要求 | `webui.bz2`（固定文件名、扁平归档、根目录有 `index.html`）+ `/usr/local/<id>/nginx/<id>.conf` |
| 8.3 端口 | 使用 `18889/18890`，避开 22/80/443/8181/5050；引擎监听 `0.0.0.0`（非仅回环） |
| 8.12 | iframe 应用**不使用** `PrivateTmp=true`（否则 `/var/api`、`/var/log` 悬空） |
| 8.14 / 10.3 | `config.ini.user` = `le3gold-xunlei`，systemd `User=` 同名；生命周期脚本**不创建用户**；`User=root` 禁止 |
| 10.4 | 程序与配置对服务只读，只有数据/日志目录可写；`ProtectSystem=strict` + `ReadWritePaths` |
| 10.6 | 共享文件夹用 `ter_share_add -owner` 创建，并按一方应用方式补 Rich ACL |
| 10.7 / 12.1 | 包内布局与官方单包模板一致（`/usr/local/<id>`）；平台会把文件迁移到 `/Volume*/@apps/<id>`，本包为此提供运行时副本（见上文第 3 点） |
| 12.9.6 | 运行期文件清单见上 |
| 发布 | Release 资源名 `<应用ID>_<平台>.deb`，不带版本号 |
| nginx | 只用平台已定义的变量（TOS 的 nginx **没有** `$connection_upgrade`，故用字面量 `Connection upgrade`） |

## 来源与审计链

包内 `PROVENANCE.md` 记录每个二进制的下载地址、大小、`sha256`（启动器额外含 `md5`）。
构建脚本对缓存与下载结果逐字节校验，校验不过直接失败；`tools/verify_deb.py`
再从成品 deb 里反向校验一次。

上游：

- 引擎（迅雷官方 CDN，linux 构建）：`https://2rvk4e3gkdnl7u1kl0k.xbase.cloud/v1/file/pancli/amd64/xunlei-pan-cli.3.23.7.amd64`
- 启动器（迅雷官方 SPK 内成员 `bin/bin/xunlei-pan-cli-launcher.amd64`）：`https://down.sandai.net/nas/nasxunlei-DSM7-x86_64.spk`

## 已知限制

1. **V6 审核红线（最大风险）**：包内二进制须有公开可审计来源。迅雷引擎是闭源商业软件，
   第三方身份提审大概率被拒。本包应按**厂商渠道应用**定位。
2. **再分发授权**：迅雷引擎版权属于迅雷，公开再分发需要授权。
3. **共享目录 ACL 依赖平台**：见上文第 2 点，本包已做回退但首选仍是共享目录。
4. **换版本要重新核对**：引擎是自更新的（会往 `.drive/bin/` 放新副本），
   升级引擎版本后应重新跑 `build.py` 与真机验证。

## 成本最低的替代方案

请迅雷把 `terramaster` 加进
`https://2rvk4e3gkdnl7u1kl0k.xbase.cloud/v1/file/pancli/versions.info.amd64`
的 filter（当前是 `match: ["platform","in","synology","linux"]`）。
这样**所有已装 2.9.1 的 TOS 设备会自动升级到 3.23.7，零打包工作量**，
比重新打包更划算，也顺带解决长期维护。

## 参考

- 《TOS 7 Application Development Guide》（`terramaster-tos/tos-app-pkg-tools`）
- 一方应用最佳实践：`/Volume1/@apps/qbittorrent`、`/Volume1/@apps/transmission`、`/Volume1/@apps/xunleipan`
- 第三方 TOS 7 deb 应用参考：`Moechz/kavita`、`Moechz/sftpgo`、`Moechz/audiobookshelf`