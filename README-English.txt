=====================================================
 VRM Perfect Sync Tool - quick guide (plain text)
=====================================================

WHAT IT DOES
  Adds iPhone/ARKit "perfect sync" (52 expression blendshapes) to your
  VRoid VRM models, in batch. No Blender knowledge needed.
  Your original files are never modified - results are saved as new
  files named  yourmodel_ps.vrm

HOW TO START
  1. Unzip this folder to a SHORT path, for example:  C:\vrm-tool
     (avoid deep folders such as the WeChat download folder -
      Windows breaks on paths longer than 260 characters)
  2. Double-click  Perfect-Sync.bat
     - FULL version: starts right away, everything is bundled.
     - LITE version: if something is missing (Python / Blender /
       VRM add-on), the first-run window offers one-click downloads.
       Missed that window? Click "Set up environment..." at the
       top-right of the app.
  3. In the app:
     - Left  = donor: one model that already has perfect sync
               (ready-made ones are in the samples folder)
     - Right = recipients: your models to process (multi-select OK)
     - Choose an output folder, press Start.
  4. Load the new *_ps.vrm files in your VTuber app. Done!

IMPORTANT - EXPORTING FROM VROID STUDIO
  - Export as VRM 0.0  (VRM 1.0 is rejected)
  - Do NOT enable "Reduce Polygons" or "Delete Transparent Meshes"
    (they change the face and the transfer cannot match it)

MORE HELP
  Full illustrated guide (English + Chinese):
  https://github.com/elainyilanchen/blender-vrm-perfect-sync#readme
