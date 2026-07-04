# -*- coding: utf-8 -*-
"""
表情微调 CLI 工具:不开 Blender 界面,直接改 VRM 的 Clip 权重 / 形态键强度。

典型闭环:Warudo 里目检 → 发现某表情过强/过弱 → 用本脚本改供体 →
perfect_sync_batch.py --overwrite 批量刷新所有版本 → verify_clips.py 校验。

用法 (前缀均为: blender.exe --background --python tune_expression.py -- ):

  1) 查看当前所有 Clip 绑定和权重(找名字用):
     --file "donor_perf_sync.vrm" --list

  2) 改 Clip 绑定权重(最常用,可逆,直接改数值):
     --file "donor_perf_sync.vrm" --set "BlendShape.BrowDownLeft=0.25"
     多绑定 Clip 需指定键名(用 / 分隔):
     --set "BlendShape.MouthPressLeft/_mouthPress+CatMouth=0.3"
     --set 可传多个,一次改多处。

  3) 缩放形态键本身的位移量(改变形幅度;注意会累积,0.8 再 0.8 = 0.64,
     建议优先用 --set 调 Clip 权重):
     --file "..." --scale-key "mouthSmileLeft=0.8"

  输出:默认原地保存(首次自动备份为 原名.vrm.bak);--out 可另存。
"""

import argparse
import os
import shutil
import sys

import bpy
import numpy as np


def _bind_mesh_name(bind):
    m = getattr(bind, "mesh", None)
    if m is None:
        return ""
    for attr in ("mesh_object_name", "value", "name"):
        v = getattr(m, attr, None)
        if isinstance(v, str) and v:
            return v
    return ""


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True)
    p.add_argument("--list", action="store_true",
                   help="只列出 Clip/绑定/权重,不修改")
    p.add_argument("--set", action="append", default=[],
                   metavar="CLIP[/KEY]=W", help="设置 Clip 绑定权重")
    p.add_argument("--scale-key", action="append", default=[],
                   metavar="KEY=F", help="形态键位移量整体乘以系数 F")
    p.add_argument("--out", help="另存路径(默认原地保存,首次备份 .bak)")
    args = p.parse_args(argv)

    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.import_scene.vrm(filepath=args.file)

    arm = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
    face = next((o for o in bpy.data.objects
                 if o.type == "MESH" and o.data.shape_keys and any(
                     k.name.startswith("Fcl_")
                     for k in o.data.shape_keys.key_blocks)), None)
    if arm is None or face is None:
        raise RuntimeError("未找到骨架或脸部 mesh")
    groups = arm.data.vrm_addon_extension.vrm0.blend_shape_master \
        .blend_shape_groups

    if args.list:
        print("\n===== Clip 绑定一览 =====")
        for g in groups:
            binds = ["%s=%.4g" % (b.index, b.weight) for b in g.binds]
            print("  %-38s %s" % (g.name, ", ".join(binds)))
        print("\n===== 非 Fcl 形态键 =====")
        for k in face.data.shape_keys.key_blocks[1:]:
            if not k.name.startswith("Fcl_"):
                print("  " + k.name)
        return

    if not args.set and not args.scale_key:
        raise SystemExit("未指定任何修改;用 --list 查看,--set/--scale-key 修改")

    changed = []

    # ---- Clip 权重 ----
    clip_by_lname = {g.name.lower(): g for g in groups}
    for spec in args.set:
        lhs, _, w = spec.rpartition("=")
        clip_name, _, key_name = lhs.partition("/")
        w = float(w)
        g = clip_by_lname.get(clip_name.lower())
        if g is None:
            raise RuntimeError("找不到 Clip: %s" % clip_name)
        binds = list(g.binds)
        if key_name:
            targets = [b for b in binds
                       if b.index.lower() == key_name.lower()]
            if not targets:
                raise RuntimeError("Clip %s 中无绑定键 %s(现有: %s)" % (
                    g.name, key_name, ", ".join(b.index for b in binds)))
        elif len(binds) == 1:
            targets = binds
        else:
            # 多绑定时,若有键名与 Clip 主名对应(去掉 BlendShape. 前缀)则选它
            main_name = g.name.lower().replace("blendshape.", "")
            targets = [b for b in binds if b.index.lower() == main_name]
            if not targets:
                raise RuntimeError(
                    "Clip %s 有 %d 个绑定,请用 CLIP/KEY=W 指定键(现有: %s)"
                    % (g.name, len(binds),
                       ", ".join(b.index for b in binds)))
        for b in targets:
            old = float(b.weight)
            b.weight = w
            changed.append("Clip %s / %s : %.4g -> %.4g"
                           % (g.name, b.index, old, w))

    # ---- 形态键缩放 ----
    kb = face.data.shape_keys.key_blocks
    key_by_lname = {k.name.lower(): k for k in kb}
    n = len(face.data.vertices) * 3
    basis = np.empty(n)
    kb[0].data.foreach_get("co", basis)
    for spec in args.scale_key:
        name, _, f = spec.rpartition("=")
        f = float(f)
        k = key_by_lname.get(name.lower())
        if k is None:
            raise RuntimeError("找不到形态键: %s" % name)
        co = np.empty(n)
        k.data.foreach_get("co", co)
        k.data.foreach_set("co", basis + (co - basis) * f)
        changed.append("形态键 %s 位移量 ×%.4g" % (k.name, f))

    # ---- 保存 ----
    out = args.out or args.file
    if out == args.file:
        bak = args.file + ".bak"
        if not os.path.exists(bak):
            shutil.copy2(args.file, bak)
            print("已备份原文件: %s" % bak)
    for o in bpy.data.objects:
        o.select_set(True)
    bpy.ops.export_scene.vrm(filepath=out)

    print("\n===== 修改内容 =====")
    for c in changed:
        print("  " + c)
    print("已保存: %s" % out)


if __name__ == "__main__":
    main()
