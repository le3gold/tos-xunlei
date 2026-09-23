#!/usr/bin/env python3
"""Independent verifier for the TOS 7 Deb package built by build.py.

This module deliberately does NOT reuse anything from build.py: it re-reads
the produced .deb byte-for-byte, parses the ar container and both inner tar
archives itself and re-checks every rule from the TOS 7 Application
Development Guide that this package claims to satisfy.  A build that passes
here is internally consistent; it still has to be installed on a real TNAS.

Usage:
    python tools/verify_deb.py out/<appid>_<platform>.deb
"""
import bz2
import hashlib
import io
import json
import os
import re
import sys
import tarfile

AR_MAGIC = b"!<arch>\n"

# nginx variables that the platform's nginx.conf is known to define. Anything
# outside this set would abort `nginx -t` and take the whole TOS web UI down.
NGINX_SAFE_VARS = {
    "host", "server_port", "remote_addr", "remote_port", "http_upgrade",
    "http_cookie", "http_referer", "scheme", "proxy_add_x_forwarded_for",
    "request_uri", "uri", "args", "is_args", "document_root", "server_name",
    "http_host", "http_user_agent", "http_x_forwarded_for", "binary_remote_addr",
}

EXPECTED_LANGS = [
    "zh-cn", "zh-hk", "en-us", "de-de", "fr-fr", "es-es", "pt-pt", "it-it",
    "ru-ru", "pl-pl", "tr-tr", "ja-jp", "ko-kr", "hu-hu",
]


class Fail(SystemExit):
    def __init__(self, msg):
        super().__init__("VERIFY FAILED: " + msg)


class Checker:
    def __init__(self, verbose=True):
        self.n = 0
        self.verbose = verbose

    def ok(self, cond, msg):
        self.n += 1
        if not cond:
            raise Fail(msg)
        return True

    def note(self, msg):
        if self.verbose:
            print("     note: %s" % msg)


# --------------------------------------------------------------------- ar
def ar_members(blob):
    if not blob.startswith(AR_MAGIC):
        raise Fail("not an ar archive (bad magic)")
    off = len(AR_MAGIC)
    out = []
    while off < len(blob):
        hdr = blob[off:off + 60]
        if len(hdr) < 60:
            raise Fail("truncated ar member header at offset %d" % off)
        name = hdr[0:16].decode("ascii", "replace").strip()
        try:
            size = int(hdr[48:58].decode("ascii").strip())
        except ValueError:
            raise Fail("unparsable ar size field for member %r" % name)
        if hdr[58:60] != b"`\n":
            raise Fail("bad ar member trailer for %r" % name)
        body = blob[off + 60:off + 60 + size]
        if len(body) != size:
            raise Fail("short ar member %r" % name)
        out.append((name, body))
        off += 60 + size + (size % 2)
    return out


# -------------------------------------------------------------------- tar
def tar_entries(blob):
    """Return {path: (mode, typechar, bytes-or-None)}; paths keep tar's prefix."""
    res = {}
    with tarfile.open(fileobj=io.BytesIO(blob)) as tf:
        for ti in tf.getmembers():
            name = ti.name
            if name.startswith("./"):
                name = name[2:]
            if ti.isdir():
                res[name] = (ti.mode, "d", None)
            elif ti.isfile():
                res[name] = (ti.mode, "f", tf.extractfile(ti).read())
            else:
                res[name] = (ti.mode, "o", None)
    return res


def parse_control(text):
    fields = {}
    key = None
    for line in text.splitlines():
        if not line.strip():
            continue
        if line[0] in " \t" and key:
            fields[key] += "\n" + line.strip("\n")
            continue
        if ":" not in line:
            raise Fail("control line without a colon: %r" % line)
        key, val = line.split(":", 1)
        key = key.strip()
        fields[key] = val.strip()
    return fields


# ------------------------------------------------------------------ checks
def verify(deb_store, cfg, verbose=True):
    c = Checker(verbose)
    app = cfg["APP_ID"]
    ver = cfg["APP_VERSION"] + "-" + cfg["PKG_RELEASE"] if cfg.get("PKG_RELEASE") else cfg["APP_VERSION"]
    root = "usr/local/%s" % app

    # ---- file name: the guide forbids versions in the released file name
    base = os.path.basename(deb_store)
    c.ok(base == "%s_%s.deb" % (app, cfg["PLATFORM"]),
         "release asset must be named <appid>_<platform>.deb, got %r" % base)
    # ---- version consistency: the developer platform compares config.ini,
    #      DEBIAN/control and the Release tag, and requires xx.yy.zzz
    c.ok(re.fullmatch(r"\d+\.\d+\.\d+", cfg["APP_VERSION"]),
         "the developer platform only accepts xx.yy.zzz versions, got %r"
         % cfg["APP_VERSION"])
    c.ok(not cfg.get("PKG_RELEASE"),
         "a package release suffix makes DEBIAN/control disagree with the "
         "Release tag version; keep one version number everywhere")

    blob = open(deb_store, "rb").read()
    members = ar_members(blob)

    # ---- ar layout
    names = [m[0] for m in members]
    c.ok(names == ["debian-binary", "control.tar.gz", "data.tar.xz"],
         "unexpected ar member list: %r" % names)
    payload = dict(members)
    c.ok(payload["debian-binary"] == b"2.0\n",
         "debian-binary must be exactly b'2.0\\n'")

    ctrl = tar_entries(payload["control.tar.gz"])
    data = tar_entries(payload["data.tar.xz"])

    # ---- control script set
    for name in ("control", "md5sums", "preinst", "postinst", "prerm", "postrm"):
        c.ok(name in ctrl, "control.tar.gz is missing %s" % name)
    for name in ("preinst", "postinst", "prerm", "postrm"):
        c.ok(ctrl[name][0] == 0o755, "%s must be mode 0755" % name)
    for name in ("control", "md5sums"):
        c.ok(ctrl[name][0] == 0o644, "%s must be mode 0644" % name)

    # ---- control fields
    c.ok(ctrl["control"][2].endswith(b"\n") and ctrl["md5sums"][2].endswith(b"\n"),
         "control and md5sums must end with a newline (dpkg requirement)")
    for name in ("preinst", "postinst", "prerm", "postrm"):
        c.ok(ctrl[name][2].endswith(b"\n"), "%s must end with a newline" % name)
    fields = parse_control(ctrl["control"][2].decode("utf-8"))
    c.ok(fields.get("Package") == app, "control Package must be %r" % app)
    c.ok(fields.get("Version") == ver, "control Version must be %r, got %r" % (ver, fields.get("Version")))
    c.ok(fields.get("Architecture") == cfg["ARCH"],
         "control Architecture must be %r" % cfg["ARCH"])
    c.ok("Maintainer" in fields and fields["Maintainer"], "control needs a Maintainer")
    c.ok(fields.get("Installed-Size", "").isdigit(), "Installed-Size must be a number")
    c.ok("Depends" in fields, "control needs a Depends field")
    desc = fields.get("Description", "")
    c.ok(desc and not desc.startswith(" "), "control Description must have a synopsis line")

    # ---- md5sums must match the payload
    listed = {}
    for line in ctrl["md5sums"][2].decode("utf-8").splitlines():
        if not line.strip():
            continue
        h, p = line.split(None, 1)
        listed[p.strip()] = h
    real_files = {k: v for k, v in data.items() if v[1] == "f"}
    for path, (_mode, _t, content) in real_files.items():
        c.ok(path in listed, "md5sums is missing %s" % path)
        c.ok(listed[path] == hashlib.md5(content).hexdigest(),
             "md5 mismatch for %s" % path)
    c.ok(len(listed) == len(real_files),
         "md5sums lists %d files but the payload has %d" % (len(listed), len(real_files)))

    # ---- everything lives under the app's own prefix (ancestor dirs allowed)
    for path in data:
        c.ok(path in ("usr", "usr/local", root) or path.startswith(root + "/"),
             "payload escapes %s/: %s" % (root, path))

    # ---- no unrendered template markers anywhere
    for path, (_m, t, content) in sorted(data.items()):
        if t != "f" or path.endswith("webui.bz2"):
            continue
        if b"\x00" in content:
            continue  # upstream binary payload, not a rendered template
        c.ok(b"@@" not in content, "unrendered template marker in %s" % path)

    # ---- config.ini
    cfgpath = root + "/config.ini"
    c.ok(cfgpath in data, "config.ini is missing")
    raw = data[cfgpath][2].decode("utf-8")
    for line in raw.splitlines():
        stripped = line.strip()
        c.ok(not stripped.startswith(("//", "#", "/*", ";")),
             "config.ini must not contain comments: %r" % stripped[:40])
    conf = json.loads(raw)  # raises on trailing commas / single quotes
    c.ok(conf["id"] == app, "config.ini.id must equal %r" % app)
    c.ok(conf["type"] == "iframe", "config.ini.type must be 'iframe'")
    c.ok(conf["path"] == "/%s/" % app, "config.ini.path must be '/%s/'" % app)
    c.ok("open_path" not in conf,
         "config.ini must not mix type with open_path (guide 8.4.1)")
    c.ok(conf.get("application_type") == "deb", "config.ini.application_type must be 'deb'")
    c.ok(conf.get("system_id") == app, "config.ini.system_id must equal the app id")
    c.ok(conf.get("package") == app, "config.ini.package must equal the app id")
    c.ok(conf.get("user") == app, "config.ini.user must equal the app id")
    c.ok(conf.get("user") not in (None, "", "root", "0"),
         "config.ini.user must be a dedicated non-root user")
    c.ok(conf.get("version") == ver, "config.ini.version must equal %r" % ver)
    c.ok(conf.get("platform") == cfg["PLATFORM"], "config.ini.platform mismatch")
    c.ok(conf.get("icon") == "/images/icons/%s.svg" % app, "config.ini.icon path mismatch")
    c.ok(conf.get("category"), "config.ini.category must not be empty")
    c.ok(cfg["SHARE_NAME"] in conf.get("share_folders", []),
         "config.ini.share_folders must declare %r (required for user data)"
         % cfg["SHARE_NAME"])
    for field in ("resize", "maxmin", "width", "height"):
        c.ok(field in conf, "config.ini should set %r so the window is usable" % field)

    # ---- language file
    langpath = root + "/%s.lang" % app
    c.ok(langpath in data, "%s.lang is missing" % app)
    lang = data[langpath][2].decode("utf-8")
    for sec in EXPECTED_LANGS:
        c.ok("[%s]" % sec in lang, "language file is missing section [%s]" % sec)
    c.ok('version = "%s"' % ver in lang, "language file must carry the package version")

    # ---- icon
    iconpath = root + "/images/icons/%s.svg" % app
    c.ok(iconpath in data, "icon %s.svg is missing" % app)
    svg = data[iconpath][2].decode("utf-8", "replace")
    c.ok("<svg" in svg, "icon is not an svg")
    c.ok("viewBox" in svg, "icon svg needs a viewBox so it scales")
    c.ok("<text" not in svg, "icon must not depend on font rendering")

    # ---- distribution identification used by the /etc/os-release repair
    c.ok(root + "/os-release" in data,
         "os-release fallback is missing; postinst needs it to repair /etc/os-release")

    # ---- systemd unit
    unit = root + "/init.d/%s.service" % app
    c.ok(unit in data, "systemd unit %s.service is missing" % app)
    c.ok(data[unit][0] == 0o644, "the service unit must be mode 0644")
    usvc = data[unit][2].decode("utf-8")
    c.ok("User=%s" % app in usvc, "unit must run as User=%s" % app)
    c.ok("User=root" not in usvc and "User=0" not in usvc, "unit must not run as root")
    c.ok("PrivateTmp=true" not in usvc,
         "iframe applications must not use PrivateTmp=true (guide 8.12)")
    c.ok("ProtectSystem=strict" in usvc, "unit must set ProtectSystem=strict")
    c.ok("NoNewPrivileges=true" in usvc, "unit must set NoNewPrivileges=true")
    c.ok("ReadWritePaths=/var/lib/%s" % app in usvc,
         "unit must declare ReadWritePaths=/var/lib/%s" % app)
    exec_match = re.search(r"^ExecStart=(.*)$", usvc, re.M)
    c.ok(exec_match, "unit needs an ExecStart")
    c.ok("$" not in exec_match.group(1), "ExecStart must not contain shell variables")
    c.ok(exec_match.group(1).strip() == "/var/lib/%s/runtime/%s" % (app, app),
         "ExecStart must point at /var/lib/%s/runtime/%s; TOS moves the"
         " payload onto a volume whose rich ACL may not admit this user,"
         " so the service must run from its own copy" % (app, app))
    c.ok("WorkingDirectory=/var/lib/%s\n" % app in usvc,
         "WorkingDirectory must be the application state directory, never the"
         " payload path (systemd fails with 200/CHDIR otherwise)")
    c.ok("EnvironmentFile=" in usvc, "unit should load the packaged EnvironmentFile")

    # ---- nginx snippet
    ngx = root + "/nginx/%s.conf" % app
    c.ok(ngx in data, "nginx snippet %s.conf is missing" % app)
    n = data[ngx][2].decode("utf-8")
    # comments are not configuration: check the directive text only
    n_code = "\n".join(re.sub(r"#.*$", "", line) for line in n.splitlines())
    c.ok(not re.search(r"\bserver\s*\{", n_code),
         "nginx snippet must not define a server block")
    c.ok("location ^~ /%s/app/" % app in n_code,
         "nginx snippet must expose the engine under /%s/app/" % app)
    c.ok("proxy_pass http://127.0.0.1:%s/" % cfg["WEBUI_PORT"] in n_code,
         "nginx proxy_pass must target 127.0.0.1:%s" % cfg["WEBUI_PORT"])
    for var in set(re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", n_code)):
        c.ok(var in NGINX_SAFE_VARS,
             "nginx snippet uses $%s, which the platform nginx does not define" % var)

    # ---- entry point
    entry = root + "/bin/%s" % app
    c.ok(entry in data, "entry point bin/%s is missing" % app)
    c.ok(data[entry][0] == 0o755, "bin/%s must be executable" % app)
    e = data[entry][2].decode("utf-8")
    c.ok(e.startswith("#!/bin/bash"), "bin/%s must start with #!/bin/bash" % app)
    c.ok("ter_share_add" in e, "entry point must resolve the shared folder")
    c.ok('DriveListen="0.0.0.0:' in e,
         "the engine must listen on 0.0.0.0 (guide 8.3 forbids loopback-only)")
    c.ok(cfg["XL_PLATFORM"] in e, "entry point must pass PLATFORM=terramaster")
    c.ok("xunlei-pan-cli-launcher.%s" % cfg["ARCH"] in e,
         "entry point must start the official launcher")
    c.ok('readlink -f "$0"' in e,
         "entry point must resolve its own directory; the runtime copy and "
         "the packaged tree are different paths")
    e_code = "\n".join(re.sub(r"#.*$", "", l) for l in e.splitlines())
    c.ok("/usr/local/" not in e_code,
         "entry point must not depend on /usr/local/<appid>: TOS relocates it "
         "onto a volume the application user may not be able to read")

    # ---- engine payload, byte for byte
    engine = root + "/bin/xunlei-pan-cli.%s.%s" % (cfg["ENGINE_VERSION"], cfg["ARCH"])
    launcher = root + "/bin/xunlei-pan-cli-launcher.%s" % cfg["ARCH"]
    for path, digest_key, label in ((engine, "ENGINE_SHA256", "engine"),
                                    (launcher, "LAUNCHER_SHA256", "launcher")):
        c.ok(path in data, "%s binary %s is missing" % (label, os.path.basename(path)))
        c.ok(data[path][0] == 0o755, "%s binary must be mode 0755" % label)
        got = hashlib.sha256(data[path][2]).hexdigest()
        c.ok(got == cfg[digest_key],
             "%s sha256 mismatch:\n  expected %s\n  got      %s"
             % (label, cfg[digest_key], got))
    c.ok(data[root + "/bin/version"][2].decode().strip() == cfg["ENGINE_VERSION"],
         "bin/version must record the packaged engine version")
    c.ok(root + "/PROVENANCE.md" in data, "PROVENANCE.md is missing")

    # ---- webui.bz2 (mandatory for iframe applications)
    web = root + "/webui.bz2"
    c.ok(web in data, "webui.bz2 is mandatory for iframe applications")
    raw_bz2 = data[web][2]
    inner = tar_entries(bz2.decompress(raw_bz2))
    c.ok("index.html" in inner, "webui.bz2 must carry index.html at its root")
    html = inner["index.html"][2].decode("utf-8")
    c.ok("<iframe" in html, "the loader page must mount the engine in an iframe")
    c.ok('src="./app/"' in html, "the loader iframe must point at ./app/")
    c.ok('id="bar"' in html and "41px" in html,
         "the loader must reserve the strip the TOS desktop overlays on"
         " type:iframe windows (40px menu + 1px border); without it the"
         " engine's own toolbar sits under the desktop's close button and"
         " cannot be clicked")
    c.ok("icon.svg" in inner,
         "the title bar icon must ship inside webui.bz2; /images/... in"
         " config.ini is not reachable from inside the window")
    # The desktop paints its own help / minimise / maximise / close buttons on
    # top of that strip. Three of them are grey SVG images, but the close
    # button is a font glyph coloured with var(--common-font-level3), which is
    # a dark grey in the light theme and white at 45 percent opacity in the
    # dark theme: over a permanently white strip it disappears until hovered.
    # The bar therefore has to follow the desktop's theme.
    c.ok("data-theme" in html and '[data-theme="dark"]' in html,
         "the title bar must have a dark palette keyed off the desktop's"
         " data-theme, because the desktop's close glyph turns white in the"
         " dark theme and would be invisible on a white bar")
    c.ok("--main-bg-color" in html and "--dialog-title-color" in html
         and "--common-line-level1" in html,
         "the title bar must read the desktop's own window colours"
         " (--main-bg-color / --dialog-title-color / --common-line-level1)"
         " instead of hard-coding a palette")
    c.ok('attributeFilter: ["data-theme"]' in html,
         "the title bar must follow a theme change made while the window is"
         " open (MutationObserver on the desktop's data-theme)")
    c.ok("prefers-color-scheme" in html,
         "the title bar needs a fallback palette for when the parent document"
         " is not readable")
    c.ok("#27313f" not in html and "background: #fff; border-bottom" not in html,
         "the title bar must not go back to a fixed white background and a"
         " fixed dark text colour")

    # ---- lifecycle scripts
    scripts = {}
    for name in ("preinst", "postinst", "prerm", "postrm"):
        body = ctrl[name][2].decode("utf-8")
        # comments are documentation, not behaviour
        code = "\n".join(re.sub(r"#.*$", "", line) for line in body.splitlines())
        scripts[name] = code
        c.ok(body.startswith("#!/bin/bash"), "%s must start with #!/bin/bash" % name)
        c.ok("useradd" not in code and "adduser" not in code,
             "%s must not create users; the platform does that (guide 8.14)" % name)
        c.ok("@@" not in code, "unrendered template marker in %s" % name)
    postrm = scripts["postrm"]
    c.ok(not re.search(r"rm\s+-rf?\s+/Volume", postrm),
         "postrm must never delete the user's shared folder")
    c.ok("ter_share_add" not in postrm,
         "postrm must not recreate or remove the user's shared folder")
    postinst = scripts["postinst"]
    c.ok("webui.bz2" in postinst, "postinst must unpack webui.bz2")
    c.ok("os-release" in postinst,
         "postinst must repair /etc/os-release; the Xunlei engine aborts without it")
    entry_code = "\n".join(re.sub(r"#.*$", "", l)
                           for l in data[root + "/bin/" + app][2].decode("utf-8").splitlines())
    c.ok("/etc/os-release" in entry_code,
         "entry point must warn when /etc/os-release is unreadable")
    c.ok("daemon-reload" in postinst, "postinst must reload systemd")
    c.ok("ter_share_add" in postinst, "postinst must create the shared folder")
    c.ok("-owner" in postinst,
         "postinst must pass -owner to ter_share_add so TOS provisions the"
         " shared folder for the application user (guide 10.6)")
    c.ok("RUNTIME_DIR" in postinst and
         "cp -f" in postinst and
         "xunlei-pan-cli-launcher." in postinst,
         "postinst must copy the executables into the application's own "
         "runtime directory; the service runs from that copy")
    c.ok("tmacltool" in postinst and
         "user:${APP_ID}:allow:rwxpdDaARWc:fd" in postinst,
         "postinst must grant the application user the TerraMaster rich ACL"
         " on the shared folder, as the first-party download apps do")
    c.ok("SHARE_VOL" in postinst and
         "user:${APP_ID}:allow:r-x:--" in postinst,
         "postinst must grant the application user traversal of the volume"
         " root; without it the entry on the shared folder is unreachable"
         " (docs/PLATFORM-DEFECT.md)")
    c.ok("tmacltool" not in e,
         "the entry point runs as the application user and must not pretend"
         " to change ACLs")
    c.ok("tmacltool del" in postrm and
         "user:${APP_ID}:allow:r-x:--" in postrm,
         "postrm must remove the volume-root traversal entry it added")
    c.ok("not writable by" in e,
         "entry point must probe the shared folder and report it unwritable")
    c.ok("${DATA_DIR}/download" in e,
         "entry point needs a writable fallback location for downloads")
    # The engine offers <ConfigPath>/download as a second download root and
    # ConfigPath is ${DATA_DIR}, i.e. the system disk. That entry must resolve
    # to the shared folder, never to /dev/md9.
    c.ok('ln -sfn "${DOWNLOAD_PATH}" "${DATA_DIR}/download"' in e,
         "the engine's own download root (${DATA_DIR}/download, on the system"
         " disk) must be a symlink to the shared folder so a task sent there"
         " cannot fill the system disk")
    c.ok('[ "${DOWNLOAD_PATH}" = "${SHARE_PATH}/download" ]' in e,
         "that symlink may only be made when the shared folder is the download"
         " target; in the fallback ${DATA_DIR}/download is the target itself")
    c.ok('[ -h "${DATA_DIR}/download" ]' in e and
         'rmdir "${DATA_DIR}/download"' in e,
         "the entry point must only replace an empty directory or its own link,"
         " never delete an existing download tree")
    c.ok('mkdir -p "${DATA_DIR}/bin" "${DATA_DIR}/.drive" "${DATA_DIR}/download"'
         not in e,
         "the entry point must not create ${DATA_DIR}/download unconditionally;"
         " that path belongs to the shared folder now")
    prerm = scripts["prerm"]
    c.ok("systemctl stop" in prerm, "prerm must stop the service")

    print("  verified %d assertions on %s (%s, %d bytes)"
          % (c.n, base, ver, len(blob)))
    return True


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = {}
    with open(os.path.join(here, "config.env"), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            cfg[k.strip()] = v
    verify(argv[1], cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))