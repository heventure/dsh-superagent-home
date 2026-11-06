---
name: photo-postprocessing
description: Cull bad shots, develop RAW files, grade, crop, retouch and export shareable photos from the camera backup (DCIM) directory. Use when the user uploads new photos and asks for filtering, RAW development, colour grading, cropping or sharing-ready output.
---

# Photo post-processing

## Setup
- Python venv with `rawpy`, `pillow`, `numpy` (for example `/tmp/photo-venv`, or a persistent venv once the photo directory is known).
- `exiftool` and `ffmpeg` are used for metadata and video frames.
- The photo directory path is configured by the user. Never write into the original RAW/JPEG files; all output goes to a separate `exports/` folder under the date folder.

## Workflow
1. **Inventory**: list new files and read EXIF (`exiftool -j -DateTimeOriginal -ISO -FNumber -ExposureTime <files>`).
2. **Cull**: flag blurred, badly exposed or duplicate frames. Mark them with a `reject/` subfolder listing; move nothing without confirmation.
3. **Develop RAW**: `scripts/develop.py <raw> <out.jpg>` uses `rawpy` with camera white balance and 16-bit processing, then saves a 8-bit sRGB JPEG.
4. **Grade, crop, retouch**: apply the requested adjustments with Pillow/numpy; keep the parameters in a sidecar `.json` next to the export so the edit can be repeated.
5. **Export for sharing**: long edge 2048 px, sRGB, quality 90, EXIF stripped of GPS unless the user asks to keep it.

## Rules
- Never delete originals.
- Report the output paths and any frames rejected, and ask before overwriting an existing export.
