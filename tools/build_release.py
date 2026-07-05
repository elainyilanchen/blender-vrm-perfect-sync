# -*- coding: utf-8 -*-
"""
Build the two release zips:

  dist/blender-vrm-perfect-sync-<ver>-lite-win64.zip   (~45 MB)
      Tool + docs + sample donors. Dependencies are fetched on demand by
      the launcher / setup wizard.

  dist/blender-vrm-perfect-sync-<ver>-full-win64.zip   (~450 MB)
      Everything bundled and ready to run offline:
      + runtime/python              portable CPython 3.12 (with tkinter)
      + runtime/blender-4.0.2-...   portable Blender (portable config)
        with the VRM add-on pre-installed and enabled

All third-party pieces are downloaded from official sources (or their
mirrors) and SHA-256 verified where the upstream publishes checksums.

Usage:  python tools/build_release.py v1.1.0
Needs:  any Python 3.8+, internet, ~2.5 GB free disk. Windows only
        (runs the bundled Blender once to install the add-on).
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
CACHE = os.path.join(DIST, "cache")
# 短顶层目录 + 短 blender 目录名:给 Windows 260 字符路径上限留足余量
# (实测踩坑:解压在微信接收文件夹这类深路径里,插件文件会超限装不上)
TOPDIR = "vrm-perfect-sync"
BLENDER_SHORT = "blender"

# ---- pinned dependencies -------------------------------------------------
BLENDER_DIRNAME = "blender-4.0.2-windows-x64"
BLENDER_ZIP = BLENDER_DIRNAME + ".zip"
BLENDER_URLS = [
    "https://mirrors.tuna.tsinghua.edu.cn/blender/release/Blender4.0/" + BLENDER_ZIP,
    "https://download.blender.org/release/Blender4.0/" + BLENDER_ZIP,
]
BLENDER_SHA_URLS = [  # official checksum list for the 4.0.2 release
    "https://mirrors.tuna.tsinghua.edu.cn/blender/release/Blender4.0/blender-4.0.2.sha256",
    "https://download.blender.org/release/Blender4.0/blender-4.0.2.sha256",
]
ADDON_ZIP = "VRM_Addon_for_Blender-2_34_1.zip"
_ADDON_GH = ("https://github.com/saturday06/VRM-Addon-for-Blender/"
             "releases/download/v2.34.1/" + ADDON_ZIP)
ADDON_URLS = [_ADDON_GH, "https://ghfast.top/" + _ADDON_GH]
PBS = "cpython-3.12.13+20260623-x86_64-pc-windows-msvc-install_only_stripped"
PBS_SHA256 = "de3e362376859b060fa8b856c434efa81fcf6d4ede3d6e177c7e2169670cac50"
_PBS_GH = ("https://github.com/astral-sh/python-build-standalone/releases/"
           "download/20260623/" + PBS + ".tar.gz")
PBS_URLS = [
    _PBS_GH,
    "https://registry.npmmirror.com/-/binary/python-build-standalone/"
    "20260623/" + PBS + ".tar.gz",
    "https://ghfast.top/" + _PBS_GH,
]

# files that make up the tool itself (both variants)
TOOL_FILES = [
    "Perfect-Sync.bat",
    "perfect_sync_gui.py",
    "perfect_sync_batch.py",
    "verify_clips.py",
    "tune_expression.py",
    "README.md",
    "README-English.txt",
    "README-简体中文.txt",
    "LICENSE",
    "docs/CLI.md",
    "docs/screenshot.png",
    "docs/screenshot-zh.png",
    "samples/README.md",
    "samples/female_model_perf_sync.vrm",
    "samples/male_model_perf_sync.vrm",
]

INSTALL_ADDON_PY = """import bpy, os, sys
zip_path = sys.argv[sys.argv.index("--") + 1]
bpy.ops.preferences.addon_install(filepath=zip_path, overwrite=True)
module = os.path.splitext(os.path.basename(zip_path))[0]
bpy.ops.preferences.addon_enable(module=module)
bpy.ops.wm.save_userpref()
try:
    bpy.ops.import_scene.vrm.get_rna_type()
    print("ADDON_INSTALL_OK", module)
except Exception as e:
    print("ADDON_INSTALL_FAIL", e)
"""


def log(*a):
    print(*a, flush=True)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(urls, dest, expected_sha=None):
    if os.path.isfile(dest):
        if expected_sha is None or sha256_of(dest) == expected_sha:
            log("  cached:", os.path.basename(dest))
            return dest
        os.remove(dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    last = None
    for url in urls:
        log("  fetching", url)
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r, \
                    open(dest + ".part", "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                done, mark = 0, 0
                while True:
                    chunk = r.read(1 << 19)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total and done * 10 // total > mark:
                        mark = done * 10 // total
                        log("    %d%%" % (mark * 10))
            os.replace(dest + ".part", dest)
            if expected_sha and sha256_of(dest) != expected_sha:
                log("    checksum MISMATCH, trying next source")
                os.remove(dest)
                continue
            return dest
        except Exception as e:
            last = e
            log("    failed:", e)
    raise RuntimeError("all sources failed for %s (%s)"
                       % (os.path.basename(dest), last))


def blender_sha():
    """Fetch the official sha256 list and return the zip's hash."""
    sha_file = download(BLENDER_SHA_URLS, os.path.join(CACHE,
                                                       "blender-4.0.2.sha256"))
    for line in open(sha_file, encoding="utf-8", errors="replace"):
        if BLENDER_ZIP in line:
            return line.split()[0].lower()
    raise RuntimeError("zip entry not found in blender sha256 list")


def copy_tool(stage):
    for rel in TOOL_FILES:
        src = os.path.join(ROOT, rel)
        dst = os.path.join(stage, TOPDIR, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


def zip_dir(stage, out_zip):
    if os.path.exists(out_zip):
        os.remove(out_zip)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _dirs, files in os.walk(stage):
            for name in files:
                p = os.path.join(base, name)
                z.write(p, os.path.relpath(p, stage))
    return out_zip


def main():
    ver = sys.argv[1] if len(sys.argv) > 1 else "dev"
    os.makedirs(CACHE, exist_ok=True)

    # ---------------- lite ----------------
    log("== lite ==")
    stage = os.path.join(DIST, "stage-lite")
    shutil.rmtree(stage, ignore_errors=True)
    copy_tool(stage)
    lite = zip_dir(stage, os.path.join(
        DIST, "blender-vrm-perfect-sync-%s-lite-win64.zip" % ver))
    log("  ->", lite, "%.1f MB" % (os.path.getsize(lite) / 1048576))

    # ---------------- full ----------------
    log("== full ==")
    log("downloading dependencies ...")
    bzip = download(BLENDER_URLS, os.path.join(CACHE, BLENDER_ZIP),
                    expected_sha=blender_sha())
    azip = download(ADDON_URLS, os.path.join(CACHE, ADDON_ZIP))
    pzip = download(PBS_URLS, os.path.join(CACHE, PBS + ".tar.gz"),
                    expected_sha=PBS_SHA256)

    stage = os.path.join(DIST, "stage-full")
    shutil.rmtree(stage, ignore_errors=True)
    copy_tool(stage)
    runtime = os.path.join(stage, TOPDIR, "runtime")

    log("extracting Blender ...")
    with zipfile.ZipFile(bzip) as z:
        z.extractall(runtime)
    # rename to the short dir name (path-length headroom)
    bhome = os.path.join(runtime, BLENDER_SHORT)
    os.rename(os.path.join(runtime, BLENDER_DIRNAME), bhome)
    # portable config BEFORE first run so prefs stay inside the bundle
    os.makedirs(os.path.join(bhome, "4.0", "config"), exist_ok=True)

    log("extracting portable Python ...")
    with tarfile.open(pzip, "r:gz") as t:
        t.extractall(runtime)
    assert os.path.isfile(os.path.join(runtime, "python", "python.exe"))

    log("installing VRM add-on into the bundled Blender ...")
    fd, tmp = tempfile.mkstemp(suffix=".py")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(INSTALL_ADDON_PY)
    try:
        r = subprocess.run(
            [os.path.join(bhome, "blender.exe"), "--background",
             "--python", tmp, "--", azip],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=600)
    finally:
        os.remove(tmp)
    if "ADDON_INSTALL_OK" not in (r.stdout or ""):
        log(r.stdout[-2000:] if r.stdout else "", r.stderr[-500:] if r.stderr else "")
        raise RuntimeError("add-on install failed")
    log("  add-on installed and enabled (portable prefs)")

    log("zipping full bundle (takes a few minutes) ...")
    full = zip_dir(stage, os.path.join(
        DIST, "blender-vrm-perfect-sync-%s-full-win64.zip" % ver))
    log("  ->", full, "%.1f MB" % (os.path.getsize(full) / 1048576))

    log("== checksums ==")
    for p in (lite, full):
        log(" ", sha256_of(p), os.path.basename(p))
    log("BUILD_DONE")


if __name__ == "__main__":
    main()
