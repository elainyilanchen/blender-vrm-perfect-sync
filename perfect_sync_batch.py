# -*- coding: utf-8 -*-
"""
VRoid VRM 批量 Perfect Sync 脚本 (v2)
=====================================
把供体 VRM0 模型上的完美同步资产(52 个 ARKit 形态键 + 辅助形态键 + BlendShapeClip
定义)按顶点序 delta 方式转移到文件夹内所有同拓扑 VRoid 脸模型上,导出 VRM 0.x。

v2 变更:
  - Clip 不再按"一键一 Clip"生成,而是**原样复制供体的 Clip 定义**
    (名称、preset、全部 bind 及权重)——供体 Clip 可能绑定主键+辅助键组合。
  - 默认转移供体上目标缺失的**全部**形态键(含 _xxx 辅助键);--arkit-only 可限制。
  - 新增顶点序一致性校验:对比供体/目标 Basis 顶点坐标距离,差异过大则警告。
  - 已有全部 52 个 ARKit 键的模型自动跳过(除非 --overwrite);供体文件自动跳过。

前置条件:
  Blender 4.0+,已启用 "VRM format" 插件(测试于 2.34.1 / Blender 4.0.2)。

用法一:平铺模式(一个文件夹,统一供体)
  "C:\\Program Files\\Blender Foundation\\Blender 4.0\\blender.exe" --background
    --python perfect_sync_batch.py --
    --donor "C:\\models\\donor_perf_sync.vrm"
    --input "C:\\models\\in" --output "C:\\models\\out"

用法二:按角色模式(--per-character)
  --input 的每个**子文件夹**是一个角色。文件夹内已有 52 个 ARKit 键的模型
  自动识别为该角色的供体(多个候选时优先文件名含 perf_sync/donor/基准 的);
  没有本角色供体的文件夹回退使用 --donor 传入的通用供体。
  输出按相同子文件夹结构写入 --output。

  ... --per-character --input "C:\\characters" --output "C:\\characters_ps"
      [--donor "C:\\models\\generic_donor.vrm"]

  characters\
    alice\  alice_perf_sync.vrm(供体,自动识别), alice_v5.vrm, alice_v6.vrm
    bob\    bob_perf_sync.vrm(供体), bob_v2.vrm
    carol\  carol_v1.vrm            ← 无供体,用 --donor 的通用供体

用法三:显式文件列表(GUI 内部使用,也可手动调用)
  ... --donor "供体.vrm" --target "a.vrm" --target "b.vrm" --output "out"

可选参数:
  --donor 可传多个,按脸部顶点数自动匹配,多个匹配取靠前者(自己调好的放最前)。
          平铺模式必填;按角色模式可选(作为无本角色供体时的回退)。
  --target 显式指定要处理的文件(可多个),代替 --input 文件夹扫描。
  --per-character 按角色子文件夹模式(见上)。
  --overwrite     同名形态键/Clip 用供体版本覆盖(供体微调后批量刷新所有版本)。
  --arkit-only    只转移 52 个 ARKit 键(默认转移全部缺失键,含辅助键)。
  --include-look  连 LookUp/LookDown/LookLeft/LookRight Clip 一起复制
                  (默认跳过,避免与目标模型骨骼 LookAt 冲突)。
  --suffix        输出文件名后缀,默认 _ps。
"""

import argparse
import json
import os
import sys
import traceback

import bpy
import numpy as np

# 汇总给 GUI 的重要警告(只收本脚本产生的,不含 Blender 噪音)
REPORT_WARNINGS = []

# ---------------------------------------------------------------- 常量

ARKIT_52 = [
    "eyeBlinkLeft", "eyeLookDownLeft", "eyeLookInLeft", "eyeLookOutLeft",
    "eyeLookUpLeft", "eyeSquintLeft", "eyeWideLeft",
    "eyeBlinkRight", "eyeLookDownRight", "eyeLookInRight", "eyeLookOutRight",
    "eyeLookUpRight", "eyeSquintRight", "eyeWideRight",
    "jawForward", "jawLeft", "jawRight", "jawOpen",
    "mouthClose", "mouthFunnel", "mouthPucker", "mouthLeft", "mouthRight",
    "mouthSmileLeft", "mouthSmileRight", "mouthFrownLeft", "mouthFrownRight",
    "mouthDimpleLeft", "mouthDimpleRight", "mouthStretchLeft", "mouthStretchRight",
    "mouthRollLower", "mouthRollUpper", "mouthShrugLower", "mouthShrugUpper",
    "mouthPressLeft", "mouthPressRight",
    "mouthLowerDownLeft", "mouthLowerDownRight",
    "mouthUpperUpLeft", "mouthUpperUpRight",
    "browDownLeft", "browDownRight", "browInnerUp",
    "browOuterUpLeft", "browOuterUpRight",
    "cheekPuff", "cheekSquintLeft", "cheekSquintRight",
    "noseSneerLeft", "noseSneerRight",
    "tongueOut",
]
ARKIT_LOWER = {n.lower() for n in ARKIT_52}
LOOK_CLIPS = {"lookup", "lookdown", "lookleft", "lookright"}

# 顶点序校验阈值(米,已去质心):同角色 <1cm,不同角色脸型差异约 3-5cm
# 均属正常(delta 转移只依赖顶点序,与脸型无关);顶点序错乱通常远大于此。
# 取 6cm 以避免对"通用供体→差异较大的脸"这一主要用例误报。
BASIS_DIST_WARN = 0.06

# ---------------------------------------------------------------- 双语消息

LANG = "zh"

_MSG = {
    "no_face_donor": ("供体中未找到脸部 mesh 或骨架: %s",
                      "No face mesh or armature found in donor: %s"),
    "vrm1_donor": ("供体 %s 是 VRM 1.0 模型;本工具只支持 VRM 0.x"
                   "(VRoid Studio 导出时请选 \"VRM0.0\")",
                   "Donor %s is a VRM 1.0 model; this tool only supports "
                   "VRM 0.x (choose \"VRM0.0\" when exporting from VRoid "
                   "Studio)"),
    "vrm1_target": ("这是 VRM 1.0 模型;本工具只支持 VRM 0.x"
                    "(VRoid Studio 导出时请选 \"VRM0.0\")",
                    "this is a VRM 1.0 model; this tool only supports "
                    "VRM 0.x (choose \"VRM0.0\" when exporting from VRoid "
                    "Studio)"),
    "donor_lacks": ("供体 %s 仅有 %d/52 个 ARKit 键,请确认已做过完美同步",
                    "Donor %s has only %d/52 ARKit shape keys; "
                    "it must be a perfect-sync model"),
    "no_face": ("未找到脸部 mesh 或骨架",
                "No face mesh or armature found"),
    "mismatch": ("脸部顶点数 %d 与所有供体(%s)不匹配 → 拓扑不同,"
                 "需走 Surface Deform / HANA_Tool",
                 "Face vertex count %d matches no donor (%s) → different "
                 "topology; needs Surface Deform / HANA_Tool"),
    "basis_note": ("basis顶点距离 mean=%.4fm max=%.4fm",
                   "basis vertex distance mean=%.4fm max=%.4fm"),
    "basis_warn": (" [警告: 差异偏大,请务必目检结果"
                   "(脸型参数差异大或顶点序不一致)]",
                   " [WARNING: large difference - visually inspect the "
                   "result (big face-shape difference or vertex order "
                   "mismatch)]"),
    "result_info": ("键 +%d/覆%d/跳%d, Clip +%d/覆%d/跳%d, ARKit键 %d/52, "
                    "%s, 供体 %s",
                    "keys +%d/repl %d/skip %d, clips +%d/repl %d/skip %d, "
                    "ARKit keys %d/52, %s, donor %s"),
    "prog": ("%s[%d/%d] 处理 %s ...", "%s[%d/%d] Processing %s ..."),
    "is_donor": ("是供体文件", "this is a donor file"),
    "has52": ("已有全部 52 个 ARKit 键",
              "already has all 52 ARKit keys"),
    "same_path": ("输出路径与源文件相同,会覆盖原文件;请换输出文件夹或后缀",
                  "Output path equals the source file and would overwrite "
                  "it; change the output folder or suffix"),
    "cant_import": ("无法导入: %s", "failed to import: %s"),
    "local_donor": ("%s本角色供体: %s%s", "%sCharacter donor: %s%s"),
    "other_cands": ("(其他候选: %s)", " (other candidates: %s)"),
    "fallback_donor": ("%s无本角色供体,回退使用通用供体",
                       "%sNo character donor; falling back to the global "
                       "donor"),
    "no_donor_at_all": ("该角色无供体且未提供 --donor 通用供体",
                        "no donor for this character and no --donor "
                        "fallback provided"),
    "donor_load_fail": ("供体加载失败: %s", "failed to load donor: %s"),
    "donors_loaded": ("通用供体加载完成: %s", "Global donor(s) loaded: %s"),
    "fatal_donor": ("\n[致命错误] 供体加载失败: %s",
                    "\n[FATAL] Failed to load the donor: %s"),
    "dup_name": ("警告: 有重名文件 %s,输出会互相覆盖",
                 "Warning: duplicate file name %s - outputs will overwrite "
                 "each other"),
    "no_subdirs": ("警告: --per-character 模式下 %s 中没有子文件夹",
                   "Warning: no subfolders in %s for --per-character mode"),
    "root_skipped": ("提示: 根目录下 %d 个 VRM 未处理"
                     "(按角色模式只扫子文件夹): %s",
                     "Note: %d root-level VRM files not processed "
                     "(per-character mode scans subfolders only): %s"),
    "summary_hdr": ("\n========== 批量处理结果 ==========",
                    "\n========== Batch results =========="),
    "summary": ("完成: %d 转移 / %d 跳过 / %d 失败 (共 %d)",
                "Done: %d transferred / %d skipped / %d failed (total %d)"),
    "warn_nonface_bind": ("Clip %s 的 bind 指向非脸 mesh %s,已忽略该 bind",
                          "Clip %s binds to non-face mesh %s; bind ignored"),
    "warn_missing_key": ("Clip %s 缺少形态键 %s,已忽略该 bind",
                         "Clip %s is missing shape key %s; bind ignored"),
    "warn_bind_api": ("Clip %s 无法设置 bind.mesh(插件 API 变化?)",
                      "Clip %s: cannot set bind.mesh (add-on API change?)"),
    "warn_matval": ("Clip %s 含 %d 个 material_value,未复制",
                    "Clip %s has %d material_value entries; not copied"),
}


def M(key, *a):
    zh, en = _MSG[key]
    s = zh if LANG == "zh" else en
    return (s % a) if a else s

# ---------------------------------------------------------------- 工具函数


def reset_scene():
    bpy.ops.wm.read_homefile(use_empty=True)


def import_vrm(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.vrm(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def find_face_mesh(objects):
    """VRoid 的脸 = 带 Fcl_ 系形态键的 mesh;兜底取形态键最多的 mesh。"""
    best, best_count = None, -1
    for o in objects:
        if o.type != "MESH" or not o.data.shape_keys:
            continue
        names = [k.name for k in o.data.shape_keys.key_blocks]
        if any(n.startswith("Fcl_") for n in names) or any(
            n.lower() in ARKIT_LOWER for n in names
        ):
            return o
        if len(names) > best_count:
            best, best_count = o, len(names)
    return best


def find_armature(objects):
    for o in objects:
        if o.type == "ARMATURE":
            return o
    return None


def is_vrm1(armature_obj):
    """导入后从插件扩展读 spec 版本,VRM 1.x 返回 True。"""
    if armature_obj is None:
        return False
    ext = getattr(armature_obj.data, "vrm_addon_extension", None)
    spec = str(getattr(ext, "spec_version", "")) if ext else ""
    return spec.startswith("1")


def count_arkit(face_obj):
    if not face_obj.data.shape_keys:
        return 0
    return sum(1 for k in face_obj.data.shape_keys.key_blocks
               if k.name.lower() in ARKIT_LOWER)


def get_basis_co(face_obj):
    kb = face_obj.data.shape_keys.key_blocks
    n = len(face_obj.data.vertices) * 3
    co = np.empty(n, dtype=np.float64)
    kb[0].data.foreach_get("co", co)
    return co


def _bind_mesh_name(bind):
    m = getattr(bind, "mesh", None)
    if m is None:
        return ""
    for attr in ("mesh_object_name", "value", "name"):
        v = getattr(m, attr, None)
        if isinstance(v, str) and v:
            return v
    return ""


def _set_bind_mesh(bind, obj_name):
    m = getattr(bind, "mesh", None)
    if m is None:
        return False
    for attr in ("mesh_object_name", "value", "name"):
        if hasattr(m, attr):
            try:
                setattr(m, attr, obj_name)
                return True
            except Exception:
                pass
    return False


# ---------------------------------------------------------------- 供体提取


def extract_donor(donor_path, arkit_only=False):
    """导入供体一次,提取形态键 delta + BlendShapeClip 完整定义,然后清场。"""
    reset_scene()
    objs = import_vrm(donor_path)
    face = find_face_mesh(objs)
    arm = find_armature(objs)
    if face is None or arm is None:
        raise RuntimeError(M("no_face_donor", donor_path))
    if is_vrm1(arm):
        raise RuntimeError(M("vrm1_donor", donor_path))

    kb = face.data.shape_keys.key_blocks
    vcount = len(face.data.vertices)
    basis = get_basis_co(face)

    n_arkit = count_arkit(face)
    if n_arkit < 52:
        raise RuntimeError(M("donor_lacks", donor_path, n_arkit))

    deltas = {}
    for key in kb[1:]:
        if arkit_only and key.name.lower() not in ARKIT_LOWER:
            continue
        co = np.empty(vcount * 3, dtype=np.float64)
        key.data.foreach_get("co", co)
        d = co - basis
        if arkit_only or np.abs(d).max() > 1e-9 or key.name.lower() in ARKIT_LOWER:
            deltas[key.name] = d

    # Clip 完整定义
    clips = []
    ext = arm.data.vrm_addon_extension
    for g in ext.vrm0.blend_shape_master.blend_shape_groups:
        binds = []
        for b in g.binds:
            binds.append({
                "mesh": _bind_mesh_name(b),
                "key": b.index,  # 该插件中 index 即形态键名
                "weight": float(getattr(b, "weight", 1.0)),
            })
        clips.append({
            "name": g.name,
            "preset": str(getattr(g, "preset_name", "unknown")),
            "is_binary": bool(getattr(g, "is_binary", False)),
            "binds": binds,
            "n_material_values": len(getattr(g, "material_values", [])),
        })

    return {
        "path": os.path.abspath(donor_path),
        "vcount": vcount,
        "basis": basis,
        "face_name": face.name,
        "deltas": deltas,
        "clips": clips,
    }


# ---------------------------------------------------------------- 转移


def transfer_shape_keys(face_obj, donor, overwrite=False):
    mesh = face_obj.data
    if not mesh.shape_keys:
        face_obj.shape_key_add(name="Basis", from_mix=False)
    kb = mesh.shape_keys.key_blocks
    existing = {k.name.lower(): k for k in kb}
    basis_name = kb[0].name.lower()
    basis = get_basis_co(face_obj)

    added = replaced = skipped = 0
    for name, delta in donor["deltas"].items():
        lname = name.lower()
        if lname == basis_name:
            continue
        if lname in existing:
            if not overwrite:
                skipped += 1
                continue
            key = existing[lname]
            replaced += 1
        else:
            key = face_obj.shape_key_add(name=name, from_mix=False)
            key.value = 0.0
            added += 1
        key.data.foreach_set("co", basis + delta)
    return added, replaced, skipped


def copy_clips(armature_obj, face_obj, donor, overwrite=False,
               include_look=False):
    """把供体 Clip 定义(含多键 bind)复制到目标。返回 (新增, 覆盖, 跳过, 警告列表)。"""
    ext = getattr(armature_obj.data, "vrm_addon_extension", None)
    if ext is None:
        raise RuntimeError("未找到 vrm_addon_extension,请确认 VRM 插件已启用")
    if hasattr(ext, "spec_version"):
        try:
            ext.spec_version = "0.0"
        except Exception:
            pass

    groups = ext.vrm0.blend_shape_master.blend_shape_groups
    existing = {g.name.lower(): i for i, g in enumerate(groups)}
    face_keys = {k.name.lower(): k.name
                 for k in face_obj.data.shape_keys.key_blocks}
    donor_face = donor["face_name"]

    added = replaced = skipped = 0
    warnings = []
    for clip in donor["clips"]:
        lname = clip["name"].lower()
        if lname in LOOK_CLIPS and not include_look:
            continue
        if lname in existing:
            if not overwrite:
                skipped += 1
                continue
            groups.remove(existing[lname])
            existing = {g.name.lower(): i for i, g in enumerate(groups)}
            replaced += 1
        else:
            added += 1

        # bind 引用的键必须都在目标上(且 mesh 是供体脸 → 映射为目标脸)
        ok_binds = []
        for b in clip["binds"]:
            if b["mesh"] != donor_face:
                warnings.append(M("warn_nonface_bind", clip["name"],
                                  b["mesh"]))
                continue
            if b["key"].lower() not in face_keys:
                warnings.append(M("warn_missing_key", clip["name"],
                                  b["key"]))
                continue
            ok_binds.append(b)

        g = groups.add()
        g.name = clip["name"]
        if hasattr(g, "preset_name"):
            try:
                g.preset_name = clip["preset"]
            except Exception:
                pass
        if hasattr(g, "is_binary"):
            try:
                g.is_binary = clip["is_binary"]
            except Exception:
                pass
        for b in ok_binds:
            nb = g.binds.add()
            if not _set_bind_mesh(nb, face_obj.name):
                warnings.append(M("warn_bind_api", clip["name"]))
            nb.index = face_keys[b["key"].lower()]
            try:
                nb.weight = b["weight"]
            except Exception:
                pass
        if clip["n_material_values"]:
            warnings.append(M("warn_matval", clip["name"],
                              clip["n_material_values"]))
        existing[lname] = len(groups) - 1
    return added, replaced, skipped, warnings


def export_vrm(out_path):
    for o in bpy.data.objects:
        o.select_set(True)
    bpy.ops.export_scene.vrm(filepath=out_path)


# ---------------------------------------------------------------- 主流程


def process_one(vrm_path, out_path, donors, overwrite=False,
                include_look=False):
    reset_scene()
    objs = import_vrm(vrm_path)
    face = find_face_mesh(objs)
    arm = find_armature(objs)
    if face is None or arm is None:
        raise RuntimeError(M("no_face"))
    if is_vrm1(arm):
        raise RuntimeError(M("vrm1_target"))

    vcount = len(face.data.vertices)
    donor = next((d for d in donors if d["vcount"] == vcount), None)
    if donor is None:
        raise RuntimeError(M(
            "mismatch", vcount,
            ", ".join(str(d["vcount"]) for d in donors)))

    # 顶点序一致性校验:逐顶点距离。先各自去掉质心(消除角色身高/头部
    # 位置差异,delta 转移本就与位置无关),只留形状+顶点序差异,避免对
    # 身高不同但拓扑一致的模型误报。
    tb = get_basis_co(face).reshape(-1, 3)
    db = donor["basis"].reshape(-1, 3)
    tb = tb - tb.mean(axis=0)
    db = db - db.mean(axis=0)
    dist = np.linalg.norm(tb - db, axis=1)
    order_note = M("basis_note", dist.mean(), dist.max())
    if dist.mean() > BASIS_DIST_WARN:
        order_note += M("basis_warn")
        w = "%s: %s" % (os.path.basename(vrm_path), order_note)
        print("  [warn] " + w, flush=True)
        REPORT_WARNINGS.append(w)

    k_add, k_rep, k_skip = transfer_shape_keys(face, donor, overwrite)
    c_add, c_rep, c_skip, warns = copy_clips(
        arm, face, donor, overwrite, include_look)
    final_arkit = count_arkit(face)
    for w in warns:
        print("  [warn] " + w, flush=True)
        REPORT_WARNINGS.append(
            "%s: %s" % (os.path.basename(vrm_path), w))

    export_vrm(out_path)
    return M("result_info", k_add, k_rep, k_skip, c_add, c_rep, c_skip,
             final_arkit, order_note, os.path.basename(donor["path"]))


DONOR_MARKERS = ("perf_sync", "perfsync", "donor", "基准")


def probe_file(path):
    """返回 (arkit键数, 脸部顶点数);无脸返回 (0, 0)。"""
    reset_scene()
    objs = import_vrm(path)
    face = find_face_mesh(objs)
    if face is None:
        return 0, 0
    return count_arkit(face), len(face.data.vertices)


def pick_local_donor(candidates):
    """从多个已有 52 键的文件中选本角色供体:优先文件名带标记的。"""
    marked = [f for f in candidates
              if any(m in f.lower() for m in DONOR_MARKERS)]
    return sorted(marked or candidates)[0]


def process_folder(in_dir, out_dir, global_donors, args, label,
                   per_character, file_paths=None):
    """处理一个文件夹(或显式文件列表),返回 [(label, status, file, info)]。"""
    tag = ("[%s] " % label) if label else ""
    if file_paths is None:
        names = sorted(f for f in os.listdir(in_dir)
                       if f.lower().endswith(".vrm"))
        pairs = [(f, os.path.join(in_dir, f)) for f in names]
    else:
        pairs = [(os.path.basename(p), p) for p in file_paths]
    if not pairs:
        return []

    results = []
    donors = list(global_donors)
    probe = {}

    if per_character:
        # 预探测每个文件,自动识别本角色供体
        for f, src in pairs:
            try:
                probe[f] = probe_file(src)
            except Exception as e:
                probe[f] = None
                results.append((label, "FAIL", f, M("cant_import", e)))
        candidates = [f for f, _ in pairs
                      if probe.get(f) and probe[f][0] >= 52]
        if candidates:
            donor_file = pick_local_donor(candidates)
            others = [c for c in candidates if c != donor_file]
            try:
                local = extract_donor(dict(pairs)[donor_file],
                                      args.arkit_only)
                donors = [local] + donors
                print(M("local_donor", tag, donor_file,
                        M("other_cands", ", ".join(others))
                        if others else ""), flush=True)
            except Exception as e:
                results.append((label, "FAIL", donor_file,
                                M("donor_load_fail", e)))
        elif donors:
            print(M("fallback_donor", tag), flush=True)
        else:
            for f, _ in pairs:
                results.append((label, "FAIL", f, M("no_donor_at_all")))
            return results

    donor_paths = {d["path"] for d in donors}
    made_out = False
    for idx, (f, src) in enumerate(pairs, 1):
        print(M("prog", tag, idx, len(pairs), f), flush=True)
        if os.path.abspath(src) in donor_paths:
            results.append((label, "SKIP", f, M("is_donor")))
            continue
        if any(r[2] == f and r[1] == "FAIL" for r in results):
            continue  # 探测阶段已失败
        # 预检:已完成的跳过(--overwrite 时仍处理,用于批量刷新)
        if not args.overwrite:
            if per_character:
                done = probe.get(f) and probe[f][0] >= 52
            else:
                reset_scene()
                objs = import_vrm(src)
                fm = find_face_mesh(objs)
                done = fm is not None and count_arkit(fm) >= 52
            if done:
                results.append((label, "SKIP", f, M("has52")))
                continue
        if not made_out:
            os.makedirs(out_dir, exist_ok=True)
            made_out = True
        dst = os.path.join(out_dir,
                           os.path.splitext(f)[0] + args.suffix + ".vrm")
        if os.path.abspath(dst) == os.path.abspath(src):
            results.append((label, "FAIL", f, M("same_path")))
            continue
        try:
            info = process_one(src, dst, donors, args.overwrite,
                               args.include_look)
            results.append((label, "OK  ", f, info))
        except Exception as e:
            traceback.print_exc()
            results.append((label, "FAIL", f, str(e)))
    return results


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--donor", action="append", default=[])
    p.add_argument("--input")
    p.add_argument("--target", action="append", default=[],
                   help="显式指定要处理的 VRM 文件(可多个;与 --input 二选一)")
    p.add_argument("--output", required=True)
    p.add_argument("--suffix", default="_ps")
    p.add_argument("--per-character", action="store_true",
                   help="input 的每个子文件夹是一个角色,自动识别本角色供体")
    p.add_argument("--arkit-only", action="store_true",
                   help="只转移 52 个 ARKit 键(默认转移全部缺失键)")
    p.add_argument("--overwrite", action="store_true",
                   help="同名形态键/Clip 用供体版本覆盖")
    p.add_argument("--include-look", action="store_true",
                   help="连 Look 系 Clip 一起复制(默认跳过)")
    p.add_argument("--lang", choices=("zh", "en"), default="zh",
                   help="日志语言 / log language")
    p.add_argument("--report",
                   help="把结构化结果写成 JSON(GUI 用,替代解析日志)")
    args = p.parse_args(argv)

    global LANG
    LANG = args.lang

    if not args.input and not args.target:
        p.error("必须提供 --input 文件夹或 --target 文件")
    if args.target and args.per_character:
        p.error("--target 与 --per-character 不能同时使用")
    if not args.per_character and not args.donor:
        p.error("平铺模式必须提供 --donor;或改用 --per-character")

    try:
        global_donors = [extract_donor(d, args.arkit_only)
                         for d in args.donor]
    except Exception as e:
        traceback.print_exc()
        print(M("fatal_donor", e), flush=True)
        print("BATCH_RESULT ok=0 skip=0 fail=-1", flush=True)
        if args.report:
            with open(args.report, "w", encoding="utf-8") as f:
                json.dump({"fatal": str(e)}, f, ensure_ascii=False)
        return
    if global_donors:
        print(M("donors_loaded", ", ".join(
            "%s(v=%d, keys=%d, clips=%d)" % (os.path.basename(d["path"]),
                                             d["vcount"], len(d["deltas"]),
                                             len(d["clips"]))
            for d in global_donors)), flush=True)

    results = []
    if args.target:
        seen = set()
        for t in args.target:
            base = os.path.basename(t).lower()
            if base in seen:
                print(M("dup_name", base), flush=True)
            seen.add(base)
        results = process_folder(None, args.output, global_donors, args,
                                 "", False,
                                 [os.path.abspath(t) for t in args.target])
    elif args.per_character:
        subs = sorted(d for d in os.listdir(args.input)
                      if os.path.isdir(os.path.join(args.input, d)))
        if not subs:
            print(M("no_subdirs", args.input), flush=True)
        root_vrms = [f for f in os.listdir(args.input)
                     if f.lower().endswith(".vrm")]
        if root_vrms:
            print(M("root_skipped", len(root_vrms), ", ".join(root_vrms)),
                  flush=True)
        for sub in subs:
            results += process_folder(
                os.path.join(args.input, sub),
                os.path.join(args.output, sub),
                global_donors, args, sub, True)
    else:
        results = process_folder(args.input, args.output,
                                 global_donors, args, "", False)

    print(M("summary_hdr"))
    for label, status, f, info in results:
        name = ("%s/%s" % (label, f)) if label else f
        print("[%s] %s : %s" % (status, name, info))
    ok = sum(1 for r in results if r[1] == "OK  ")
    skip = sum(1 for r in results if r[1] == "SKIP")
    fail = sum(1 for r in results if r[1] == "FAIL")
    print(M("summary", ok, skip, fail, len(results)), flush=True)
    print("BATCH_RESULT ok=%d skip=%d fail=%d" % (ok, skip, fail),
          flush=True)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump({"ok": ok, "skip": skip, "fail": fail,
                       "results": [list(r) for r in results],
                       "warnings": REPORT_WARNINGS},
                      f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
