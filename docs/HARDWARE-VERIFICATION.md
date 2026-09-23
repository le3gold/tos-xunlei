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