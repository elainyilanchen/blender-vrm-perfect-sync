# Sample donor models

This folder holds ready-made **donor** models — neutral VRoid faces that already
carry the 52 ARKit perfect-sync shapes — so you can start using the tool
immediately without making your own donor first.

Point the tool's **Donor** slot at one of these, add your own VRoid models as
recipients, and press Start.

> Status: the curated male/female donors are being prepared and will be added
> here. Until then, use your own perfect-sync model as the donor, or the
> community data at
> [hinzka/52blendshapes-for-VRoid-face](https://github.com/hinzka/52blendshapes-for-VRoid-face)
> (note: that data is several years old and may not match the latest VRoid
> topology).

## Requirements a donor must meet

- Exported from VRoid Studio as **VRM 0.0** (not VRM 1.0).
- **No** mesh reduction (*Reduce Polygons / ポリゴンの削減* disabled) — the face
  must keep the standard official-VRoid topology.
- Contains all **52 ARKit blendshapes**, bound as VRM BlendShapeClips.

## License of the sample models

**The sample `.vrm` files in this folder are NOT covered by the repository's MIT
license.** Each model carries its own usage terms embedded in the VRM metadata.

These donors are built from a model created from scratch in VRoid Studio using
pixiv's default base assets. Under pixiv/VRoid's terms, a model you create this
way may be freely used, modified, and redistributed — **but it may not be marked
CC0**, because pixiv retains rights to the base meshes, textures and presets it
provides.

Since CC0 is off the table, these sample donors are distributed under
**CC BY 4.0** — the closest widely-recognized "use it freely" license that
pixiv's terms allow — with the following VRM metadata:

- **License:** CC BY 4.0 (attribution required, copyright **not** waived)
- **Allowed users:** everyone
- **Modification:** allowed
- **Redistribution:** allowed
- **Commercial use:** allowed
- **Sexual / violent use:** disallowed
- **Credit:** "blender-vrm-perfect-sync sample donor" + "VRoid Studio / pixiv"

**What this means in practice:** you can drop these donors into the tool and add
perfect sync to your own models freely. Attribution under CC BY only applies if
you *redistribute the donor itself* (or a modified donor) — it is not intended to
burden the personal models you process for your own use.

> Prefer zero attribution obligation? A custom "Other" VRM license reading
> *"free to use, modify and redistribute, including inside other models;
> attribution appreciated but not required; not CC0"* is also fully
> pixiv-compliant and slightly more permissive than CC BY. Either is fine.

If you export your own donor and want to share it, keep the same rule of thumb:
**you may redistribute a model you made in VRoid Studio, but do not set its
license to CC0.** See VRoid's official terms:

- [Can I use models made with VRoid Studio commercially?](https://vroid.pixiv.help/hc/en-us/articles/4405813333657)
- [Do VRoid Studio's sample models come with conditions of use?](https://vroid.pixiv.help/hc/en-us/articles/4402614652569)
- [About license data for VRM files](https://vroid.pixiv.help/hc/en-us/articles/360014193033)
