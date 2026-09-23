#!/usr/bin/env python3
"""
build.py - assemble the TOS 7 Deb package for the Xunlei download station.

Runs anywhere with Python 3.8+ (no dpkg-deb, no ar, no Linux required):
the Deb container is written byte-for-byte by this script.

Stages:  fetch -> stage -> webui -> deb -> verify

Products (out/):
  <APP_ID>_<VERSION>_<ARCH>.deb      full-version name, for local dpkg -i
  <APP_ID>_<PLATFORM>.deb            release asset name (recommended form; the
                                     platform decides the package type from the
                                     .deb extension and reads the version from
                                     config.ini, not from the release tag)
  <APP_ID>_<PLATFORM>.deb.sha256     checksum sidecar required by the platform
"""
import bz2
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import struct
import sys
import tarfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
DL = os.path.join(BUILD, "downloads")
STAGE = os.path.join(BUILD, "pkgroot")
OUT = os.path.join(HERE, "out")
ASSETS = os.path.join(HERE, "assets")

EPOCH = 0
GH_FORMAT = tarfile.GNU_FORMAT


# --------------------------------------------------------------------------- config
def load_config():
    cfg = {}
    with open(os.path.join(HERE, "config.env"), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            cfg[k.strip()] = v
    return cfg


def render(text, cfg, extra=None):
    values = dict(cfg)
    values["VERSION"] = full_version(cfg)
    if extra:
        values.update(extra)
    out = re.sub(r"@@([A-Z0-9_]+)@@", lambda m: values.get(m.group(1), m.group(0)), text)
    out = re.sub(r"@([A-Z0-9_]+)@", lambda m: values.get(m.group(1), m.group(0)), out)
    return out


def full_version(cfg):
    rel = cfg.get("PKG_RELEASE", "")
    return f"{cfg['APP_VERSION']}-{rel}" if rel else cfg["APP_VERSION"]


def read(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    # A text file that does not end in a newline makes dpkg reject the
    # package ("end of file during value of field 'Description'").
    return text if text.endswith("\n") else text + "\n"


# --------------------------------------------------------------------------- fetch
def fetch(url, dest, sha256=None):
    if os.path.isfile(dest) and os.path.getsize(dest) > 0:
        if sha256 is None or digest(dest) == sha256:
            log(f"cached   {os.path.basename(dest)}")
            return dest
        log(f"stale    {os.path.basename(dest)} (checksum changed) - refetching")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    log(f"download {os.path.basename(dest)}  <- {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "tos-app-packager/1.0"})
    tmp = dest + ".part"
    with urllib.request.urlopen(req, timeout=180) as resp, open(tmp, "wb") as fh:
        shutil.copyfileobj(resp, fh, 1 << 20)
    got = digest(tmp)
    if sha256 and got != sha256:
        os.remove(tmp)
        die(f"sha256 mismatch for {os.path.basename(dest)}\n  expected {sha256}\n  got      {got}")
    os.replace(tmp, dest)
    return dest


def fetch_launcher(cfg):
    """Return the official Xunlei launcher binary.

    Xunlei does not publish the launcher as a standalone download; it only
    ships it inside its own platform packages. This pulls it out of the SPK
    that Xunlei publishes on its own CDN (sandai.net) and checks it against
    the pinned sha256/md5, byte for byte. Nothing is patched.
    """
    dest = os.path.join(DL, f"xunlei-pan-cli-launcher.{cfg['ARCH']}")
    if os.path.isfile(dest) and digest(dest) == cfg["LAUNCHER_SHA256"]:
        log(f"cached   {os.path.basename(dest)}")
        return dest

    spk = fetch(cfg["SPK_URL"], os.path.join(DL, os.path.basename(cfg["SPK_URL"])),
                cfg["SPK_SHA256"])
    member = cfg["LAUNCHER_MEMBER"].lstrip("./")

    with tarfile.open(spk, "r:*") as outer:
        inner = None
        for name in outer.getnames():
            if name.lstrip("./").endswith("package.tgz"):
                inner = name
                break
        if inner is None:
            die(f"{os.path.basename(spk)} does not contain package.tgz")
        raw = outer.extractfile(inner).read()

    blob = None
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as payload:
        for ti in payload.getmembers():
            if ti.isfile() and ti.name.lstrip("./") == member:
                blob = payload.extractfile(ti).read()
                break
    if blob is None:
        die(f"{member} not found inside {inner}")

    got = hashlib.sha256(blob).hexdigest()
    if got != cfg["LAUNCHER_SHA256"]:
        die(f"launcher sha256 mismatch\n  expected {cfg['LAUNCHER_SHA256']}\n  got      {got}")
    if hashlib.md5(blob).hexdigest() != cfg["LAUNCHER_MD5"]:
        die("launcher md5 mismatch")

    os.makedirs(DL, exist_ok=True)
    with open(dest, "wb") as fh:
        fh.write(blob)
    log(f"extracted {os.path.basename(dest)} ({len(blob):,} bytes) from {os.path.basename(spk)}")
    return dest


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- stage
def put(path, data, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))
    record_mode(path, mode)


def record_mode(path, mode):
    MODES[os.path.relpath(path, STAGE).replace(os.sep, "/")] = mode


MODES = {}


def stage_tree(cfg):
    app = cfg["APP_ID"]
    root = os.path.join(STAGE, "usr", "local", app)

    put(os.path.join(root, "config.ini"), render(read(os.path.join(ASSETS, "config.ini.in")), cfg))
    # validate: config.ini must be strict JSON
    json.loads(read(os.path.join(root, "config.ini")))

    put(os.path.join(root, f"{app}.lang"), render(read(os.path.join(ASSETS, "app.lang")), cfg))
    put(os.path.join(root, f"{app}.env"), render(read(os.path.join(ASSETS, "app.env.in")), cfg))
    put(os.path.join(root, "images", "icons", f"{app}.svg"),
        read(os.path.join(ASSETS, "images", "icons", f"{app}.svg")))
    # Distribution identification, used to repair /etc/os-release when a
    # legacy application has made it unreadable (see postinst).
    put(os.path.join(root, "os-release"), read(os.path.join(ASSETS, "os-release")))
    put(os.path.join(root, "init.d", f"{app}.service"),
        render(read(os.path.join(ASSETS, "init.d", "app.service.in")), cfg))
    put(os.path.join(root, "nginx", f"{app}.conf"),
        render(read(os.path.join(ASSETS, "nginx", "app.conf.in")), cfg))
    put(os.path.join(root, "bin", app),
        render(read(os.path.join(ASSETS, "bin", "app.in")), cfg), 0o755)

    # engine payload - lives in bin/ next to the entry point, exactly like
    # the official TerraMaster Xunlei package ships it
    bindir = os.path.join(root, "bin")
    engine = fetch(cfg["ENGINE_URL"], os.path.join(DL, f"xunlei-pan-cli.{cfg['ENGINE_VERSION']}.{cfg['ARCH']}"),
                   cfg["ENGINE_SHA256"])
    launcher = fetch_launcher(cfg)
    for src, name in ((engine, f"xunlei-pan-cli.{cfg['ENGINE_VERSION']}.{cfg['ARCH']}"),
                      (launcher, f"xunlei-pan-cli-launcher.{cfg['ARCH']}")):
        dst = os.path.join(bindir, name)
        os.makedirs(bindir, exist_ok=True)
        shutil.copyfile(src, dst)
        record_mode(dst, 0o755)
    put(os.path.join(bindir, "version"), cfg["ENGINE_VERSION"], 0o644)

    # provenance / audit chain
    put(os.path.join(root, "PROVENANCE.md"), provenance(cfg))
    return root


def provenance(cfg):
    return f"""# PROVENANCE

This package re-distributes an unmodified official Xunlei artifact.

| Field | Value |
|---|---|
| Application | {cfg['APP_ID']} ({cfg['APP_VERSION']}) |
| Engine version | {cfg['ENGINE_VERSION']} |
| Engine source | {cfg['ENGINE_URL']} |
| Engine sha256 | {cfg['ENGINE_SHA256']} |
| Launcher source | {cfg['SPK_URL']} (member {cfg['LAUNCHER_MEMBER']}) |
| Launcher container sha256 | {cfg['SPK_SHA256']} |
| Launcher sha256 | {cfg['LAUNCHER_SHA256']} |
| Launcher md5 | {cfg['LAUNCHER_MD5']} |
| Upstream vendor | Xunlei Limited (https://www.xunlei.com) |
| Fetch channel | the update channel that the official Xunlei NAS package itself polls |

The engine binary is copied byte-for-byte; nothing inside it is patched. Only
the launch environment is supplied here, exactly as Xunlei's own TerraMaster
build does (`PLATFORM=terramaster`, `NasId=terramaster`). With that platform
value Xunlei's cloud returns the TerraMaster profile, whose login banner reads
"该版本为铁威马用户专享".

Platform-run services are started by Xunlei itself; this package only makes the
engine reachable inside the TOS desktop.
"""


# --------------------------------------------------------------------------- webui.bz2
LOADER = """<!DOCTYPE html>
<html lang="zh-cn">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
<title>迅雷</title>
<style>
  html, body { margin: 0; padding: 0; height: 100%%; overflow: hidden; background: #fff; }

  /* TOS draws NO title bar for `type: "iframe"` applications. The desktop
     overlays a 40px "micro" menu (.tos-dialog-menu.micro) across the top of
     the window instead: it carries the drag handle plus the help / minimise /
     maximise / close buttons, and it swallows the pointer events for that
     whole strip. The Xunlei SPA puts its own toolbar in exactly that strip,
     so its 新建任务 button sat under the desktop's close button and could not
     be pressed. Nothing is reserved for the application, so the application
     reserves it: this bar is the window's title bar, styled after the native
     .tos-dialog-header (40px tall, 16px inset, 24px icon, 10px gap) and made
     41px tall to clear that 40px menu plus its 1px bottom border. */
  #bar {
    height: 41px; box-sizing: border-box; display: flex; align-items: center;
    padding-left: 16px; background: #fff; border-bottom: 1px solid rgba(0, 0, 0, .06);
    font: 700 14px/41px system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    color: #27313f; user-select: none; -webkit-user-select: none;
  }
  #bar img { width: 24px; height: 24px; display: block; }
  #bar span { margin-left: 10px; }

  #app { display: block; border: 0; width: 100%%; height: calc(100%% - 41px); }
</style>
</head>
<body>
<!-- The Xunlei SPA is served by the engine itself and reverse-proxied by
     /%(app)s/app/ ; this page is only the fixed entry point the TOS desktop
     loads inside the application window, plus the title bar described above. -->
<div id="bar"><img src="./icon.svg" alt="" /><span>迅雷</span></div>
<iframe id="app" src="./app/" allow="clipboard-read; clipboard-write; fullscreen"></iframe>
</body>
</html>
"""


def build_webui(cfg, root):
    app = cfg["APP_ID"]
    payload = {
        "index.html": (LOADER % {"app": app}).encode("utf-8"),
        # The title bar in the loader shows the application icon, so the icon
        # has to travel with the archive the platform serves at /<appid>/ -
        # the /images/icons/ path in config.ini is the App Center's own copy
        # and is not reachable from inside the window.
        "icon.svg": read(os.path.join(ASSETS, "images", "icons",
                                      f"{app}.svg")).encode("utf-8"),
    }
    out = os.path.join(root, "webui.bz2")
    buf = io.BytesIO()
    # deterministic: sorted names, root:root, mtime 0, no PAX headers
    with tarfile.open(fileobj=buf, mode="w", format=GH_FORMAT) as tf:
        for name in sorted(payload):
            ti = tarfile.TarInfo(name)
            ti.size = len(payload[name])
            ti.mode = 0o644
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = "root"
            ti.mtime = EPOCH
            tf.addfile(ti, io.BytesIO(payload[name]))
    raw = buf.getvalue()
    with open(out, "wb") as fh:
        fh.write(bz2.compress(raw, 9))
    record_mode(out, 0o644)
    # sanity: must contain an openable html at the archive root
    with tarfile.open(out, "r:bz2") as tf:
        names = tf.getnames()
    if "index.html" not in names:
        die("webui.bz2 does not contain index.html at its root")
    log(f"webui.bz2 {len(open(out,'rb').read())} bytes -> {names}")
    return out


# --------------------------------------------------------------------------- deb
def control_file(cfg):
    text = render(read(os.path.join(ASSETS, "control.in")), cfg)
    text = text.replace("@@SIZE@@", "0")  # patched below
    return text


def write_deb(cfg, root):
    app = cfg["APP_ID"]
    ver = full_version(cfg)
    work = os.path.join(BUILD, "debian")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)

    # ---- control ----
    size_kb = 0
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            try:
                size_kb += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    size_kb = max(1, size_kb // 1024)

    control = render(read(os.path.join(ASSETS, "control.in")), cfg).replace("@@SIZE@@", str(size_kb))
    ctrl_dir = os.path.join(work, "control")
    os.makedirs(ctrl_dir)
    with open(os.path.join(ctrl_dir, "control"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(control)

    # Windows cannot express the mode through the filesystem, so the tar
    # members of the control archive get their modes from this table.
    ctrl_modes = {"control": 0o644, "md5sums": 0o644}
    for name in ("preinst", "postinst", "prerm", "postrm"):
        body = render(read(os.path.join(ASSETS, name)), cfg)
        path = os.path.join(ctrl_dir, name)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        ctrl_modes[name] = 0o755

    # ---- md5sums (paths are relative to /, DEBIAN itself excluded) ----
    lines = []
    for dirpath, dirs, files in os.walk(STAGE):
        dirs.sort()
        for f in sorted(files):
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, STAGE).replace(os.sep, "/")
            h = hashlib.md5()
            with open(full, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            lines.append(f"{h.hexdigest()}  {rel}")
    with open(os.path.join(ctrl_dir, "md5sums"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(sorted(lines)) + "\n")

    # ---- tar members ----
    # Deterministic container. gzip writes an mtime of its own accord, and
    # that alone changed the digest of the whole package on every build even
    # though not one byte of the payload differed. Pinning it to EPOCH makes
    # the same sources always produce the same .deb, so the sha256 published
    # alongside a release stays meaningful.
    ctrl_tar = os.path.join(work, "control.tar.gz")
    with open(ctrl_tar, "wb") as _ctrl_out:
        with gzip.GzipFile(fileobj=_ctrl_out, mode="wb", mtime=EPOCH,
                           compresslevel=9) as _ctrl_gz:
            with tarfile.open(fileobj=_ctrl_gz, mode="w",
                              format=GH_FORMAT) as tf:
                _add_tree(tf, ctrl_dir, prefix="./", modes=ctrl_modes)

    # Walk from the staging root: dpkg needs every member under ./usr/local/<app>/
    data_tar = os.path.join(work, "data.tar.xz")
    with tarfile.open(data_tar, "w:xz", format=GH_FORMAT) as tf:
        _add_tree(tf, STAGE, prefix="./")

    # ---- ar container ----
    os.makedirs(OUT, exist_ok=True)
    deb_full = os.path.join(OUT, f"{app}_{ver}_{cfg['ARCH']}.deb")
    _write_ar(deb_full, ctrl_tar, data_tar)

    deb_store = os.path.join(OUT, f"{app}_{cfg['PLATFORM']}.deb")
    shutil.copyfile(deb_full, deb_store)
    sha = digest(deb_store)
    with open(deb_store + ".sha256", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"{sha}  {os.path.basename(deb_store)}\n")
    return deb_full, deb_store, sha


def _add_tree(tf, root, prefix="./", modes=None):
    modes = MODES if modes is None else modes
    entries = []
    for dirpath, dirs, files in os.walk(root):
        dirs.sort()
        for name in list(dirs) + sorted(files):
            entries.append(os.path.join(dirpath, name))
    for full in sorted(entries):
        rel = os.path.relpath(full, root).replace(os.sep, "/")
        arc = prefix + rel
        ti = tf.gettarinfo(full, arcname=arc)
        ti.uid = ti.gid = 0
        ti.uname = ti.gname = "root"
        ti.mtime = EPOCH
        if ti.isdir():
            ti.mode = 0o755
        elif ti.isfile():
            mode = modes.get(rel)
            if mode is None:
                mode = 0o755 if os.access(full, os.X_OK) else 0o644
            ti.mode = mode
        if ti.isfile():
            with open(full, "rb") as fh:
                tf.addfile(ti, fh)
        else:
            tf.addfile(ti)


def _ar_member(name, payload):
    header = b"%-16s%-12d%-6d%-6d%-8s%-10d`\n" % (
        name.encode(), EPOCH, 0, 0, b"100644", len(payload))
    return header + payload + (b"\n" if len(payload) % 2 else b"")


def _write_ar(path, ctrl_tar, data_tar):
    with open(path, "wb") as fh:
        fh.write(b"!<arch>\n")
        fh.write(_ar_member("debian-binary", b"2.0\n"))
        fh.write(_ar_member("control.tar.gz", open(ctrl_tar, "rb").read()))
        fh.write(_ar_member("data.tar.xz", open(data_tar, "rb").read()))


# --------------------------------------------------------------------------- main
def log(msg):
    print(f"==> {msg}", flush=True)


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    cfg = load_config()
    for key in ("APP_ID", "APP_VERSION", "PLATFORM", "ARCH", "ENGINE_URL", "SPK_URL", "LAUNCHER_MEMBER"):
        cfg.get(key) or die(f"config.env is missing {key}")

    log(f"{cfg['APP_ID']} {full_version(cfg)} for {cfg['PLATFORM']}")
    shutil.rmtree(STAGE, ignore_errors=True)
    root = stage_tree(cfg)
    build_webui(cfg, root)
    deb_full, deb_store, sha = write_deb(cfg, root)

    log(f"deb      {deb_full}  ({os.path.getsize(deb_full):,} bytes)")
    log(f"asset    {deb_store}")
    log(f"sha256   {sha}")

    log("running the independent verifier")
    sys.path.insert(0, os.path.join(HERE, "tools"))
    import verify_deb  # noqa: E402
    verify_deb.verify(deb_store, cfg)


if __name__ == "__main__":
    main()