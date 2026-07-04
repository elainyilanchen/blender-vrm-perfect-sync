# blender-vrm-perfect-sync

**Add iPhone/ARKit "perfect sync" (52 blendshapes) to your VRoid VRM models — in batch, with a click-to-run app. No Blender skills required.**

VRoid Studio exports don't include the 52 ARKit expression shapes that face-tracking apps (Warudo, VNyan, VRM Posing Desktop, VSeeFace…) use for perfect sync. This tool copies a finished perfect-sync setup from **one donor model** onto **any number of your other VRoid models** automatically, because every official VRoid face shares the same mesh topology — the expression shapes transfer vertex-for-vertex, with zero manual sculpting.

> Windows only. Works fully offline once set up. Your original files are never modified — results are written as new `*_ps.vrm` files.

---

## ✨ What you get

- **One-click app** (`Perfect-Sync.bat`) with a friendly window — pick a donor on the left, drop your models on the right, press Start.
- **Batch processing** with multiple donor/recipient groups (one donor per character, many versions each).
- **First-run wizard** that checks for and can auto-download everything you need (Blender + VRM add-on).
- **Bilingual UI** (English / 中文), high-DPI aware.
- **Safe**: existing keys are skipped by default; a verify step confirms every clip binding transferred correctly.
- **Power-user CLI** underneath the GUI — see [docs/CLI.md](docs/CLI.md).

---

## 🚀 Quick start (for everyone)

1. **Download this repo**: click the green **Code → Download ZIP**, then unzip it to a folder you can find (e.g. your Desktop).
2. **Double-click `Perfect-Sync.bat`** (or `启动完美同步工具.bat`).
   - If Python isn't installed, the launcher offers to install it for you.
3. On first run, the **setup wizard** checks three things — Python, Blender, and the VRM add-on — and can download the missing ones with one click (~400 MB, once).
4. In the main window:
   - **Donor (left):** choose a model that already has perfect sync (see *Getting a donor* below).
   - **Recipients (right):** add the models you want to add expressions to (Ctrl-click to select several).
   - Pick an **output folder** and press **Start**.
5. Open the results (`yourmodel_ps.vrm`) in your VTuber app and enjoy perfect sync. 🎉

Different characters use different donors? Click **“+ Add group”** for each one.

---

## 🎭 Getting a donor

A "donor" is any VRoid model that already has the 52 ARKit perfect-sync shapes.

- **Use your own** — if you've already made one perfect-sync model, use it as the donor for all your other models of that character. Any personal tweaks (expression strengths, fixed tongue, etc.) carry over to every model.
- **Use a sample donor** — ready-made neutral male/female donors are provided in [`samples/`](samples/) so you can start immediately. See [samples/README.md](samples/README.md) for their license.

> **Important — export settings in VRoid Studio:** export as **VRM 0.0**, and do **not** enable *Reduce Polygons / ポリゴンの削減* or any mesh-reduction option. Both change the face so the transfer can't line up. (The tool detects and rejects VRM 1.0 and mismatched topology, so you won't get a broken file — you'll just get a clear error.)

---

## ✅ Requirements

| Need | Auto-handled? |
|------|---------------|
| Windows 10/11 | — |
| Python 3 | Launcher offers to auto-install |
| Blender (2.93–4.1, ships/tested on 4.0.2) | Setup wizard can download a portable copy |
| VRM add-on for Blender | Setup wizard installs it |

If you already have Blender with the VRM add-on, just point the tool at your `blender.exe` and skip the download.

---

## 🔧 Advanced / CLI

Everything the GUI does is a thin wrapper over headless Blender scripts you can run yourself — batch transfer, per-character folders, clip-weight tuning, and binding verification. See **[docs/CLI.md](docs/CLI.md)**.

---

## 📄 License & credits

- **Code** (scripts, launcher, docs): [MIT](LICENSE).
- **Sample models** under `samples/`: their own terms — see [samples/README.md](samples/README.md).
- Built on: [Blender](https://www.blender.org/) (GPL), the [VRM Add-on for Blender](https://github.com/saturday06/VRM-Addon-for-Blender) (MIT), and [VRoid Studio](https://vroid.com/) by pixiv.
- The vertex-order delta-transfer idea follows the community approach pioneered by [hinzka/52blendshapes-for-VRoid-face](https://github.com/hinzka/52blendshapes-for-VRoid-face).

---

## 中文说明

**给 VRoid 的 VRM 模型批量添加 iPhone/ARKit「完美同步」(52 个表情形态键),点一下就能用,无需 Blender 基础。**

VRoid 导出的模型默认没有面捕软件(Warudo、VNyan、VRM Posing Desktop、VSeeFace 等)所需的 52 个 ARKit 表情。本工具把**一个供体模型**上做好的完美同步,按顶点序自动搬到**任意多个** VRoid 模型上——因为官方 VRoid 脸拓扑统一,表情形态键零误差转移,无需手动雕刻。

> 仅支持 Windows。配好后可完全离线运行。**不会修改原文件**,结果另存为 `*_ps.vrm`。

### 快速开始

1. 点绿色 **Code → Download ZIP** 下载并解压到好找的文件夹。
2. **双击 `启动完美同步工具.bat`**。没装 Python 会提示自动安装。
3. 首次运行的**向导**会检测 Python / Blender / VRM 插件,可一键下载缺失项(约 400MB,仅一次)。
4. 主界面:左边选**供体**(已做完美同步的模型),右边**添加受体**(要加表情的模型,可 Ctrl 多选),选输出文件夹,点**开始处理**。
5. 把结果 `模型名_ps.vrm` 导入面捕软件即可。不同角色用不同供体就点「+ 添加组合」。

### 供体从哪来

供体 = 任何已带 52 个 ARKit 表情的 VRoid 模型。可以**用自己做好的**(该角色的个人微调会一并带到所有模型),也可以用 [`samples/`](samples/) 里提供的中性男/女示例供体(许可见 [samples/README.md](samples/README.md))。

> **VRoid Studio 导出注意**:选 **VRM 0.0**,且**不要开启「ポリゴンの削減 / 减少多边形」**等网格精简选项(会改变拓扑导致无法转移)。VRM 1.0 和拓扑不符会被明确报错拒收,不会产出坏文件。

详细命令行用法见 [docs/CLI.md](docs/CLI.md)。
