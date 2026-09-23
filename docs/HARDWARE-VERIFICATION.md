# 真机实测记录（TOS 7 @ 10.18.8.214）

**结论：路径 B 技术可行，已在真机上跑通。**

## 测试机环境

| 项 | 值 |
|---|---|
| TOS | TeraMaster Tnas（Ubuntu 22.04 基座） |
| 内核 | `6.12.63+` x86_64 |
| glibc | 2.35 |
| systemd | 249 |
| Python | 3.10.12 |
| dpkg | 1.21.1（`dpkg-deb` 可用） |
| 内存 / CPU | 15.7 GB / 4 核 |

## 关键发现一：TOS 自己的迅雷就是同一套引擎

`/Volume1/@apps/xunleipan/`（`application_type: "tpk"`，非 deb）里：

- `bin/xunlei-pan-cli.2.9.1.amd64` + `bin/xunlei-pan-cli-launcher.amd64`
- `init.d/service` 用 **`PLATFORM=terramaster`**、`NasId=terramaster`、
  `DriveListen=0.0.0.0:21063` 启动
- `nginx/xunleipan.conf`：`location /xunleipan/ { proxy_pass http://127.0.0.1:21063/; }`
- `config.ini`：`"type": "iframe"`、`"path": "/xunleipan/"`、`category: ["Download"]`、`depend: ["PHP74"]`
- 共享文件夹由 TOS 专有工具 `ter_share_add -name "XunLei"` 创建，
  **WebUI 由迅雷引擎自己在 TCP 端口上提供，nginx 反代 + iframe 打开**

→ 所以 **不需要任何 CGI 垫片**，也不需要群晖模拟层。之前设想的
`index.cgi` + `authenticate.cgi` 方案完全用不上。

`info.file` 内容：
```json
{"arch":"amd64","client_version":"2.9.1","device_id":"...",
 "package_name":"pan.xunlei.cli.terramaster","platform":"terramaster"}
```
`package_name` 是 **`pan.xunlei.cli.terramaster`** —— 迅雷有铁威马专用包。

## 关键发现二：更新通道把 terramaster 排除在外

2.9.1 启动器自带更新地址：
`https://2rvk4e3gkdnl7u1kl0k.xbase.cloud/v1/file/pancli/versions.info.amd64`

该文件里：
- 最新版本 `version: "3.23.7"`，`accept` 列表含 `2.9.1` → **2.9.1 本可直接升到 3.23.7**
- 但 filter 是 `match: ["platform","in","synology","linux"]`

**`terramaster` 不在名单里，所以 TOS 永远收不到升级提示。** 这解释了
"TOS 卡在 2.9.1" 的根因——不是打包问题，是迅雷侧的灰度策略。

同页还有官方直链（无需群晖 SPK，`linux` 平台，41 MB 是过时的元数据，实测 62.8 MB）：
```
https://2rvk4e3gkdnl7u1kl0k.xbase.cloud/v1/file/pancli/amd64/xunlei-pan-cli.3.23.7.amd64
sha256 09122229f63047b39159f529799f4ba9a4055b4c0351536febe581af1891ea2e
```

## 关键发现三：3.23.7 + PLATFORM=terramaster 实测跑通

隔离目录 `/Volume1/xunlei-353-test/`，用 TOS 自己的环境变量约定启动 3.23.7：

```sh
PLATFORM=terramaster NasId=terramaster \
ConfigPath=... DownloadPATH=... HOME=.../.drive \
DriveListen=0.0.0.0:21064 DrivePublicPort=21604 drive_loglevel=info \
./xunlei-pan-cli-launcher.amd64 \
  -logfile ... -launcher_listen=unix://.../pan-cli-launcher.sock -update_url ""
```

结果：
- 启动器打印 `Platform:terramaster`，**接受了这个平台值**（`AllowCustomPlatform:false` 也没拦）
- 自动把引擎复制到 `<ConfigPath>/.drive/bin/xunlei-pan-cli.3.23.7.amd64` 并拉起
- `curl http://127.0.0.1:21064/` → **HTTP 200，返回迅雷官方 WebUI HTML**
- 引擎从云端拉到配置，`platforms` 里 **`terramaster` 是一等条目**：

```json
"terramaster": {
  "contact": "NAS迅雷铁威马用户QQ群：744615778 | 常见问题",
  "login_message": { "title": "迅雷App扫码登录",
    "messages": ["1. 该版本为铁威马用户专享", ...] },
  "upload_strategy": "downloading"
}
```

→ 用 3.23.7 引擎 + `PLATFORM=terramaster` 得到的**就是铁威马专享的官方界面**，
和迅雷的预期完全一致。同时它也知道 `fnos` / `fnos_community` / `ugreen` / `zspace` /
`hiksemi` / `qnap` / `synology` 等 20 个平台。

## 两条并行的建议

1. **立刻可做（本仓库）**：用官方 `linux` 引擎 3.23.7 + `PLATFORM=terramaster`
   打一个 TOS deb，完全复刻 `xunleipan` 的启动方式（nginx 反代 + `type: iframe`）。
2. **同时推进（成本更低）**：请迅雷把 `terramaster` 加进 `versions.info.amd64`
   的 filter —— 那么所有已装 2.9.1 的 TOS 机器会自动升到 3.23.7，**零打包工作量**。
   这条比重新打包更值钱，且顺带解决长期维护。

## 清理说明

测试实例（pid 1491479/1491490）已 kill。`/Volume1/xunlei-353-test/` 仍保留，
用于下一步验证 deb 的真实布局；不再需要时可直接 `rm -rf`。

---

# 第二阶段：成品 deb 真机验证（1.0.0）

## 安装与运行

| 检查项 | 结果 |
|---|---|
| `useradd -r -M -s /usr/sbin/nologin le3gold-xunlei`（平台本应自己做）+ `dpkg -i` | 无报错 |
| `systemctl is-enabled` / `is-active` | `enabled` / `active` |
| 服务进程身份 | `le3gold-xunlei`（uid 997，**非 root**） |
| 引擎监听 | `18889`（WebUI）、`18890` |
| `curl http://127.0.0.1:18889/` | 200，SPA 标题「迅雷下载」 |
| `/le3gold-xunlei/app/`（经平台 nginx，8181） | 200 |
| `/le3gold-xunlei/app/assets/index-fecd76c5.js` | 200，1,527,665 字节 |
| `POST /le3gold-xunlei/app/device/info/watch` | **403 + JSON 鉴权错误**（证明请求打到了迅雷 API，而不是 404） |
| `nginx -t` | OK |
| 引擎日志中的平台标记 | 「铁威马专享」9 次、`terramaster` 43 次 |
| 覆盖安装（再 `dpkg -i` 一次） | 正常，修复逻辑幂等 |

`/le3gold-xunlei/`（iframe 加载页）在手动安装下返回 404 —— 因为该实例没有在
TOS 的 `config.ini` 注册，平台不会把 `webui.bz2` 挂到该路径下。真实应用中心安装
注册后由平台提供。

## 发现四：/etc/os-release 被旧版迅雷破坏（导致引擎 panic）

3.23.7 引擎在识别平台时会读 `/etc/os-release`，失败即 `panic: platform not suport`。

旧版迅雷应用（`xunleipan 2.9.1`）把 `/etc/os-release` 换成指向
`/Volume1/@apps/xunleipan/nginx/os-release` 的符号链接（该文件对普通用户不可读），
停止服务时还会直接 `unlink` 它。旧版迅雷以 uid 0 运行，所以从未暴露这个问题。

验证方式：

- 以 root 运行引擎 → 正常；
- 以应用用户运行引擎 → panic；
- 把符号链接换成普通 `0644` 文件 → 正常。

`bind --bind` 挂载、SMACK 之类的绕过都无效（该文件受 TOS 访问控制保护）。
本包在 `postinst` 里做幂等修复（仅在缺失/不可读时动作），见 README。

> 这同时是一个**平台侧问题**：旧版迅雷退出后 `/etc/os-release` 处于损坏状态，
> 会影响所有以非 root 运行、且需要读该文件的应用。

## 发现五：/Volume1 的 Rich ACL 对非 root 用户全线拒绝

`/Volume1` 以 `tmacl` 选项挂载（btrfs），由内核模块 `tmacl_vfs`
（`/lib/modules/6.12.63+/kernel/fs/tmacl_vfs.ko.xz`，"TerraMaster Rich ACL Support"）
执行 ACL。规则存在 `system.tm_acl` xattr 中，用 `tmacltool` 管理。

在测试机上实测：

| 试验 | 结果 |
|---|---|
| 非 root 用户写 `/Volume1/<share>/`（目录属主就是自己、权限 rwx） | `EACCES` |
| 非 root 用户写 `/Volume1/@zlog`（777） | `EACCES` |
| 给该用户 `tmacltool modify ... user:<user>:allow:rwxpdDaARWc:fd` 后再写 | 仍 `EACCES` |
| `tmacltool get-perm <path> <uid>` | `max_permission: rwxpdDaARWc--`（**工具认为已授权**） |
| TOS 自带应用运行用户（`qbittorrent`、`transmission`、`webserver`、`PHP80`）按同样方式测试 | 全部 `EACCES` |
| root 写同一目录 | OK |

即：**该机上任何非 root 用户都写不进 `/Volume1`，与 ACL 是否授权无关**。
TOS 自带 qBittorrent 的目录（`/Volume1/qBittorrent/qBittorrent/config`）是 9 月 20 日
由该应用用户创建的，说明这条路径**曾经可用**；`/Volume1/*` 下共享目录的
`#recycle` 时间为 9 月 22 日 12:07，疑似与一次共享/ACL 迁移有关。

因此本包采取的策略是：

1. 严格按指南 10.6 与一方应用的方式授权（`ter_share_add -owner` + `tmacltool modify`）；
2. 启动时**实测**共享目录可写性，不可写则回退到 `/var/lib/le3gold-xunlei/download`
   并输出明确告警，保证下载功能不因此整体失效。

> **更正（同日稍后查明，见发现七）**：本节结论「与 ACL 是否授权无关」不准确。
> `tmacltool get-perm` 报已授权是针对**文件夹**的；真正缺的是**卷根 `/Volume1`** 上的
> 条目 —— tmacl 不回落到 POSIX mode 位，非 root 用户连穿越都做不到，文件夹上的条目
> 因而永远没被检查到。在卷根补一条 `r-x` 后，本节列出的所有 `EACCES` 全部消失。
> 准确说法是：**与文件夹上的授权无关，缺的是卷根上的授权。**

> 建议内部跟进：`ter_share_add -owner` 只写文件夹自身的 ACE、不写卷根，会让按指南
> 10.6 写的应用全部不可用。详见 `docs/PLATFORM-DEFECT.md`。

## 清理状态

- 生产环境的迅雷 2.9.1 未被改动（仍占 21063/21603）。
- `/etc/os-release` 目前是 `0644` 普通文件（本包修复的结果）。
- 临时探针 `/tmp/tr-root`、`/tmp/xl-*`、`/tmp/le3gold-xunlei_x86_64.deb` 已删除。
- 早期测试实例目录 `/Volume1/xunlei-353-test/` 仍在，确认无用后可 `rm -rf`。

## 发现六：平台把应用放到存储卷后，非 root 服务无法读取自身（200/CHDIR）

用户从应用中心安装后页面报 **502 Bad Gateway**。定位过程：

| 检查 | 结果 |
|---|---|
| `systemctl status le3gold-xunlei` | `activating (auto-restart)`，`status=200/CHDIR` |
| `dpkg -L` / `/usr/local/le3gold-xunlei` | 已是**符号链接** → `/Volume1/@apps/le3gold-xunlei`（平台按指南 10.7 迁移） |
| `su -s /bin/bash le3gold-xunlei -c "cd /usr/local/le3gold-xunlei"` | **Permission denied** |
| 逐层定位 | `/Volume1` 可穿越；**`/Volume1/@apps` 起被拒** |
| `ls -ld /Volume1/@apps` | `drwxr-xr-x+ test test`（权限位 755，POSIX 允许） |
| `tmacltool get /Volume1/@apps` | **无任何条目** |
| 给应用用户 `tmacltool modify /Volume1/@apps user:...:allow:r-x---a-R-c--:fd--` 后再试 | `tmacltool get-perm` 显示 `r-x---a-R-c--`，但内核**仍然 `EACCES`** |
| 对一方应用做同样检查（`qbittorrent` 用户访问自己的 `/Volume1/@apps/qbittorrent`） | **同样 Permission denied** |

即：在这台 TOS 7 上，**任何非 root 用户都无法穿越 `/Volume1/@apps`**，
tmacl 的授权调用不生效。而第三方 deb 应用的文件按设计就在
`/Volume1/@apps/<appid>/`，因此任何以非 root 运行的应用都起不来：
systemd 连 `WorkingDirectory` 都设不进去 → `200/CHDIR` → nginx 502。

### 解决办法（已实装）

不依赖平台修 ACL，让服务**不需要读 `/Volume1`**：

- `postinst` 把入口脚本、启动器、引擎复制到 `/var/lib/le3gold-xunlei/runtime/`
  （系统盘 `/`，ext4，无 `tmacl`），属主为应用用户；每次安装/升级刷新。
- systemd 单元改为 `ExecStart=/var/lib/le3gold-xunlei/runtime/le3gold-xunlei`、
  `WorkingDirectory=/var/lib/le3gold-xunlei`。
- 入口脚本用 `readlink -f "$0"` 自定位，不再假定 `/usr/local/<appid>` 可读。
- 引擎写在工作目录下的状态文件（`CidStore.DB` / `seq_id` / `setting.cfg`）
  因此落在应用状态目录，而不是可执行文件旁边（升级时不会被动到权限）。

修复后实测：服务 `active`，18889/18890 在听，`curl 127.0.0.1:18889/` → 200，
经平台 nginx（8181）`/le3gold-xunlei/app/` → 200、`/le3gold-xunlei/` → 200。

> 建议内部跟进：`/Volume1/@apps` 对非 root 用户不可访问且 ACL 授权无效，
> 这与"第三方应用必须非 root 运行 + 文件放在存储卷"的设计直接冲突，
> 会影响所有第三方 deb 应用。修复方式可以是平台在注册应用时授予 ACL，
> 或让该 ACL 授权真正生效。

## 发现七：卷根没有 ACE 才是真正的根因 —— 补一条穿越权限即完全修复

### 调查过程

1. `ps -eo user,uid,pid,args` 加 `/proc/<pid>/status` 逐个核对：TOS 自带的 PHP74、
   OnlyOffice、TerraSync、DockerEngine、VMs、openclaw、terai … 共 30 个应用
   **全部是 uid 0**；`/etc/systemd/system/PHP74.service` 里写的就是 `User=0`。
   `ps -eo uid | sort | uniq -c` 中 uid >= 1000 的进程数：**0**（唯一的非 root 应用
   进程，是我们自己那对 uid 997 的引擎进程）。→ 平台自己也从不以非 root 运行。
2. `grep Volume1 /proc/mounts` -> `btrfs rw,noatime,tmacl,...`；
   `/sys/kernel/security/lsm` -> `lockdown,capability,landlock,yama,bpf,ipe,ima,evm`，
   **没有 SMACK**。标签路线（`security.SMACK64`）能写但无效，印证了这不是标签问题。
3. `ls -ld /Volume1` -> `drwxr-xr-x+`（755，others 本应可穿越）；
   `tmacltool get /Volume1` -> **空**（`/Volume10` 同样为空）；
   `tmacltool get-perm /Volume1 997` -> `max_permission: -------------`。
   → tmacl **默认拒绝**，且**不回落**到 `other` 位。
4. 用 `setpriv --reuid=<uid> --regid=<uid> --clear-groups ls /Volume1` 逐个验证：
   uid 997（本应用）、10003（qbittorrent）、10001（PHP80）、1001（guest）**全部**
   `Permission denied`；uid 0 正常。再用 `su -s /bin/sh le3gold-xunlei -c ...`（带真实
   附加组，包含 `allusers`）复核，结果相同 —— 排除「组没带对」。
5. 隔离实验：先 `tmacltool clear /Volume1` 还原成空（实验前本来就是空），确认故障重现；
   再 `ter_share_add -name XunLeiTest2 -owner le3gold-xunlei` 新建一个共享目录，对比
   `/Volume1` 与 `/Volume1/XunLeiTest2` 的 ACL —— **新目录有 ACE，卷根依旧为空**，
   应用用户仍然 `Permission denied`。→ `ter_share_add -owner` 不会补卷根。

### 修复验证

```sh
tmacltool modify /Volume1 "user:le3gold-xunlei:allow:r-x:--"
```

| 检查 | 结果 |
|---|---|
| `ls /Volume1`（以应用用户） | OK |
| `touch /Volume1/XunLeiPlus/x` | OK |
| `mkdir -p /Volume1/XunLeiPlus/download` 并写入 | OK |
| 引擎日志 `download_paths` | `["/Volume1/XunLeiPlus/download/"]` |
| 引擎 fsnotify | 探针文件一落盘即被引擎监听到，说明引擎确实在盯该目录 |

`r-x` 是穿越所需的最小权限，**不带继承标志**（显示为 `r-x----------:----`），不会向卷内
其它目录扩散；读写权限仍由文件夹本体的条目决定。

### 实装方式

- `assets/postinst` 步骤 3a：解析出承载共享文件夹的卷，为**本应用自己的用户**补 `r-x`。
- `assets/postrm`：卸载时 `tmacltool del` 掉该条目，避免留下悬空 uid。
- `assets/bin/app.in`：删掉原先那两句**无效**的 `tmacltool modify`（以应用用户身份运行
  本来就改不动 ACL），保留可写性实测与告警。
- `tools/verify_deb.py`：新增 3 条断言（postinst 必须补卷根穿越、入口脚本不得假装改
  ACL、postrm 必须删除该条目）。断言总数 228 -> 230。

### 验证流程（可重复）

1. 删掉卷根条目 -> 故障复现（以应用用户 `touch` 被拒）。
2. `dpkg -i out/le3gold-xunlei_1.0.0_amd64.deb`。
3. 卷根条目被 postinst 自动补回；应用用户可穿越，并可写 `XunLeiPlus/download`。
4. 服务 `active` + `enabled`；18889 -> 200；平台 nginx `/le3gold-xunlei/app/` -> 200。

清理：探针目录 `/Volume1/XunLeiTest`、`/Volume1/XunLeiTest2` 已删除；`/Volume10` 上的
实验 ACE 已 `clear` 干净。
