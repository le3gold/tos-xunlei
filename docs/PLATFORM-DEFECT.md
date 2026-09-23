# TOS 7 平台缺陷（1）：非 root 应用无法访问共享文件夹

> 状态：已在真机复现，等待平台修复
> 环境：TOS 7 / 内核 6.12.63+ / x86_64 TNAS
> 复现日期：2026-09-23
> 发现场景：迅雷应用封装（`le3gold-xunlei`）

## 1. 结论

按《TOS 7 Application Development Guide》第 10 章把 deb 应用做成**专用非 root
用户**运行（10.3、10.9）、数据放在 **`/Volume*/`** 数据盘（10.4、10.7）、用
**`ter_share_add -owner`** 申请共享文件夹（10.6、附录 G）之后，应用**仍然无法读写
自己的共享文件夹** —— 实际上无法访问 `/Volume*` 下的**任何**路径，包括它自己的
`/Volume*/@apps/<appid>/data`。

原因不在应用，而在平台：**tmacl 富 ACL 默认拒绝，且不回落到 POSIX mode 位；而全机
所有卷根都没有任何 ACL 条目。** 穿越一个路径需要在**每一层**都有权限，卷根这一层
就把所有非 root 用户拦死了。

同一台机器上，TOS 自带的 30 个应用（PHP74、OnlyOffice、TerraSync、DockerEngine、
openclaw、terai …）**全部以 root 运行**（`PHP74.service` 里写的就是 `User=0`），
所以从未暴露这个问题。换句话说：**当前 TOS 7 上，一个严格遵守 10.3 / 10.9 的第三方
应用，无法按 10.4 / 10.6 / 10.7 存取数据盘。**

## 2. 复现（3 条命令）

```sh
# 1) 用官方做法给应用用户授权共享文件夹
ter_share_add -name XunLeiPlus -owner le3gold-xunlei
#    -> /Volume1/XunLeiPlus          返回路径，即成功

# 2) 文件夹上的 ACL 看起来完全正确
tmacltool get /Volume1/XunLeiPlus
#    [0] user:le3gold-xunlei:allow:rwxpdDaARWc--:fd--

# 3) 以该用户访问 -> 失败
su -s /bin/sh le3gold-xunlei -c 'touch /Volume1/XunLeiPlus/x'
#    touch: cannot touch '/Volume1/XunLeiPlus/x': Permission denied
```

## 3. 取证

| 观测项 | 命令 | 结果 |
|---|---|---|
| 卷根 DAC 权限 | `ls -ld /Volume1` | `drwxr-xr-x+ test test` — 755，others 本应可穿越 |
| 卷根 ACL | `tmacltool get /Volume1` | **空**（`/Volume10` 同样为空） |
| 卷根对应用用户的有效权限 | `tmacltool get-perm /Volume1 997` | `max_permission: -------------` |
| 共享文件夹 ACL | `tmacltool get /Volume1/XunLeiPlus` | `user:le3gold-xunlei:allow:rwxpdDaARWc--:fd--` 正确 |
| 是否只是我们的应用有问题 | 以内置 `qbittorrent` 用户 `ls /Volume1` | `Permission denied` |
| 是否只是应用用户被拒 | `setpriv --reuid=1001 --regid=1001 --clear-groups ls /Volume1` | `Permission denied`（普通 TOS 用户同样被拒） |
| 挂载参数 | `grep Volume1 /proc/mounts` | `btrfs rw,noatime,tmacl,...` |
| 是否 LSM 标签问题 | `cat /sys/kernel/security/lsm` | `lockdown,capability,landlock,yama,bpf,ipe,ima,evm` — 无 SMACK |
| 加入 `admin` 组能否绕过 | `usermod -aG admin <app>` | 仍是 `Permission denied` |
| 在文件夹上重复授权能否绕过 | `tmacltool modify <share> user:<app>:allow:rwxpdDaARWc:fd` | 仍是 `Permission denied`（父层未授权） |
| 在 `/Volume1/@apps` 上授权 | 同上 | 仍不可穿越（`/Volume1` 这一层仍无权限） |

补充说明：`le3gold-xunlei.service` 的 `ReadWritePaths` 也放开了 `/Volume1/XunLeiPlus`，
systemd 侧不是瓶颈；把入口程序与其依赖复制到系统盘的副本、绕开「读自己的安装目录」
之后，服务本身能正常启动（`active` + `enabled`、端口 200），**只有访问数据盘这一件事
做不到**。

## 4. 最小修复验证

只在**卷根**补一条仅穿越的条目：

```sh
tmacltool modify /Volume1 "user:le3gold-xunlei:allow:r-x:--"
```

随即全部通过：

| 检查 | 结果 |
|---|---|
| `ls /Volume1` | OK |
| `touch /Volume1/XunLeiPlus/x` | OK |
| `mkdir -p /Volume1/XunLeiPlus/download` + 写入 | OK |
| 迅雷引擎上报的下载路径 | `download_paths: ["/Volume1/XunLeiPlus/download/"]` |
| SMB 可见性 | 是（下载文件直接出现在共享文件夹里） |

`r-x` 是穿越所需的最小权限，**不带继承标志**，因此不会向卷内其它目录扩散；读写权限
仍然由文件夹本体的条目决定。

## 5. 建议的平台修复（任一即可）

1. **首选：让 `ter_share_add -owner` 顺带授权卷根。** 在建立共享文件夹、写入文件夹
   自身 ACE 的同时，为 `<appid>` 在承载卷的卷根补一条不继承的 `r-x`。改一个函数，
   就能让所有按 10.6 写的第三方应用立刻可用。
2. **安装应用时预置卷根穿越权限。** 平台创建 `/Volume*/@apps/<appid>` 与 `allusers`
   成员关系时，一并给 `<appid>` 在卷根补 `r-x`。
3. **让 tmacl 在无匹配条目时回落到 POSIX mode 位。** 语义与 Linux 惯例一致；影响面
   最大，建议只对「完全没有任何 ACE」的目录启用。

顺带一条**文档**修正：10.6 里建议的 `usermod -aG allusers <appid>` 目前无效 ——
`allusers` 组的成员在卷根同样没有 ACL 条目。

## 6. 本包的临时绕过（平台修复后应删除）

- `assets/postinst` 步骤 **3a**：在承载共享文件夹的那个卷的卷根上，为**本应用自己的
  用户**补一条 `user:<appid>:allow:r-x:--`。
- `assets/postrm`：卸载时删除这条条目（避免给平台删掉用户后留下悬空 uid）。
- 没有违反 10.6 的「不要直接改共享文件夹权限」：改的是**卷根**，不是文件夹；只授
  **穿越**、只授**自己**。
- `assets/bin/app.in` 不再尝试改 ACL（它以应用用户身份运行，本来就改不动），改为实测
  下载目录可写性，缺失时才回退到 `/var/lib/<appid>/download` 并**明确告警**。

平台修好后，删掉 `postinst` 的 3a 段与 `postrm` 的对应段即可，其余代码无需改动。
`tools/verify_deb.py` 现有两条断言绑定这两段（"postinst must grant the application
user traversal of the volume root" 与 "postrm must remove the volume-root traversal
entry"），届时一并删除。

## 7. 现状统计

| 项 | 数量 |
|---|---|
| 全机应用数 | 30 |
| 以 root 运行的 | 30 |
| 以非 root 运行的 | 0（本应用除外） |
| `/etc/systemd/system` 里显式声明 `User=` 的应用单元 | 1 个：`PHP74.service` -> `User=0` |
| 带 ACL 条目的卷根 | **0** |
---

# TOS 7 平台缺陷（2）：iframe 应用窗口的关闭按钮在深色主题下不可见

> 状态：已在真机复现并取证，等待平台修复
> 环境：TOS 7 / 内核 6.12.63+ / x86_64 TNAS
> 复现日期：2026-09-23
> 发现场景：迅雷应用封装（`le3gold-xunlei`）

## 1. 现象

`type: "iframe"` 的应用，窗口右上角的关闭按钮 `×` 在浅色主题下正常，切到**深色主题**
后默认完全看不见，只有鼠标浮上去、按钮底色转红时才出现。同一排的最小化 `−`、最大化
`□`、帮助 `?` 三个按钮没有这个问题。

## 2. 原因

TOS 7 不为 iframe 应用画标题栏，而是在窗口顶部**覆盖**一条 40px 的
`.tos-dialog-menu.micro`，四个按钮共用一条样式：

```css
.tos-dialog-menu > [class^=tos-button-] {
  color: var(--common-font-level3);
  background-repeat: no-repeat; background-position: 50%;
}
```

其中最小化、最大化、帮助各自带一张 `background-image`（`button_minimize.svg` /
`button_maximize.svg` / `button_help.svg`），颜色是**写死的** `#7C7C7C` 灰，与主题无关，
压在任何底色上都看得见。

**关闭按钮没有任何 `background-image`**，它用的是字体图标：

```html
<div class="tos-button-close"><i class="iconfont iconReject"></i></div>
```

于是它的颜色完全由 `--common-font-level3` 决定，而 TOS 给它定义了两个值：

| 主题 | 定义位置 | `--common-font-level3` |
|---|---|---|
| 浅色 | `:root` | `rgba(0,0,0,0.45)` —— 深灰，压在白底上可见 |
| 深色 | `html[data-theme=dark]` | `hsla(0,0%,100%,0.45)` —— **白 45%** |

深色的 `白 45%` 是给深色标题栏准备的，而这条 40px 覆盖条**自己没有背景色**：那一格
显示什么，取决于应用页面画了什么。迅雷的 SPA（以及 TOS 上大多数第三方 Web 应用）是
浅色的，于是 `白 45%` 的 `×` 压在白色标题栏上 = 不可见。浮上去时平台把底色涂成
`--common-error-color`（`#ff383c`）并把图标强制成 `#f7f8fa`，这才显形。

平台其实**自带**正确的资源：`/usr/www/tos/img/button_close.525215ef.svg`
（`fill="#7C7C7C"`，与另外三个按钮同色），在 `device-memory`、`device-lan`、`device-temperature`
等组件里都在用 —— **只有窗口标题栏的关闭按钮没接上**。

## 3. 取证

| 观察项 | 依据 | 结果 |
|---|---|---|
| 关闭按钮的样式 | `grep -o 'tos-dialog-menu .tos-button-close[^}]*}' /usr/www/tos/css/*.css` | 只有 `position` / `border-radius` / `:hover`，**无 `background-image`** |
| 另外三个按钮 | 同上 | 都有 `background-image:url(../img/button_*)` |
| 关闭按钮的标记 | `chunk-*.js` | `e("i",{staticClass:"iconfont iconReject"})` |
| 两个主题的取值 | `chunk-tos-components.*.css` | `:root` -> `rgba(0,0,0,.45)`；`html[data-theme=dark]` -> `hsla(0,0%,100%,.45)` |
| 平台自带的关闭图标 | `cat img/button_close*.svg` | `fill="#7C7C7C"`，存在但标题栏未引用 |
| iframe 是否被沙箱隔离 | `chunk-2a09363a*.js` | **无 `sandbox` 属性**，`src = window.origin + path` => 与桌面**同源** |

## 4. 建议的平台修复（任一即可）

1. **首选：给关闭按钮也接上 `background-image`。** 资源已在包里
   （`img/button_close.svg`），一条选择器即可，四个按钮从此都与主题无关。
2. **或者：把关闭按钮的颜色从 `--common-font-level3` 换成
   `--common-iconfont-ActiveColor`**（浅色 `#7c7c7c` / 深色 `#d4d1cd`），并保证它在
   两个主题下对浅底、深底都可读。
3. **或者：给 `.tos-dialog-menu.micro` 一个自己的背景色。** 现在「看不看得见」这件事
   取决于应用页面在那一格里画了什么 —— 对第三方应用来说不可控。

## 5. 本包的绕过（平台修复后可删）

`build.py` 的 `LOADER`：入口页自己画的那条 41px 标题栏**跟随桌面主题取色**，不再是
写死的白底深字。

- 父文档同源且无 `sandbox`，直接读它的 `data-theme`，并取
  `--main-bg-color` / `--dialog-title-color` / `--common-line-level1` 的**计算值**套到
  标题栏上：深色主题下标题栏就是平台自己的 `#0f1112`，`白 45%` 的 `×` 自然可见。
- `MutationObserver` 监听父文档的 `data-theme`，窗口开着时切换主题也跟着变。
- 万一父文档读不到（换域名、将来加了沙箱），回落到 `prefers-color-scheme` 加平台公布的
  两套取值，不会退化成「白底白叉」。
- 只**读**父文档，不改它的任何 DOM/CSS。

平台修好第 1 或第 2 条之后，这段 JS 可以删掉，标题栏改回纯 CSS 即可。
`tools/verify_deb.py` 现有 5 条断言绑定这段（`data-theme`、三个变量名、
`attributeFilter: ["data-theme"]`、`prefers-color-scheme`、不得回到写死白底）。
