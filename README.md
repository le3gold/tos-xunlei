# tos-xunlei — 迅雷 for TOS 7 应用中心

**状态：调研完成，等待方向决策。尚未开始打包，仓库内不含任何迅雷二进制。**

## 一句话结论

技术上有明确可行的路径，但**迅雷没有官方 deb**——公开可下载的只有面向群晖的 SPK。
把其中的迅雷引擎重新封装成 TOS deb 在工程上完全做得到（引擎是标准 Linux ELF，
不需要 root），但**会踩到 TOS 7 上架审核的 V6 红线**：包内二进制必须有公开可审计的来源。
所以本项目应按"厂商渠道应用"定位，而不是"第三方提审应用"。

## 已实测的事实

| 项 | 结果 |
|---|---|
| 迅雷官方 NAS 页面 | `http://nas.xunlei.com/`，合作伙伴列表里**已经包含 TerraMaster** |
| 官方 CDN | `https://down.sandai.net/nas/` |
| 页面 JS 里仅有的两个包 | `nasxunlei-DSM6-x86_64.spk`、`nasxunlei-DSM7-x86_64.spk` |
| 猜测过的 deb 路径 | `nas/xunlei_x86_64.deb`、`nas/nasxunlei-TOS-x86_64.deb`、`nas/nasxunlei-TerraMaster-x86_64.deb` 等**全部不存在** |
| DSM7 SPK 大小 / 校验 | 27,084,800 字节 |
| 引擎版本 | `bin/bin/version` = **3.23.5**，`version_code` = 3023005 |
| SPK `INFO` 版本 | `3.23.5-0814080017` |

### 载荷（SPK 内 `package.tgz`）结构

```
bin/bin/version                          # 3.23.5
bin/bin/version_code                     # 3023005
bin/bin/xunlei-pan-cli-launcher.amd64    19.7 MB  启动器
bin/bin/xunlei-pan-cli.3.23.5.amd64      62.8 MB  下载引擎
bin/xunlei-pan-cli.sh                    # 3 行壳脚本
ui/index.cgi                             17.5 MB  官方 WebUI（Go，CGI 程序）
ui/Main.js ui/layout.html ui/style.css   # WebUI 静态资源
ui/images/* ui/texts/{chs,enu}/*
```

### 关键结论：引擎可以非 root 运行

用自写的 ELF 解析器读了动态段：

| 二进制 | 架构 | NEEDED | glibc 要求 |
|---|---|---|---|
| `xunlei-pan-cli-launcher.amd64` | x86-64 | `libpthread`, `libc` | ≥ 2.3 |
| `xunlei-pan-cli.3.23.5.amd64` | x86-64 | `libm`, `libdl`, `libstdc++`, `libpthread`, `libgcc_s`, `libc` | ≥ 2.17 |
| `ui/index.cgi` | x86-64 | `libpthread`, `libc` | ≥ 2.3 |

- **没有任何群晖专有 `.so` 依赖**，只有标准 glibc/libstdc++。TOS 7 是 glibc 2.35，满足。
- SPK 的 `conf/privilege` 声明 `run-as: package`，即**在群晖上本来就是以非 root 的
  `sc-pan-xunlei-com` 用户运行**。
- `scripts/service-setup` 里那句注释 `I need root to bind to port 53` 是
  **dnscrypt 模板的残留文本**（该 SPK 源自 `jedisct1/pan-xunlei-com` 的 dnscrypt
  服务模板，`ui/index.conf` 的 keywords 还留着 dns/dnscrypt/doh/proxy）。
  实际的 `service_prestart()` 里没有任何 53 端口操作。二进制里的 `[::1]:53` 只是
  DNS 解析器默认值和内嵌的指纹库字符串。

结论：**TOS 侧不需要 root，不需要特权端口，符合指引第 10 章"禁止 User=root"。**

## 启动方式（来自 SPK 的 `service-setup`）

```
DriveListen=unix://<pkgdest>/var/pan-xunlei-com.sock
PLATFORM=群晖
OS_VERSION="<platform> dsm <ver>"
ConfigPath=<共享文件夹>
DownloadPATH=<共享文件夹>/下载/
HOME=<共享文件夹>/.drive
bin/xunlei-pan-cli.sh -launcher_listen=unix://<pkgdest>/var/pan-xunlei-com-launcher.sock \
                      --pid <pkgdest>/var/pan-xunlei-com.pid --logfile <pkgdest>/var/xxx.log
```

即：**引擎全部通过 Unix socket 通信**，不需要监听任何 TCP 端口。

## WebUI 怎么接进 TOS iframe 模式

官方 `ui/index.cgi` 是个 **CGI 程序**，靠 `REQUEST_METHOD` / `QUERY_STRING` 等
环境变量工作，认证上依赖群晖的 `/usr/syno/synoman/webman/modules/authenticate.cgi`
和 `/webman/login.cgi`。

业界已有成熟先例 `cnk3x/xunlei`（★2041，MIT）证明了怎么在非群晖 Linux 上跑它：
用 Go 的 `net/http/cgi` 把 `index.cgi` 挂到自己的 HTTP 服务器上，并 mock 掉群晖环境：

- `mockEnv()`：注入 `SYNOPLATFORM` / `SYNOPKG_PKGDEST` / `SYNOPKG_DSM_VERSION_*` /
  `PLATFORM=群晖` / `OS_VERSION` / `ConfigPath` / `HOME` / `DownloadPATH`
- `mockSyno()`：写一份假的 `/etc/synoinfo.conf`，并把 `authenticate.cgi` 换成一个
  只输出 `admin` 的桩程序
- `/webman/login.cgi` 返回假 `{"SynoToken":"...","result":"success","success":true}`
- 路由 `/webman/3rdparty/pan-xunlei-com/index.cgi/` → CGI handler

**映射到 TOS iframe 模式**（指引 8.3.1）：把上面那台 Go HTTP 服务器换成
**Python 3.10 标准库写的 CGI 宿主**（TOS 7 预装 Python 3.10，deb 不允许依赖
Node/Java/Go/PHP，用 Python 可以零额外依赖），让它监听指引要求的
`/var/api/<app_id>.sock`（mode 0660）即可。

这样 WebUI 就是**迅雷官方界面**，不是第三方重写的面板。

## 风险与待解问题

1. **V6 审核红线（最大阻塞）**：包内二进制必须公开可审计来源。迅雷引擎是闭源
   商业软件，从迅雷 CDN 下载——第三方提审必然被拒。
2. **再分发授权**：迅雷引擎版权属于迅雷。TerraMaster 是官方合作伙伴，有既有渠道，
   但没有授权就不能公开再分发。
3. **群晖模拟很脆弱**：`/etc/synoinfo.conf`、`authenticate.cgi`、`login.cgi`、
   `PLATFORM=群晖` 都是模拟出来的。TOS 侧要额外维护这层模拟；一旦迅雷换版本
   可能失效。而 TOS 的 `/etc` 是禁止写入的（指引第 10 章），只能在应用私有目录里
   构造等价路径，需要真机验证引擎是否真的读这些路径。
4. **无法在本机构建验证**：本机没有 Linux 环境（无 dpkg-deb / Docker / WSL），
   只能做静态分析与打包，**必须在 TOS 真机上做安装与运行验证**。
5. **数据目录**：`ConfigPath` 与 `DownloadPATH` 需要落到用户可见的共享文件夹
   （`config.ini` 的 `share_folders`），保证 SMB/NFS 能取到下载内容；`.drive`
   里存的是登录态与下载进度，卸载脚本**绝不能删**。

## 两条路

**A. 厂商渠道（推荐）**
通过迅雷 NAS 合作渠道索取面向 TOS 的原生构建（或由 TerraMaster 以厂商身份在应用
中心更新现有迅雷应用到 3.23.5）。优点：无 V6 问题、无群晖模拟层、可长期维护。
公开渠道只有群晖 SPK，说明即便是飞牛的版本很可能也是社区重打包——
详见 `xm0625/docker-xunlei-arm-fpk`（"飞牛arm版迅雷-docker版"）。

**B. 内部技术验证包**
按上面设计封装一个 deb，**仅用于内网验证/给迅雷方做对接素材**，不进应用中心提审。
技术上完全可行，本文档已给出全部要点。

## 参考

- 迅雷 NAS 官方页：http://nas.xunlei.com/
- `cnk3x/xunlei`（MIT）：非群晖 Linux 上运行迅雷套件的成熟实现，含群晖环境模拟
- `Moechz/kavita`、`Moechz/sftpgo`、`Moechz/audiobookshelf`：真实 TOS 7 第三方
  deb 应用，最佳实践参考（`build.sh` / `makedeb.sh` / `assets/`）
- `RyanYang163/tos7-app-*`：**故意违规的审核测试语料**（20 个应用覆盖 54 条审核
  条目 A1–I10），可用于反查审核红线，**不要当作正面样例**