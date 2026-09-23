# TOS 7 平台缺陷：非 root 应用无法访问共享文件夹

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