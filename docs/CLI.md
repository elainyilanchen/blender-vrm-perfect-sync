# Command-line usage

The GUI is a wrapper around three headless Blender scripts. You can run them
directly for automation. All commands share this shape:

```
"<path>\blender.exe" --background --python <script.py> -- <args>
```

Requirements: Blender 2.93–4.1 (tested on 4.0.2) with the **VRM format** add-on
enabled, and `numpy` (bundled with Blender's Python).

---

## 1. Transfer perfect sync — `perfect_sync_batch.py`

Copy the 52 ARKit shapes + helper shapes + BlendShapeClip definitions from a
donor onto target models.

**Flat mode** (one folder, one donor):

```
blender --background --python perfect_sync_batch.py -- ^
  --donor "C:\models\donor_perf_sync.vrm" ^
  --input "C:\models\in" --output "C:\models\out"
```

**Per-character mode** — each subfolder of `--input` is one character; a model
that already has 52 keys is auto-detected as that character's donor (filenames
containing `perf_sync` / `donor` win ties); characters without a donor fall back
to `--donor`:

```
blender --background --python perfect_sync_batch.py -- ^
  --per-character --input "C:\characters" --output "C:\characters_ps" ^
  --donor "C:\models\generic_donor.vrm"
```

**Explicit file list** (what the GUI uses):

```
... --donor "donor.vrm" --target "a.vrm" --target "b.vrm" --output "out"
```

Key options:

| Option | Meaning |
|--------|---------|
| `--donor` (repeatable) | Donor(s); matched to targets by face vertex count. Required in flat mode. |
| `--overwrite` | Replace same-named keys/clips with the donor's version (refresh all models after tweaking a donor). |
| `--arkit-only` | Transfer only the 52 ARKit keys (default also copies helper keys). |
| `--include-look` | Also copy LookUp/Down/Left/Right clips (skipped by default). |
| `--suffix` | Output filename suffix (default `_ps`). |
| `--lang zh\|en` | Log language. |
| `--report FILE` | Write a JSON result report (used by the GUI). |

Models that already have all 52 keys are skipped unless `--overwrite`. VRM 1.0
files and faces whose vertex count doesn't match any donor are rejected with a
clear error.

---

## 2. Verify clip bindings — `verify_clips.py`

Confirms every perfect-sync clip (and any intentionally-tuned weights) matches
the donor after transfer. Exit code is non-zero on any mismatch.

```
blender --background --python verify_clips.py -- ^
  --donor "donor_perf_sync.vrm" --file "out\model_ps.vrm" [--file ...]
```

---

## 3. Tune expression weights — `tune_expression.py`

Adjust clip binding weights or shape-key strength without opening Blender's UI.

```
# List clips / bindings / weights
... tune_expression.py -- --file "donor_perf_sync.vrm" --list

# Set a clip's binding weight (auto-backs up to .bak on first in-place save)
... tune_expression.py -- --file "donor_perf_sync.vrm" ^
    --set "BlendShape.BrowDownLeft=0.25"

# Multi-binding clip: name the specific key with CLIP/KEY=W
... --set "BlendShape.MouthPressLeft/_mouthPress+CatMouth=0.3"

# Scale a shape key's displacement (note: this compounds; prefer --set)
... --scale-key "mouthSmileLeft=0.9"
```

Typical loop: tune the **donor**, then re-run `perfect_sync_batch.py --overwrite`
to push the change to every model, then `verify_clips.py` to confirm.
