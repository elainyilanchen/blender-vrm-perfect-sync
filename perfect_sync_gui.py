# -*- coding: utf-8 -*-
"""
VRM 完美同步小工具(图形界面) / VRM Perfect Sync Tool (GUI)
============================================================
每个"组合"左边放 1 个供体(已做完美同步的基准模型),右边放任意多个受体,
可开多个组合对应不同供体。后台调用 Blender 无界面跑批,日志实时显示。

零第三方依赖(tkinter + 标准库)。首次使用可在"初始化环境"里一键下载
便携版 Blender 4.0.2 + VRM 插件(约 400MB,与系统里已装的 Blender 互不干扰)。

运行:双击 启动完美同步工具.bat,或 python perfect_sync_gui.py
"""

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import urllib.request
import zipfile
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BATCH_SCRIPT = os.path.join(SCRIPT_DIR, "perfect_sync_batch.py")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "gui_config.json")
CREATE_NO_WINDOW = 0x08000000


def enable_dpi_awareness():
    """让 Windows 按真实像素渲染,避免在 2K/4K 高分屏上被位图拉伸发糊。
    必须在创建任何 Tk 窗口之前调用。返回缩放比(1.0=96dpi)。"""
    scale = 1.0
    try:
        import ctypes
        # Per-Monitor-V2(Win10 1703+),失败则退到 System-DPI-aware
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
        try:
            dpi = ctypes.windll.user32.GetDpiForSystem()
            scale = dpi / 96.0
        except Exception:
            pass
    except Exception:
        pass
    return scale

# ---------------- 便携环境(初始化下载用) ----------------
RUNTIME_DIR = os.path.join(SCRIPT_DIR, "runtime")
DL_DIR = os.path.join(RUNTIME_DIR, "downloads")
BLENDER_DIRNAME = "blender-4.0.2-windows-x64"
BLENDER_ZIP = BLENDER_DIRNAME + ".zip"
_BLENDER_TUNA = ("https://mirrors.tuna.tsinghua.edu.cn/blender/release/"
                 "Blender4.0/" + BLENDER_ZIP)
_BLENDER_OFFICIAL = ("https://download.blender.org/release/Blender4.0/"
                     + BLENDER_ZIP)
ADDON_ZIP = "VRM_Addon_for_Blender-2_34_1.zip"  # 官方标注支持 Blender 2.93-4.1
_ADDON_GH = ("https://github.com/saturday06/VRM-Addon-for-Blender/"
             "releases/download/v2.34.1/" + ADDON_ZIP)
_ADDON_PROXY = "https://ghfast.top/" + _ADDON_GH  # 国内加速代理,可能失效


def in_china():
    """判断是否国内环境,用于镜像源排序(判断错了也只是慢,不影响功能)。"""
    try:
        import ctypes
        if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0xFF == 0x04:
            return True  # 中文系统
    except Exception:
        pass
    try:
        import time
        return time.timezone == -28800  # UTC+8
    except Exception:
        return False


def blender_urls():
    return ([_BLENDER_TUNA, _BLENDER_OFFICIAL] if in_china()
            else [_BLENDER_OFFICIAL, _BLENDER_TUNA])


def addon_urls():
    return ([_ADDON_PROXY, _ADDON_GH] if in_china()
            else [_ADDON_GH, _ADDON_PROXY])
PORTABLE_EXE = os.path.join(RUNTIME_DIR, BLENDER_DIRNAME, "blender.exe")

# Blender 无界面模式的已知噪音日志,默认不显示
NOISE_RE = re.compile(
    r"Socket source|pyrna_enum_to_py|fake_module|TBBmalloc|addon-module|"
    r"NodeTreeInterface|Read prefs:|^Blender \d|Blender quit|"
    r"glTF import finished|Data are loaded|WARN \(bpy\.rna\)|^\s*$")
RESULT_RE = re.compile(r"BATCH_RESULT ok=(-?\d+) skip=(-?\d+) fail=(-?\d+)")

CHECK_PY = """import bpy
ok = False
try:
    bpy.ops.import_scene.vrm.get_rna_type()
    ok = True
except Exception:
    pass
print("BLVER", bpy.app.version_string)
print("VRMADDON", int(ok))
"""

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

# ---------------- 双语文本 ----------------
# 每项 (中文, English);App.t(key) 按当前语言取值

TEXT = {
    "title": ("VRM 完美同步小工具", "VRM Perfect Sync Tool"),
    "lang_label": ("语言 Language:", "语言 Language:"),
    "vrm0_hint": ("⚠ VRoid Studio 导出注意:① 选 \"VRM0.0\"(VRM 1.0 会被"
                  "拒收) ② 不要开启\"减少多边形/ポリゴンの削減\"等网格精简"
                  "选项(拓扑会变,表情无法转移)",
                  "⚠ VRoid Studio export: (1) choose \"VRM0.0\" (VRM 1.0 "
                  "is rejected)  (2) do NOT enable \"Reduce Polygons\" or "
                  "any mesh-reduction option (it changes the topology and "
                  "breaks the transfer)"),
    "mode_badge_normal": ("模式:普通 — 已有完美同步表情的模型会跳过",
                          "Mode: Normal — models that already have the "
                          "keys are skipped"),
    "mode_badge_overwrite": ("模式:覆盖 — 同名表情键/Clip 将被供体版本覆盖",
                             "Mode: Overwrite — existing keys/clips will "
                             "be replaced by the donor's"),
    "blender_loc": ("Blender 位置:", "Blender location:"),
    "browse": ("浏览...", "Browse..."),
    "setup_btn": ("初始化环境...", "Set up environment..."),
    "slot_title": ("组合 {}", "Group {}"),
    "donor_label": ("供体(基准模型,1 个)", "Donor (base model, 1 file)"),
    "pick_donor": ("选择供体...", "Choose donor..."),
    "del_slot": ("删除此组合", "Delete group"),
    "recip_label": ("受体(要加表情的模型,可多个)",
                    "Recipients (models to process, multiple OK)"),
    "add_recip": ("添加受体...", "Add recipients..."),
    "remove_sel": ("移除选中", "Remove selected"),
    "add_slot": ("+ 添加组合(不同供体开新组合)",
                 "+ Add group (new group per donor)"),
    "out_label": ("输出文件夹:", "Output folder:"),
    "suffix_label": ("  文件名后缀:", "  Filename suffix:"),
    "overwrite_chk": ("覆盖模式:已有表情的模型也重新转移(供体更新后刷新用)",
                      "Overwrite mode: re-transfer models that already have "
                      "the keys (use after updating a donor)"),
    "fulllog_chk": ("显示完整日志(调试用)", "Full log (debug)"),
    "start": ("开始处理", "Start"),
    "cancel": ("取消", "Cancel"),
    "open_out": ("打开输出文件夹", "Open output folder"),
    "ready": ("就绪", "Ready"),
    "cancelling": ("正在取消...", "Cancelling..."),
    "min_one_slot": ("至少要保留一个组合。", "At least one group must remain."),
    "hint": ("提示", "Note"),
    "donor_in_recips": ("这个文件已经在右边的受体列表里了。\n"
                        "同一个文件不能既当供体又当受体。",
                        "This file is already in the recipients list.\n"
                        "A file cannot be both donor and recipient."),
    "recip_is_donor": ("{} 是本组合的供体,不能同时作为受体,已跳过。",
                       "{} is this group's donor and cannot also be a "
                       "recipient; skipped."),
    "dlg_donor": ("选择供体模型(已做完美同步的那个)",
                  "Choose the donor model (the perfect-sync one)"),
    "dlg_recips": ("选择受体模型(可按住 Ctrl 多选)",
                   "Choose recipient models (Ctrl-click for multiple)"),
    "dlg_blender": ("找到 blender.exe(通常在 Program Files\\Blender "
                    "Foundation 里)",
                    "Locate blender.exe (usually under Program Files\\"
                    "Blender Foundation)"),
    "dlg_out": ("选择处理结果保存到哪个文件夹",
                "Choose where to save the results"),
    "vrm_filter": ("VRM 模型", "VRM model"),
    # 校验
    "v_no_blender": ("没有找到 Blender:点\"浏览\"选择 blender.exe,"
                     "或点\"初始化环境\"自动下载",
                     "Blender not found: click Browse to locate "
                     "blender.exe, or use Set up environment to download "
                     "it automatically"),
    "v_blender_missing": ("Blender 路径不存在: {}",
                          "Blender path does not exist: {}"),
    "v_no_batch": ("找不到处理脚本 perfect_sync_batch.py"
                   "(要和本工具放在同一个文件夹)",
                   "perfect_sync_batch.py not found (it must sit in the "
                   "same folder as this tool)"),
    "v_no_out": ("请选择输出文件夹", "Please choose an output folder"),
    "v_bad_out": ("输出文件夹路径无效: {}", "Invalid output folder: {}"),
    "v_bad_suffix": ("后缀里不能包含这些字符: < > : \" / \\ | ? *",
                     "The suffix may not contain: < > : \" / \\ | ? *"),
    "v_slot_no_donor": ("组合 {} 没有选择供体(左边)",
                        "Group {} has no donor (left side)"),
    "v_donor_missing": ("组合 {} 的供体文件不存在: {}",
                        "Group {} donor file does not exist: {}"),
    "v_slot_no_recip": ("组合 {} 没有添加受体(右边)",
                        "Group {} has no recipients (right side)"),
    "v_recip_missing": ("组合 {} 的受体不存在: {}",
                        "Group {} recipient does not exist: {}"),
    "v_dup_recip": ("{} 同时出现在组合 {} 和组合 {} 的受体里,请只保留一个",
                    "{} appears as a recipient in both group {} and group "
                    "{}; keep only one"),
    "v_donor_as_recip": ("{} 在组合 {} 是供体,但在组合 {} 是受体;"
                         "同一文件不能既当供体又当受体,请从受体里移除",
                         "{} is the donor of group {} but a recipient in "
                         "group {}; a file cannot be both - remove it from "
                         "the recipients"),
    "v_same_name": ("两个不同位置的文件都叫 {},输出会互相覆盖;请改名其中一个",
                    "Two files from different folders are both named {}; "
                    "their outputs would overwrite each other - rename one"),
    "v_overwrite_src": ("后缀为空且输出文件夹和 {} 所在文件夹相同,"
                        "会覆盖原文件;请加后缀或换输出文件夹",
                        "Empty suffix + same output folder as {} would "
                        "overwrite the original; add a suffix or change "
                        "the output folder"),
    "v_nothing": ("还没有添加任何模型:每个组合左边选 1 个供体,"
                  "右边添加要处理的模型",
                  "No models added yet: in each group choose 1 donor on "
                  "the left and add recipients on the right"),
    "fix_first": ("请先解决这些问题", "Please fix these first"),
    # 运行
    "mode_normal": ("当前为普通模式:已经有完美同步表情的模型会自动跳过。"
                    "如果想重新转移它们(例如供体更新过),请勾选\"覆盖模式\"。",
                    "Normal mode: models that already have the perfect-sync "
                    "keys will be SKIPPED. Tick 'Overwrite mode' to "
                    "re-transfer them (e.g. after updating a donor)."),
    "mode_overwrite": ("当前为覆盖模式:同名表情键/Clip 会被供体版本覆盖。",
                       "Overwrite mode: existing keys/clips with the same "
                       "names will be replaced by the donor's version."),
    "checking_env": ("正在检查 Blender 环境(版本 / VRM 插件)...",
                     "Checking the Blender environment (version / VRM "
                     "add-on)..."),
    "env_fail_run": ("无法运行 Blender 进行检查: {}",
                     "Failed to run Blender for the check: {}"),
    "env_ver": ("Blender 版本 {},VRM 插件:{}",
                "Blender {}, VRM add-on: {}"),
    "env_yes": ("已启用", "enabled"),
    "env_no": ("未安装/未启用", "missing/disabled"),
    "env_too_old": ("这个 Blender 版本({})太旧,VRM 插件需要 2.93 以上;"
                    "请升级或用\"初始化环境\"下载便携版",
                    "This Blender ({}) is too old; the VRM add-on needs "
                    "2.93+. Upgrade it or download the portable build via "
                    "Set up environment"),
    "env_no_addon": ("这个 Blender 里没有 VRM 插件,无法处理。"
                     "点\"初始化环境\"可自动安装插件(2.93-4.1),"
                     "或下载完整便携版",
                     "This Blender has no VRM add-on. Use Set up "
                     "environment to install it automatically (Blender "
                     "2.93-4.1) or download the portable build"),
    "env_42_hint": ("注意:Blender 4.2+ 需要 Extension 版 VRM 插件,"
                    "本工具无法自动安装;建议用\"初始化环境\"下载便携版 4.0.2",
                    "Note: Blender 4.2+ needs the Extension build of the "
                    "VRM add-on which this tool cannot auto-install; "
                    "recommend the portable 4.0.2 via Set up environment"),
    "env_untested": ("提示:本工具在 Blender 4.0.2 上测试;{} 未经测试,"
                     "如遇问题建议用初始化环境下载 4.0.2 便携版",
                     "Note: this tool is tested on Blender 4.0.2; {} is "
                     "untested. If problems occur, use the portable 4.0.2"),
    "slot_header": ("—— 组合 {}:供体 {},受体 {} 个 ——",
                    "—— Group {}: donor {}, {} recipient(s) ——"),
    "fatal_start": ("[致命错误] 无法启动 Blender: {}",
                    "[FATAL] Could not start Blender: {}"),
    "fatal_slot_start": ("组合 {}: Blender 启动失败",
                         "Group {}: failed to start Blender"),
    "fatal_donor": ("组合 {}: 供体加载失败(往上看红色报错;常见原因:"
                    "该模型没有 52 个表情键不能当供体,或它是 VRM 1.0 模型)",
                    "Group {}: donor failed to load (see the red error "
                    "above; usually the model lacks the 52 ARKit keys, or "
                    "it is a VRM 1.0 model)"),
    "fatal_addon": ("Blender 里似乎没有安装/启用 VRM 插件。"
                    "点\"初始化环境\"自动安装,或在 Blender 的 编辑 → "
                    "偏好设置 → 插件 里启用后再试。",
                    "The VRM add-on seems missing in Blender. Use Set up "
                    "environment to install it, or enable it in Blender's "
                    "Edit → Preferences → Add-ons."),
    "fatal_crash": ("Blender 中途异常退出,请勾选\"显示完整日志\"重跑一次查看原因。",
                    "Blender exited unexpectedly; tick 'Full log' and run "
                    "again to see why."),
    # 完成
    "done_title": ("完成", "Done"),
    "cancelled_title": ("已取消", "Cancelled"),
    "cancelled_body": ("处理被取消,已完成 {} 个模型。",
                       "Processing cancelled; {} model(s) were finished."),
    "problem_title": ("出现问题", "Problems occurred"),
    "partial_title": ("部分失败", "Some failed"),
    "warn_popup_title": ("完成(有警告)", "Done (with warnings)"),
    "totals": ("转移成功 {} 个 / 跳过 {} 个 / 失败 {} 个",
               "{} transferred / {} skipped / {} failed"),
    "saved_to": ("结果保存在:", "Results saved to:"),
    "fail_hint": ("失败的模型请在日志里找红色 [FAIL] 行,后面写了原因"
                  "(最常见:脸的顶点数和供体不一致,不是同一拓扑的 VRoid 脸)。",
                  "For failed models, find the red [FAIL] lines in the log; "
                  "the reason follows (most common: face vertex count "
                  "differs from the donor - not the same VRoid topology)."),
    "skip_hint": ("有 {} 个模型被跳过(已有完美同步表情或是供体)。"
                  "想强制重新转移请勾选\"覆盖模式\"。",
                  "{} model(s) were skipped (already have the keys or are "
                  "donors). Tick 'Overwrite mode' to force re-transfer."),
    "warns_header": ("处理过程中有以下警告:", "Warnings during processing:"),
    "quit_confirm": ("还在处理中,确定要退出吗?(会中断当前处理)",
                     "Still processing - really quit? (This aborts the "
                     "current run)"),
    "confirm": ("确认", "Confirm"),
    "status_done": ("转移 {} / 跳过 {} / 失败 {}",
                    "{} done / {} skipped / {} failed"),
    # 初始化
    "setup_title": ("初始化环境", "Set up environment"),
    "setup_intro": ("给全新电脑准备运行环境。两种方式任选:",
                    "Prepare a fresh machine. Choose either option:"),
    "setup_note": ("自动下载的均为可自由分发的开源软件,来自官方源或其镜像:"
                   "Blender(GPL 协议)、VRM 插件(MIT 协议)。",
                   "Everything downloaded is freely redistributable "
                   "open-source software from official sources or their "
                   "mirrors: Blender (GPL), VRM add-on (MIT)."),
    "setup_paths": ("将安装到: {}\n下载缓存: {}",
                    "Install location: {}\nDownload cache: {}"),
    "setup_loc_label": ("安装位置:", "Install to:"),
    "setup_loc_hint": ("(便携版 Blender 约 1GB 将解压到这里的 runtime 子夹)",
                       "(portable Blender ~1GB will unpack into a runtime "
                       "subfolder here)"),
    "setup_a": ("一键下载便携版 Blender 4.0.2 + VRM 插件\n"
                "(约 400MB,耗时较长,只需一次;与系统里已装的 Blender 互不干扰)",
                "Download portable Blender 4.0.2 + VRM add-on\n"
                "(~400MB, takes a while, one-time; independent from any "
                "installed Blender)"),
    "setup_b": ("为上面选好的已有 Blender 自动安装 VRM 插件\n"
                "(适用于 Blender 2.93-4.1;会写入该 Blender 的用户设置)",
                "Install the VRM add-on into the Blender chosen above\n"
                "(for Blender 2.93-4.1; writes to that Blender's user "
                "preferences)"),
    "setup_check": ("检查当前 Blender", "Check current Blender"),
    "setup_run_a": ("开始下载便携版", "Download portable build"),
    "setup_run_b": ("安装 VRM 插件", "Install VRM add-on"),
    "setup_pick_zip": ("手动选择插件 zip...", "Pick add-on zip manually..."),
    "setup_busy": ("正在执行,请勿关闭窗口...", "Working, do not close..."),
    "dl_try": ("下载 {} (来源 {}/{}): {}",
               "Downloading {} (source {}/{}): {}"),
    "dl_progress": ("  已下载 {}%", "  {}% downloaded"),
    "dl_fail_one": ("  此来源失败: {}", "  This source failed: {}"),
    "dl_fail_all": ("所有下载来源都失败了。可手动下载 {} 放到 {} 后重试;"
                    "或检查网络/代理。",
                    "All download sources failed. You can manually download "
                    "{} into {} and retry, or check your network/proxy."),
    "dl_cached": ("发现已下载的 {},跳过下载", "Found cached {}, skipping "
                  "download"),
    "extracting": ("解压 Blender 中...", "Extracting Blender..."),
    "extract_bad": ("压缩包损坏,已删除,请重试下载",
                    "Corrupt archive; deleted - please retry"),
    "disk_low": ("磁盘空间不足(需要约 1.2GB 可用):{}",
                 "Not enough disk space (~1.2GB needed): {}"),
    "portable_cfg": ("已启用便携配置(不影响系统 Blender 设置)",
                     "Portable config enabled (system Blender unaffected)"),
    "addon_installing": ("安装 VRM 插件到: {}", "Installing VRM add-on "
                         "into: {}"),
    "addon_ok": ("VRM 插件安装并启用成功", "VRM add-on installed and "
                 "enabled"),
    "addon_fail": ("插件安装失败:{}", "Add-on install failed: {}"),
    "setup_done": ("初始化完成!Blender 路径已自动填好,可以关闭本窗口开始使用。",
                   "Setup complete! The Blender path has been filled in - "
                   "close this window and start."),
    "setup_b_needs_blender": ("请先在主窗口选择一个有效的 blender.exe",
                              "First choose a valid blender.exe in the "
                              "main window"),
    "setup_b_42": ("该 Blender 是 {},自动安装仅支持 2.93-4.1;"
                   "请改用便携版方案",
                   "That Blender is {}; auto-install only supports "
                   "2.93-4.1 - use the portable option instead"),
    # 首次启动向导
    "wiz_title": ("首次使用设置", "First-run setup"),
    "wiz_intro": ("本工具需要下面 3 样东西,已自动检测:",
                  "This tool needs these 3 things (auto-detected):"),
    "wiz_python": ("Python 3(运行本界面)", "Python 3 (runs this window)"),
    "wiz_blender": ("Blender(后台处理引擎)",
                    "Blender (background engine)"),
    "wiz_addon": ("VRM 插件(装在 Blender 里)",
                  "VRM add-on (inside Blender)"),
    "wiz_ok": ("✓ 已就绪", "✓ ready"),
    "wiz_missing": ("✗ 缺失", "✗ missing"),
    "wiz_checking": ("检测中...", "checking..."),
    "wiz_dl_size": ("一键补齐需下载约 {}", "about {} to download"),
    "wiz_fix": ("一键补齐缺失项", "Fix missing items now"),
    "wiz_recheck": ("重新检测", "Re-check"),
    "wiz_enter": ("进入主界面", "Enter the tool"),
    "wiz_noshow": ("下次启动不再显示", "Don't show this again"),
    "wiz_all_ok": ("全部就绪,直接开始吧!",
                   "Everything is ready - let's go!"),
}


def find_blender():
    """自动探测 blender.exe:便携版优先,其次 PATH,再扫常见安装目录。"""
    if os.path.isfile(PORTABLE_EXE):
        return PORTABLE_EXE
    w = shutil.which("blender")
    if w:
        return w
    hits = []
    roots = [r"C:\Program Files\Blender Foundation",
             r"D:\Program Files\Blender Foundation",
             os.path.expandvars(
                 r"%LOCALAPPDATA%\Programs\Blender Foundation"),
             os.path.expandvars(r"%ProgramW6432%\Blender Foundation")]
    for root in roots:
        if os.path.isdir(root):
            for d in sorted(os.listdir(root), reverse=True):
                exe = os.path.join(root, d, "blender.exe")
                if os.path.isfile(exe):
                    hits.append(exe)
    return hits[0] if hits else ""


def check_blender(exe):
    """运行一次 Blender,返回 (版本元组, 插件可用, 错误字符串)。"""
    fd, tmp = tempfile.mkstemp(suffix=".py")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(CHECK_PY)
        r = subprocess.run(
            [exe, "--background", "--python", tmp],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120, creationflags=CREATE_NO_WINDOW,
            env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    except Exception as e:
        return None, False, str(e)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    out = (r.stdout or "") + (r.stderr or "")
    mv = re.search(r"^BLVER (\d+)\.(\d+)(?:\.(\d+))?", out, re.M)
    ma = re.search(r"^VRMADDON (\d)", out, re.M)
    if not mv:
        return None, False, out[-400:]
    ver = tuple(int(x or 0) for x in mv.groups())
    return ver, bool(ma and ma.group(1) == "1"), ""


class Slot(ttk.LabelFrame):
    """一个组合:左侧 1 个供体,右侧 n 个受体。"""

    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        self.donor_var = tk.StringVar()

        left = ttk.Frame(self)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        self.lb_donor = ttk.Label(left)
        self.lb_donor.pack(anchor="w")
        # 上行:文件名(正常字体,蓝色区分);下行:完整路径只读框 + 横向滚动条
        self.donor_name_var = tk.StringVar(value="—")
        self.lb_donor_name = ttk.Label(
            left, textvariable=self.donor_name_var, foreground="#0b5394")
        self.lb_donor_name.pack(anchor="w", fill="x")
        path_row = ttk.Frame(left)
        path_row.pack(anchor="w", fill="x", pady=(0, 2))
        self.donor_path_entry = ttk.Entry(
            path_row, textvariable=self.donor_var, width=38,
            state="readonly", foreground="#666666")
        self.donor_path_entry.pack(fill="x")
        hsb = ttk.Scrollbar(path_row, orient="horizontal",
                            command=self.donor_path_entry.xview)
        self.donor_path_entry.configure(xscrollcommand=hsb.set)
        hsb.pack(fill="x")
        self.donor_var.trace_add("write", self._donor_changed)
        self.bt_pick = ttk.Button(left, command=self.pick_donor)
        self.bt_pick.pack(anchor="w")
        self.bt_del = ttk.Button(
            left, command=lambda: self.app.remove_slot(self))
        self.bt_del.pack(anchor="w", pady=(18, 0))

        right = ttk.Frame(self)
        right.grid(row=0, column=1, sticky="nsew")
        self.columnconfigure(1, weight=1)
        self.lb_recip = ttk.Label(right)
        self.lb_recip.pack(anchor="w")
        box_row = ttk.Frame(right)
        box_row.pack(fill="both", expand=True, pady=2)
        self.listbox = tk.Listbox(box_row, height=5, selectmode="extended")
        sb = ttk.Scrollbar(box_row, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        btns = ttk.Frame(right)
        btns.pack(anchor="w")
        self.bt_add = ttk.Button(btns, command=self.add_recipients)
        self.bt_add.pack(side="left")
        self.bt_rm = ttk.Button(btns, command=self.remove_selected)
        self.bt_rm.pack(side="left", padx=6)
        self.apply_lang()

    def _donor_changed(self, *_):
        p = self.donor_var.get()
        self.donor_name_var.set(os.path.basename(p) if p else "—")
        # 让只读框显示到路径末尾(文件名端),而非停在开头
        self.donor_path_entry.xview_moveto(1.0)

    def apply_lang(self):
        t = self.app.t
        self.lb_donor.configure(text=t("donor_label"))
        self.bt_pick.configure(text=t("pick_donor"))
        self.bt_del.configure(text=t("del_slot"))
        self.lb_recip.configure(text=t("recip_label"))
        self.bt_add.configure(text=t("add_recip"))
        self.bt_rm.configure(text=t("remove_sel"))

    def pick_donor(self):
        t = self.app.t
        p = filedialog.askopenfilename(
            title=t("dlg_donor"),
            filetypes=[(t("vrm_filter"), "*.vrm")])
        if p:
            if p in self.recipients():
                messagebox.showwarning(t("hint"), t("donor_in_recips"))
                return
            self.donor_var.set(p)

    def add_recipients(self):
        t = self.app.t
        paths = filedialog.askopenfilenames(
            title=t("dlg_recips"),
            filetypes=[(t("vrm_filter"), "*.vrm")])
        existing = set(self.recipients())
        for p in paths:
            if p == self.donor_var.get():
                messagebox.showwarning(
                    t("hint"),
                    t("recip_is_donor").format(os.path.basename(p)))
                continue
            if p not in existing:
                self.listbox.insert("end", p)
                existing.add(p)

    def remove_selected(self):
        for i in reversed(self.listbox.curselection()):
            self.listbox.delete(i)

    def recipients(self):
        return list(self.listbox.get(0, "end"))


class App(tk.Tk):
    def __init__(self, scale=1.0):
        super().__init__()
        self.scale = scale
        # DPI 清晰化:进程已声明 DPI-aware(真实像素渲染),这里把 Tk 的
        # 缩放系数(每点像素数)设为真实 DPI 对应值,点数字体即按屏幕 DPI
        # 正确放大。不手动改各内置字体的 size(其可能以像素为单位,乱改会
        # 破坏语义);tk scaling 是标准且安全的做法。
        try:
            self.tk.call("tk", "scaling", scale * 96.0 / 72.0)
        except Exception:
            pass
        self._px = lambda v: int(round(v * scale))
        self.geometry("%dx%d" % (self._px(900), self._px(800)))
        self.minsize(self._px(780), self._px(640))
        self.slots = []
        self.proc = None
        self.cancelled = False
        self.q = queue.Queue()
        self.env_cache = {}
        self.warn_lines = []
        self.i18n = []  # (widget, key)

        cfg = self._read_config()
        self._cfg = cfg
        # 默认英文(全球通用),中文用户首启向导里可切换
        self.lang_var = tk.StringVar(
            value="中文" if cfg.get("lang") == "zh" else "English")

        pad = {"padx": 10, "pady": 4}

        # --- 顶栏:语言 + Blender 路径 ---
        row = ttk.Frame(self)
        row.pack(fill="x", **pad)
        self.lb_lang = ttk.Label(row)
        self.lb_lang.pack(side="left")
        cb = ttk.Combobox(row, textvariable=self.lang_var, width=8,
                          state="readonly", values=("中文", "English"))
        cb.pack(side="left", padx=(4, 16))
        cb.bind("<<ComboboxSelected>>", lambda e: self.apply_lang())
        self.lb_blender = ttk.Label(row)
        self.lb_blender.pack(side="left")
        self.blender_var = tk.StringVar(
            value=cfg.get("blender") if cfg.get("blender")
            and os.path.isfile(cfg.get("blender")) else find_blender())
        ttk.Entry(row, textvariable=self.blender_var).pack(
            side="left", fill="x", expand=True, padx=6)
        self.bt_browse = ttk.Button(row, command=self.pick_blender)
        self.bt_browse.pack(side="left")
        self.bt_setup = ttk.Button(row, command=self.open_setup)
        self.bt_setup.pack(side="left", padx=(6, 0))

        # --- VRM0 提示 ---
        self.lb_vrm0 = tk.Label(self, anchor="w", fg="#b26a00")
        self.lb_vrm0.pack(fill="x", padx=10)

        # --- 组合区(可滚动 + 鼠标滚轮) ---
        holder = ttk.Frame(self)
        holder.pack(fill="both", expand=False, **pad)
        self.canvas = tk.Canvas(holder, height=self._px(280),
                                highlightthickness=0)
        vsb = ttk.Scrollbar(holder, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")
        self.slot_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.slot_frame,
                                  anchor="nw", tags="inner")
        self.slot_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")))
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure("inner", width=e.width))
        # 鼠标滚轮:指针进入组合区时接管滚动(列表框上让列表自己滚)
        self.canvas.bind("<Enter>", lambda e: self.bind_all(
            "<MouseWheel>", self._on_wheel))
        self.canvas.bind("<Leave>", lambda e: self.unbind_all("<MouseWheel>"))

        self.bt_add_slot = ttk.Button(self, command=self.add_slot)
        self.bt_add_slot.pack(anchor="w", padx=10)

        # --- 输出设置 ---
        row = ttk.Frame(self)
        row.pack(fill="x", **pad)
        self.lb_out = ttk.Label(row)
        self.lb_out.pack(side="left")
        self.out_var = tk.StringVar(value=cfg.get("output", ""))
        ttk.Entry(row, textvariable=self.out_var).pack(
            side="left", fill="x", expand=True, padx=6)
        self.bt_out = ttk.Button(row, command=self.pick_out)
        self.bt_out.pack(side="left")
        self.lb_suffix = ttk.Label(row)
        self.lb_suffix.pack(side="left")
        self.suffix_var = tk.StringVar(value=cfg.get("suffix", "_ps"))
        ttk.Entry(row, textvariable=self.suffix_var, width=10).pack(
            side="left")

        row = ttk.Frame(self)
        row.pack(fill="x", **pad)
        self.overwrite_var = tk.BooleanVar(value=False)
        self.ck_overwrite = ttk.Checkbutton(row,
                                            variable=self.overwrite_var)
        self.ck_overwrite.pack(side="left")
        self.fulllog_var = tk.BooleanVar(value=False)
        self.ck_fulllog = ttk.Checkbutton(row, variable=self.fulllog_var)
        self.ck_fulllog.pack(side="right")
        # 模式高亮徽标(始终可见,不靠日志)
        self.lb_mode = tk.Label(self, anchor="w", font=("", 9, "bold"))
        self.lb_mode.pack(fill="x", padx=10)
        self.overwrite_var.trace_add(
            "write", lambda *_: self._update_mode_badge())

        # --- 运行控制 ---
        row = ttk.Frame(self)
        row.pack(fill="x", **pad)
        self.start_btn = ttk.Button(row, command=self.start)
        self.start_btn.pack(side="left")
        self.cancel_btn = ttk.Button(row, state="disabled",
                                     command=self.cancel)
        self.cancel_btn.pack(side="left", padx=6)
        self.open_btn = ttk.Button(row, state="disabled",
                                   command=self.open_out)
        self.open_btn.pack(side="left", padx=6)
        self.bar = ttk.Progressbar(row, mode="indeterminate", length=160)
        self.bar.pack(side="left", padx=10)
        self.status_var = tk.StringVar()
        ttk.Label(row, textvariable=self.status_var).pack(side="left")

        # --- 日志 ---
        self.log = ScrolledText(self, height=14, state="disabled",
                                font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log.tag_configure("ok", foreground="#1a7f37")
        self.log.tag_configure("fail", foreground="#c62828")
        self.log.tag_configure("skip", foreground="#888888")
        self.log.tag_configure("warn", foreground="#b26a00")
        self.log.tag_configure("info", foreground="#0b5394")

        self.add_slot()
        self.apply_lang()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self.pump)

    # ---------------- 语言 ----------------

    def lang(self):
        return "en" if self.lang_var.get() == "English" else "zh"

    def t(self, key, *fmt):
        s = TEXT[key][1 if self.lang() == "en" else 0]
        return s.format(*fmt) if fmt else s

    def apply_lang(self):
        self.title(self.t("title"))
        self.lb_lang.configure(text=self.t("lang_label"))
        self.lb_vrm0.configure(text=self.t("vrm0_hint"))
        self.lb_blender.configure(text=self.t("blender_loc"))
        self.bt_browse.configure(text=self.t("browse"))
        self.bt_setup.configure(text=self.t("setup_btn"))
        self.bt_add_slot.configure(text=self.t("add_slot"))
        self.lb_out.configure(text=self.t("out_label"))
        self.bt_out.configure(text=self.t("browse"))
        self.lb_suffix.configure(text=self.t("suffix_label"))
        self.ck_overwrite.configure(text=self.t("overwrite_chk"))
        self.ck_fulllog.configure(text=self.t("fulllog_chk"))
        self.start_btn.configure(text=self.t("start"))
        self.cancel_btn.configure(text=self.t("cancel"))
        self.open_btn.configure(text=self.t("open_out"))
        self._update_mode_badge()
        if not self.status_var.get() or self.status_var.get() in (
                TEXT["ready"][0], TEXT["ready"][1]):
            self.status_var.set(self.t("ready"))
        for s in self.slots:
            s.apply_lang()
        self.renumber()

    def _update_mode_badge(self):
        if self.overwrite_var.get():
            self.lb_mode.configure(text=self.t("mode_badge_overwrite"),
                                   fg="#c62828")
        else:
            self.lb_mode.configure(text=self.t("mode_badge_normal"),
                                   fg="#0b5394")

    # ---------------- 组合管理 ----------------

    def add_slot(self):
        s = Slot(self.slot_frame, self)
        s.pack(fill="x", pady=4, padx=2)
        self.slots.append(s)
        self.renumber()

    def remove_slot(self, slot):
        if len(self.slots) == 1:
            messagebox.showinfo(self.t("hint"), self.t("min_one_slot"))
            return
        slot.destroy()
        self.slots.remove(slot)
        self.renumber()

    def renumber(self):
        for i, s in enumerate(self.slots, 1):
            s.configure(text=self.t("slot_title", i))

    def _on_wheel(self, e):
        w = self.winfo_containing(e.x_root, e.y_root)
        if isinstance(w, tk.Listbox):
            return  # 列表框自己滚
        self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")

    # ---------------- 选择器 ----------------

    def pick_blender(self):
        p = filedialog.askopenfilename(
            title=self.t("dlg_blender"),
            filetypes=[("Blender", "blender.exe"), ("exe", "*.exe")])
        if p:
            self.blender_var.set(p)

    def pick_out(self):
        p = filedialog.askdirectory(title=self.t("dlg_out"))
        if p:
            self.out_var.set(p)

    def open_out(self):
        out = self.out_var.get().strip()
        if out and os.path.isdir(out):
            os.startfile(out)

    # ---------------- 校验 ----------------

    def validate(self):
        t = self.t
        problems = []
        blender = self.blender_var.get().strip()
        if not blender:
            problems.append(t("v_no_blender"))
        elif not os.path.isfile(blender):
            problems.append(t("v_blender_missing", blender))
        if not os.path.isfile(BATCH_SCRIPT):
            problems.append(t("v_no_batch"))

        out = self.out_var.get().strip()
        if not out:
            problems.append(t("v_no_out"))
        else:
            parent = out
            while parent and not os.path.exists(parent):
                parent = os.path.dirname(parent)
            if not parent or not os.path.isdir(parent):
                problems.append(t("v_bad_out", out))

        suffix = self.suffix_var.get().strip()
        if re.search(r'[<>:"/\\|?*]', suffix):
            problems.append(t("v_bad_suffix"))

        jobs = []
        donors = {}      # path -> slot no
        recipients = {}  # path -> slot no
        for i, s in enumerate(self.slots, 1):
            donor = s.donor_var.get().strip()
            recs = s.recipients()
            if not donor and not recs:
                continue  # 完全空的组合忽略
            if not donor:
                problems.append(t("v_slot_no_donor", i))
                continue
            if not os.path.isfile(donor):
                problems.append(t("v_donor_missing", i, donor))
                continue
            if not recs:
                problems.append(t("v_slot_no_recip", i))
                continue
            donors[os.path.abspath(donor)] = i
            ok_recs = []
            for r in recs:
                if not os.path.isfile(r):
                    problems.append(t("v_recip_missing", i, r))
                    continue
                ar = os.path.abspath(r)
                if ar in recipients:
                    problems.append(t("v_dup_recip",
                                      os.path.basename(r),
                                      recipients[ar], i))
                recipients[ar] = i
                if out and suffix == "" and \
                        os.path.dirname(ar) == os.path.abspath(out):
                    problems.append(t("v_overwrite_src",
                                      os.path.basename(r)))
                ok_recs.append(r)
            if ok_recs:
                jobs.append((i, donor, ok_recs))

        # 跨组合:一边当供体一边当受体
        for ar, ri in recipients.items():
            if ar in donors:
                problems.append(t("v_donor_as_recip",
                                  os.path.basename(ar), donors[ar], ri))

        # 跨组合重名(输出互相覆盖)
        base_seen = {}
        for ar in recipients:
            b = os.path.basename(ar).lower()
            if b in base_seen and base_seen[b] != ar:
                problems.append(t("v_same_name", os.path.basename(ar)))
            base_seen[b] = ar

        if not jobs and not problems:
            problems.append(t("v_nothing"))
        return problems, jobs

    # ---------------- 运行 ----------------

    def start(self):
        problems, jobs = self.validate()
        if problems:
            messagebox.showerror(
                self.t("fix_first"),
                "\n".join("• " + p for p in problems))
            return
        self.jobs = jobs
        self.totals = [0, 0, 0]
        self.fatal = []
        self.warn_lines = []
        self.cancelled = False
        self.start_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.open_btn.configure(state="disabled")
        self.bar.start(12)
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        # 模式提醒(第 3 条反馈)
        key = "mode_overwrite" if self.overwrite_var.get() else "mode_normal"
        self.q.put(("line", self.t(key), "info"))
        threading.Thread(target=self.worker, daemon=True).start()

    def _env_ok(self, blender):
        """环境预检:版本 + VRM 插件。返回 True 才继续。"""
        t = self.t
        key = (blender, os.path.getmtime(blender))
        if key not in self.env_cache:
            self.q.put(("line", t("checking_env"), "info"))
            self.env_cache[key] = check_blender(blender)
        ver, addon, err = self.env_cache[key]
        if ver is None:
            self.q.put(("line", t("env_fail_run", err), "fail"))
            self.fatal.append(t("env_fail_run", err))
            return False
        vs = "%d.%d.%d" % ver
        self.q.put(("line", t("env_ver", vs,
                              t("env_yes") if addon else t("env_no")),
                    "info"))
        if ver < (2, 93):
            self.q.put(("line", t("env_too_old", vs), "fail"))
            self.fatal.append(t("env_too_old", vs))
            return False
        if not addon:
            msg = t("env_no_addon")
            if ver >= (4, 2):
                msg += "\n" + t("env_42_hint")
            self.q.put(("line", msg, "fail"))
            self.fatal.append(msg)
            return False
        if ver >= (4, 2) or ver < (3, 0):
            self.q.put(("line", t("env_untested", vs), "warn"))
        return True

    def worker(self):
        t = self.t
        blender = self.blender_var.get().strip()
        out = self.out_var.get().strip()
        suffix = self.suffix_var.get().strip()
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        if not self._env_ok(blender):
            self.q.put(("done", None, None))
            return
        for slot_no, donor, recs in self.jobs:
            if self.cancelled:
                break
            self.q.put(("line", t("slot_header", slot_no,
                                  os.path.basename(donor), len(recs)),
                        "info"))
            fd, report = tempfile.mkstemp(suffix=".json")
            os.close(fd)
            cmd = [blender, "--background", "--python", BATCH_SCRIPT, "--",
                   "--donor", donor, "--output", out, "--suffix", suffix,
                   "--lang", self.lang(), "--report", report]
            for r in recs:
                cmd += ["--target", r]
            if self.overwrite_var.get():
                cmd.append("--overwrite")
            marker = None
            tail = []
            try:
                self.proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    encoding="utf-8", errors="replace", env=env,
                    creationflags=CREATE_NO_WINDOW)
            except OSError as e:
                self.q.put(("line", t("fatal_start", e), "fail"))
                self.fatal.append(t("fatal_slot_start", slot_no))
                os.remove(report)
                continue
            for line in self.proc.stdout:
                line = line.rstrip("\r\n")
                tail.append(line)
                if len(tail) > 60:
                    tail.pop(0)
                m = RESULT_RE.search(line)
                if m:
                    marker = tuple(map(int, m.groups()))
                    continue
                self.q.put(("raw", line, None))
            self.proc.wait()

            # 结果优先读 JSON 报告(与日志措辞/语言解耦);标记行兜底
            data = None
            try:
                if os.path.getsize(report) > 0:
                    with open(report, encoding="utf-8") as f:
                        data = json.load(f)
            except Exception:
                data = None
            finally:
                try:
                    os.remove(report)
                except OSError:
                    pass

            if data is not None and "fatal" in data:
                self.fatal.append(t("fatal_donor", slot_no))
            elif data is not None:
                self.totals[0] += data.get("ok", 0)
                self.totals[1] += data.get("skip", 0)
                self.totals[2] += data.get("fail", 0)
                self.warn_lines.extend(data.get("warnings", []))
            elif marker is not None:
                ok, sk, fl = marker
                if fl == -1:
                    self.fatal.append(t("fatal_donor", slot_no))
                else:
                    self.totals[0] += ok
                    self.totals[1] += sk
                    self.totals[2] += fl
            elif not self.cancelled:
                joined = "\n".join(tail)
                if "import_scene" in joined and "vrm" in joined.lower():
                    hint = t("fatal_addon")
                else:
                    hint = t("fatal_crash")
                self.fatal.append("Group %d: %s" % (slot_no, hint)
                                  if self.lang() == "en"
                                  else "组合 %d: %s" % (slot_no, hint))
                self.q.put(("line", "[FATAL] " + hint, "fail"))
        self.q.put(("done", None, None))

    def cancel(self):
        self.cancelled = True
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.status_var.set(self.t("cancelling"))

    # ---------------- 日志泵 ----------------

    def pump(self):
        try:
            while True:
                kind, text, tag = self.q.get_nowait()
                if kind == "done":
                    self.finish()
                    continue
                if kind == "raw":
                    if not self.fulllog_var.get() and NOISE_RE.search(text):
                        continue
                    tag = None
                    if text.startswith("[FAIL]") or "致命错误" in text \
                            or "[FATAL]" in text:
                        tag = "fail"
                    elif text.startswith("[OK"):
                        tag = "ok"
                    elif text.startswith("[SKIP"):
                        tag = "skip"
                    elif "[warn]" in text or text.startswith("警告") \
                            or text.startswith("Warning"):
                        # 只染色显示;弹窗警告改由 JSON 报告提供
                        # (仅含本工具的重要警告,不混入 Blender 噪音)
                        tag = "warn"
                self.log.configure(state="normal")
                self.log.insert("end", text + "\n", tag or ())
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self.pump)

    def finish(self):
        t = self.t
        self.bar.stop()
        self.start_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        ok, sk, fl = self.totals
        if self.cancelled:
            self.status_var.set(t("cancelled_title"))
            messagebox.showinfo(t("cancelled_title"),
                                t("cancelled_body", ok))
            return
        totals = t("totals", ok, sk, fl)
        self.status_var.set(t("status_done", ok, sk, fl))
        if ok > 0:
            self.open_btn.configure(state="normal")

        extra = []
        if sk > 0 and not self.overwrite_var.get():
            extra.append(t("skip_hint", sk))
        if self.warn_lines:  # 第 5 条反馈:警告并入完成弹窗
            shown = self.warn_lines[:12]
            if len(self.warn_lines) > 12:
                shown.append("... (+%d)" % (len(self.warn_lines) - 12))
            extra.append(t("warns_header") + "\n" + "\n".join(shown))

        body = totals
        if extra:
            body += "\n\n" + "\n\n".join(extra)
        if self.fatal:
            messagebox.showerror(t("problem_title"),
                                 body + "\n\n" + "\n".join(self.fatal))
        elif fl > 0:
            messagebox.showwarning(t("partial_title"),
                                   body + "\n\n" + t("fail_hint"))
        elif self.warn_lines:
            messagebox.showwarning(t("warn_popup_title"), body)
        else:
            messagebox.showinfo(
                t("done_title"),
                body + "\n\n" + t("saved_to") + "\n" + self.out_var.get())

    # ---------------- 初始化环境 ----------------

    def open_setup(self):
        SetupDialog(self)

    # ---------------- 配置 ----------------

    def _read_config(self):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_config(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({"blender": self.blender_var.get(),
                           "output": self.out_var.get(),
                           "suffix": self.suffix_var.get(),
                           "lang": self.lang(),
                           "install_dir": self._cfg.get("install_dir"),
                           "wizard_done": bool(
                               self._cfg.get("wizard_done"))},
                          f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def on_close(self):
        self.save_config()
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno(self.t("confirm"),
                                       self.t("quit_confirm")):
                return
            self.proc.terminate()
        self.destroy()


class SetupDialog(tk.Toplevel):
    """初始化环境:下载便携版 Blender + VRM 插件,或给已有 Blender 装插件。"""

    def __init__(self, app, auto=None):
        super().__init__(app)
        self.app = app
        t = app.t
        self.title(t("setup_title"))
        px = app._px
        self.geometry("%dx%d" % (px(680), px(560)))
        self.busy = False
        self.cancelled = False
        self.q = queue.Queue()
        # 安装根目录(可自选);默认工具目录,记忆在配置里
        self.base_var = tk.StringVar(
            value=app._cfg.get("install_dir") or SCRIPT_DIR)

        ttk.Label(self, text=t("setup_intro")).pack(anchor="w",
                                                    padx=12, pady=(10, 2))
        ttk.Label(self, text=t("setup_note"), justify="left",
                  foreground="#888888", wraplength=px(640)).pack(
            anchor="w", padx=12, pady=(0, 4))

        loc = ttk.Frame(self)
        loc.pack(fill="x", padx=12, pady=(2, 0))
        ttk.Label(loc, text=t("setup_loc_label")).pack(side="left")
        ttk.Entry(loc, textvariable=self.base_var).pack(
            side="left", fill="x", expand=True, padx=6)
        ttk.Button(loc, text=t("browse"),
                   command=self.pick_base).pack(side="left")
        ttk.Label(self, text=t("setup_loc_hint"), foreground="#888888").pack(
            anchor="w", padx=12, pady=(0, 4))

        fa = ttk.LabelFrame(self, text="A", padding=8)
        fa.pack(fill="x", padx=12, pady=4)
        ttk.Label(fa, text=t("setup_a"), justify="left").pack(anchor="w")
        self.bt_a = ttk.Button(fa, text=t("setup_run_a"),
                               command=self.run_portable)
        self.bt_a.pack(anchor="w", pady=4)

        fb = ttk.LabelFrame(self, text="B", padding=8)
        fb.pack(fill="x", padx=12, pady=4)
        ttk.Label(fb, text=t("setup_b"), justify="left").pack(anchor="w")
        rowb = ttk.Frame(fb)
        rowb.pack(anchor="w", pady=4)
        self.bt_b = ttk.Button(rowb, text=t("setup_run_b"),
                               command=lambda: self.run_addon(None))
        self.bt_b.pack(side="left")
        self.bt_zip = ttk.Button(rowb, text=t("setup_pick_zip"),
                                 command=self.pick_zip)
        self.bt_zip.pack(side="left", padx=6)
        self.bt_check = ttk.Button(rowb, text=t("setup_check"),
                                   command=self.run_check)
        self.bt_check.pack(side="left", padx=6)

        self.log = ScrolledText(self, height=10, state="disabled",
                                font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self.log.tag_configure("fail", foreground="#c62828")
        self.log.tag_configure("ok", foreground="#1a7f37")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self.pump)
        if auto == "portable":
            self.after(300, self.run_portable)
        elif auto == "addon":
            self.after(300, lambda: self.run_addon(None))

    # ---- 基础 ----

    def on_close(self):
        if self.busy:
            messagebox.showwarning(self.app.t("hint"),
                                   self.app.t("setup_busy"), parent=self)
            return
        self.destroy()

    def pick_base(self):
        p = filedialog.askdirectory(parent=self,
                                    initialdir=self.base_var.get())
        if p:
            self.base_var.set(p)

    # 从自选根目录计算各路径(默认工具目录 → 与旧的 runtime\ 一致)
    def _runtime_dir(self):
        return os.path.join(self.base_var.get().strip() or SCRIPT_DIR,
                            "runtime")

    def _dl_dir(self):
        return os.path.join(self._runtime_dir(), "downloads")

    def _portable_exe(self):
        return os.path.join(self._runtime_dir(), BLENDER_DIRNAME,
                            "blender.exe")

    def say(self, text, tag=None):
        self.q.put((text, tag))

    def pump(self):
        try:
            while True:
                text, tag = self.q.get_nowait()
                self.log.configure(state="normal")
                self.log.insert("end", text + "\n", tag or ())
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self.pump)

    def _set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for b in (self.bt_a, self.bt_b, self.bt_zip, self.bt_check):
            b.configure(state=state)

    def _thread(self, fn, *a):
        if self.busy:
            return
        self._set_busy(True)

        def run():
            try:
                fn(*a)
            except Exception as e:
                self.say(str(e), "fail")
            finally:
                self.after(0, lambda: self._set_busy(False))
        threading.Thread(target=run, daemon=True).start()

    # ---- 下载 ----

    def download(self, urls, dest, display):
        t = self.app.t
        if os.path.isfile(dest) and os.path.getsize(dest) > 1024 * 1024:
            self.say(t("dl_cached", display))
            return dest
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        last_err = None
        for i, url in enumerate(urls, 1):
            self.say(t("dl_try", display, i, len(urls), url))
            tmp = dest + ".part"
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=60) as resp, \
                        open(tmp, "wb") as f:
                    total = int(resp.headers.get("Content-Length") or 0)
                    done = 0
                    last_pct = -10
                    while True:
                        chunk = resp.read(1024 * 512)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        if total:
                            pct = done * 100 // total
                            if pct >= last_pct + 10:
                                last_pct = pct
                                self.say(t("dl_progress", pct))
                os.replace(tmp, dest)
                return dest
            except Exception as e:
                last_err = e
                self.say(t("dl_fail_one", e), "fail")
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        raise RuntimeError(t("dl_fail_all", display, os.path.dirname(dest))
                           + " (%s)" % last_err)

    # ---- 方案 A:便携版 ----

    def run_portable(self):
        self._thread(self._portable)

    def _portable(self):
        t = self.app.t
        runtime = self._runtime_dir()
        dl_dir = self._dl_dir()
        portable_exe = self._portable_exe()
        blender_home = os.path.join(runtime, BLENDER_DIRNAME)
        self.say(t("setup_paths", blender_home, dl_dir))
        base = self.base_var.get().strip() or SCRIPT_DIR
        try:
            os.makedirs(base, exist_ok=True)
        except OSError as e:
            raise RuntimeError(str(e))
        free = shutil.disk_usage(base).free
        if free < 1.2 * 1024 ** 3:
            raise RuntimeError(t("disk_low", base))
        # 记住安装位置,下次 find_blender 能直接命中
        self.app._cfg["install_dir"] = base
        zip_path = self.download(
            blender_urls(), os.path.join(dl_dir, BLENDER_ZIP), "Blender")
        if not os.path.isfile(portable_exe):
            self.say(t("extracting"))
            try:
                with zipfile.ZipFile(zip_path) as z:
                    z.extractall(runtime)
            except zipfile.BadZipFile:
                os.remove(zip_path)
                raise RuntimeError(t("extract_bad"))
        # 便携配置目录:设置只写在解压目录里,不碰系统 Blender
        os.makedirs(os.path.join(blender_home, "4.0", "config"),
                    exist_ok=True)
        self.say(t("portable_cfg"))
        addon_zip = self.download(
            addon_urls(), os.path.join(dl_dir, ADDON_ZIP), "VRM add-on")
        self._install_addon(portable_exe, addon_zip)
        self.app.blender_var.set(portable_exe)
        self.app.save_config()
        self.say(t("setup_done"), "ok")

    # ---- 方案 B:给已有 Blender 装插件 ----

    def run_addon(self, zip_path):
        self._thread(self._addon, zip_path)

    def pick_zip(self):
        p = filedialog.askopenfilename(
            parent=self, filetypes=[("zip", "*.zip")])
        if p:
            self.run_addon(p)

    def _addon(self, zip_path):
        t = self.app.t
        exe = self.app.blender_var.get().strip()
        if not exe or not os.path.isfile(exe):
            raise RuntimeError(t("setup_b_needs_blender"))
        ver, addon, err = check_blender(exe)
        if ver is None:
            raise RuntimeError(t("env_fail_run", err))
        vs = "%d.%d.%d" % ver
        if ver < (2, 93) or ver >= (4, 2):
            raise RuntimeError(t("setup_b_42", vs))
        if zip_path is None:
            zip_path = self.download(
                addon_urls(), os.path.join(self._dl_dir(), ADDON_ZIP),
                "VRM add-on")
        self._install_addon(exe, zip_path)
        self.say(t("setup_done"), "ok")

    def _install_addon(self, exe, zip_path):
        t = self.app.t
        self.say(t("addon_installing", exe))
        fd, tmp = tempfile.mkstemp(suffix=".py")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(INSTALL_ADDON_PY)
            r = subprocess.run(
                [exe, "--background", "--python", tmp, "--", zip_path],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=300,
                creationflags=CREATE_NO_WINDOW,
                env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        out = (r.stdout or "") + (r.stderr or "")
        if "ADDON_INSTALL_OK" not in out:
            tail = "\n".join(out.strip().splitlines()[-8:])
            raise RuntimeError(t("addon_fail", tail))
        self.say(t("addon_ok"), "ok")
        self.app.env_cache.clear()

    # ---- 检查 ----

    def run_check(self):
        self._thread(self._check)

    def _check(self):
        t = self.app.t
        exe = self.app.blender_var.get().strip()
        if not exe or not os.path.isfile(exe):
            raise RuntimeError(t("setup_b_needs_blender"))
        ver, addon, err = check_blender(exe)
        if ver is None:
            raise RuntimeError(t("env_fail_run", err))
        vs = "%d.%d.%d" % ver
        self.say(t("env_ver", vs,
                   t("env_yes") if addon else t("env_no")),
                 "ok" if addon else "fail")
        if not addon and ver >= (4, 2):
            self.say(t("env_42_hint"), "fail")


class Wizard(tk.Toplevel):
    """首次启动向导:选语言 + 自动检测三项依赖 + 一键补齐。"""

    def __init__(self, app, detect=True):
        super().__init__(app)
        self.app = app
        self.transient(app)
        self.resizable(False, False)
        self.status = {"blender": None, "addon": None}  # None = 检测中
        self.noshow_var = tk.BooleanVar(value=True)

        pad = {"padx": 14, "pady": 4}
        row = ttk.Frame(self)
        row.pack(fill="x", **pad)
        self.lb_lang = ttk.Label(row)
        self.lb_lang.pack(side="left")
        cb = ttk.Combobox(row, textvariable=app.lang_var, width=8,
                          state="readonly", values=("中文", "English"))
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>",
                lambda e: (app.apply_lang(), self.relabel()))

        self.lb_intro = ttk.Label(self)
        self.lb_intro.pack(anchor="w", **pad)

        grid = ttk.Frame(self)
        grid.pack(fill="x", padx=24, pady=2)
        self.dep_name = {}
        self.dep_stat = {}
        for i, key in enumerate(("python", "blender", "addon")):
            self.dep_name[key] = ttk.Label(grid)
            self.dep_name[key].grid(row=i, column=0, sticky="w", pady=2)
            self.dep_stat[key] = tk.Label(grid)
            self.dep_stat[key].grid(row=i, column=1, sticky="w", padx=12)

        self.lb_size = ttk.Label(self, foreground="#0b5394")
        self.lb_size.pack(anchor="w", **pad)

        row = ttk.Frame(self)
        row.pack(fill="x", **pad)
        self.bt_fix = ttk.Button(row, command=self.fix, state="disabled")
        self.bt_fix.pack(side="left")
        self.bt_recheck = ttk.Button(row, command=self.refresh)
        self.bt_recheck.pack(side="left", padx=6)
        self.bt_enter = ttk.Button(row, command=self.close)
        self.bt_enter.pack(side="right")
        self.ck_noshow = ttk.Checkbutton(self, variable=self.noshow_var)
        self.ck_noshow.pack(anchor="w", padx=14, pady=(0, 12))

        self.relabel()
        self.protocol("WM_DELETE_WINDOW", self.close)
        if detect:
            self.refresh()

    def relabel(self):
        t = self.app.t
        self.title(t("wiz_title"))
        self.lb_lang.configure(text=t("lang_label"))
        self.lb_intro.configure(text=t("wiz_intro"))
        self.dep_name["python"].configure(text=t("wiz_python"))
        self.dep_name["blender"].configure(text=t("wiz_blender"))
        self.dep_name["addon"].configure(text=t("wiz_addon"))
        self.bt_fix.configure(text=t("wiz_fix"))
        self.bt_recheck.configure(text=t("wiz_recheck"))
        self.bt_enter.configure(text=t("wiz_enter"))
        self.ck_noshow.configure(text=t("wiz_noshow"))
        self.render()

    def refresh(self):
        self.status = {"blender": None, "addon": None}
        self.render()
        threading.Thread(target=self._detect, daemon=True).start()

    def _detect(self):
        exe = self.app.blender_var.get().strip() or find_blender()
        blender_ok = bool(exe and os.path.isfile(exe))
        addon_ok = False
        if blender_ok:
            self.app.blender_var.set(exe)
            ver, addon_ok, _ = check_blender(exe)
            if ver is None:
                blender_ok = False
        self.status = {"blender": blender_ok, "addon": addon_ok}
        if self.winfo_exists():
            self.after(0, self.render)

    def render(self):
        if not self.winfo_exists():
            return
        t = self.app.t
        self.dep_stat["python"].configure(text=t("wiz_ok"),
                                          fg="#1a7f37")
        for key in ("blender", "addon"):
            st = self.status.get(key)
            if st is None:
                self.dep_stat[key].configure(text=t("wiz_checking"),
                                             fg="#888888")
            elif st:
                self.dep_stat[key].configure(text=t("wiz_ok"),
                                             fg="#1a7f37")
            else:
                self.dep_stat[key].configure(text=t("wiz_missing"),
                                             fg="#c62828")
        checking = None in self.status.values()
        missing_blender = self.status.get("blender") is False
        missing_addon = self.status.get("addon") is False
        if checking:
            self.lb_size.configure(text="")
            self.bt_fix.configure(state="disabled")
        elif missing_blender:
            self.lb_size.configure(text=t("wiz_dl_size", "400 MB"))
            self.bt_fix.configure(state="normal")
        elif missing_addon:
            self.lb_size.configure(text=t("wiz_dl_size", "15 MB"))
            self.bt_fix.configure(state="normal")
        else:
            self.lb_size.configure(text=t("wiz_all_ok"))
            self.bt_fix.configure(state="disabled")

    def fix(self):
        auto = ("portable" if self.status.get("blender") is False
                else "addon")
        self.close()
        SetupDialog(self.app, auto=auto)

    def close(self):
        self.app._cfg["wizard_done"] = bool(self.noshow_var.get())
        self.app.save_config()
        self.destroy()


if __name__ == "__main__":
    _scale = enable_dpi_awareness()  # 必须在创建 Tk 窗口之前
    app = App(scale=_scale)
    if "--check" in sys.argv:  # 自检:能构建界面即通过(不跑检测线程)
        app.update()
        w = Wizard(app, detect=False)
        w.render()
        w.update()
        w.destroy()  # 不用 close():自检不应写入 wizard_done 配置
        app.lang_var.set("English")
        app.apply_lang()
        app.update()
        app.lang_var.set("中文")
        app.apply_lang()
        print("GUI_OK")
        app.destroy()
    else:
        if not app._cfg.get("wizard_done"):
            app.after(300, lambda: Wizard(app))
        app.mainloop()
