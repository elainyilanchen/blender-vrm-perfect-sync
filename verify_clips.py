# -*- coding: utf-8 -*-
"""
Clip 绑定校验脚本:对比供体与输出 VRM 的完美同步 Clip 定义。

逐 bind 检查键名与权重是否一致——用于确认有意调整过的权重
(如 BrowDown 0.3、MouthClose 0.103)在批量转移后原样保留。

用法 (一行):
  "C:\\Program Files\\Blender Foundation\\Blender 4.0\\blender.exe" --background
    --python verify_clips.py --
    --donor "donor_perf_sync.vrm" --file "out\\model_ps.vrm" [--file ...]

退出码非 0 表示存在不一致(可用于批处理判断)。
"""
import argparse
import sys

import bpy

LOOK_CLIPS = {"lookup", "lookdown", "lookleft", "lookright"}


def dump_clips(vrm_path):
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.import_scene.vrm(filepath=vrm_path)
    clips = {}
    for o in bpy.data.objects:
        if o.type != "ARMATURE":
            continue
        ext = o.data.vrm_addon_extension
        for g in ext.vrm0.blend_shape_master.blend_shape_groups:
            binds = []
            for b in g.binds:
                binds.append((b.index, round(float(b.weight), 4)))
            clips[g.name] = sorted(binds)
    return clips


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--donor", required=True)
    p.add_argument("--file", action="append", required=True)
    args = p.parse_args(argv)

    donor = dump_clips(args.donor)
    # 只校验完美同步 Clip(供体上 BlendShape.* 命名的);Look 系默认不转移,跳过
    ps_clips = {n: b for n, b in donor.items()
                if n.startswith("BlendShape.") and n.lower() not in LOOK_CLIPS}
    print("供体 %s: 完美同步 Clip %d 个, 其中权重≠1.0 的绑定:"
          % (args.donor, len(ps_clips)))
    for n, binds in sorted(ps_clips.items()):
        for k, w in binds:
            if w != 1.0:
                print("    %s : %s = %s" % (n, k, w))

    any_fail = False
    for f in args.file:
        target = dump_clips(f)
        missing, mismatch, ok = [], [], 0
        for n, db in ps_clips.items():
            tb = target.get(n)
            if tb is None:
                missing.append(n)
            elif tb != db:
                mismatch.append((n, db, tb))
            else:
                ok += 1
        print("\n[%s] 一致 %d / 缺失 %d / 不一致 %d"
              % (f, ok, len(missing), len(mismatch)))
        for n in missing:
            print("    缺失: %s" % n)
        for n, db, tb in mismatch:
            print("    不一致: %s\n      供体 %s\n      输出 %s" % (n, db, tb))
        if missing or mismatch:
            any_fail = True

    print("\n校验%s" % ("未通过" if any_fail else "全部通过"))
    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
