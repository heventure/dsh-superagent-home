#!/usr/bin/env python3
"""Photo post-processing toolkit for the DCIM camera backup.

Subcommands:
  inventory   count files by type and date folder
  cull        score every image (sharpness, exposure, duplicates) and flag rejects
  sheet       build a JPEG contact sheet for quick review
  develop     RAW/HEIF/JPEG -> graded JPEG (exposure, WB, tone, crop, spots)
  export      resize/sharpen a developed image for sharing

Everything writes outside the originals: nothing in DCIM is modified or deleted.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

try:  # HEIF support is optional at import time so RAW-only use still works
    import pillow_heif

    pillow_heif.register_heif_opener()
except Exception:  # pragma: no cover - dependency guard
    pillow_heif = None

DEFAULT_ROOT = Path(
    os.environ.get("DSH_PHOTO_DCIM", "/vol1/1000/Photos/Photo/camera/A/DCIM")
)
DEFAULT_OUT = Path(
    os.environ.get("DSH_PHOTO_OUT", "/vol1/1000/Photos/Photo/postprocessed")
)

RAW_EXT = {".arw", ".cr2", ".cr3", ".nef", ".nra", ".raf", ".dng", ".orf", ".rw2", ".srw", ".pef", ".raw"}
HEIF_EXT = {".hif", ".heic", ".heif"}
JPEG_EXT = {".jpg", ".jpeg"}
SUPPORTED = RAW_EXT | HEIF_EXT | JPEG_EXT
SKIP_DIRS = {"@eaDir", "#recycle", "reject", "exports", "processed"}
GPS_IFD_TAG = 34853


# --------------------------------------------------------------------------- #
# discovery
# --------------------------------------------------------------------------- #


def iter_images(root: Path, folders: list[str] | None = None):
    """Yield supported image files under root (or only the given sub-folders)."""
    root = Path(root)
    bases = [root / f for f in folders] if folders else [root]
    for base in bases:
        if base.is_file() and base.suffix.lower() in SUPPORTED:
            yield base
            continue
        if not base.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            for name in sorted(filenames):
                if name.startswith("."):
                    continue
                p = Path(dirpath) / name
                if p.suffix.lower() in SUPPORTED and p.is_file():
                    yield p


# --------------------------------------------------------------------------- #
# image loading
# --------------------------------------------------------------------------- #



def _exiftool_tags(path: Path) -> dict[int, object]:
    """Make/Model/Lens/capture time for exports, read with exiftool when present."""
    if shutil.which("exiftool") is None:
        return {}
    try:
        proc = subprocess.run(
            ["exiftool", "-j", "-Make", "-Model", "-LensModel", "-DateTimeOriginal", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        data = json.loads(proc.stdout or "[]")
    except Exception:
        return {}
    if not data:
        return {}
    row = data[0]
    tags: dict[int, object] = {}
    for key, tag in (("Make", 271), ("Model", 272), ("LensModel", 42036), ("DateTimeOriginal", 36867)):
        value = row.get(key)
        if value:
            tags[tag] = str(value)
    return tags


def _raw_thumb(path: Path) -> Image.Image | None:
    import rawpy

    with rawpy.imread(str(path)) as raw:
        try:
            thumb = raw.extract_thumb()
        except Exception:
            return None
        if thumb.format == rawpy.ThumbFormat.JPEG:
            from io import BytesIO

            return ImageOps.exif_transpose(Image.open(BytesIO(thumb.data))).convert("RGB")
        if thumb.format == rawpy.ThumbFormat.BITMAP:
            return Image.fromarray(thumb.data).convert("RGB")
    return None


def load_preview(path: Path, long_edge: int = 1600) -> Image.Image:
    """Cheap RGB preview: embedded RAW thumbnail when available, full decode otherwise."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext in RAW_EXT:
        img = _raw_thumb(path)
        if img is None:
            import rawpy

            with rawpy.imread(str(path)) as raw:
                arr = raw.postprocess(use_camera_wb=True, half_size=True, output_bps=8)
            img = Image.fromarray(arr)
    else:
        img = ImageOps.exif_transpose(Image.open(path))
        img = img.convert("RGB")
    img.thumbnail((long_edge, long_edge), Image.LANCZOS)
    return img


def load_rgb(path: Path) -> tuple[np.ndarray, dict]:
    """Full-resolution float32 RGB in [0, 1] plus source metadata."""
    path = Path(path)
    ext = path.suffix.lower()
    meta: dict = {"file": str(path)}
    if ext in RAW_EXT:
        import rawpy

        with rawpy.imread(str(path)) as raw:
            meta["camera_wb"] = [float(v) for v in raw.camera_whitebalance[:3]]
            meta["size"] = [raw.sizes.width, raw.sizes.height]
            arr16 = raw.postprocess(
                use_camera_wb=True,
                output_bps=16,
                no_auto_bright=True,
                output_color=rawpy.ColorSpace.sRGB,
            )
        arr = arr16.astype(np.float32) / 65535.0
        # rawpy does not rotate; apply the sensor flip so grading happens upright
        flip = int(raw.sizes.flip)
        if flip == 5:
            arr = np.rot90(arr, 1)
        elif flip == 6:
            arr = np.rot90(arr, 3)
        elif flip == 3:
            arr = np.rot90(arr, 2)
        meta["exif"] = _exiftool_tags(path)
    elif ext in HEIF_EXT or ext in JPEG_EXT:
        if ext in HEIF_EXT and pillow_heif is None:
            raise SystemExit("pillow-heif is required to read HEIF files")
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            meta["size"] = list(img.size)
            exif = img.getexif()
            meta["exif"] = {k: v for k, v in exif.items() if k in (271, 272, 305, 36867, GPS_IFD_TAG)}
            arr = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    else:
        raise SystemExit(f"unsupported input: {path}")
    return arr, meta


# --------------------------------------------------------------------------- #
# grading primitives (all operate on float32 [0,1] RGB)
# --------------------------------------------------------------------------- #


def srgb_to_linear(x: np.ndarray) -> np.ndarray:
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)


def linear_to_srgb(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055).astype(np.float32)


def luma(rgb: np.ndarray) -> np.ndarray:
    return (
        0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    ).astype(np.float32)


def apply_exposure_wb(rgb: np.ndarray, ev: float = 0.0, warmth: float = 0.0, tint: float = 0.0) -> np.ndarray:
    """Exposure in stops and simple warm/cool + green/magenta shifts, done in linear light."""
    if ev == 0.0 and warmth == 0.0 and tint == 0.0:
        return rgb
    lin = srgb_to_linear(rgb)
    lin *= np.float32(2.0 ** ev)
    if warmth:
        w = warmth / 100.0
        lin[..., 0] *= np.float32(1.0 + 0.35 * w)
        lin[..., 2] *= np.float32(1.0 - 0.35 * w)
    if tint:
        t = tint / 100.0
        lin[..., 1] *= np.float32(1.0 - 0.30 * t)
    lin = np.clip(lin, 0.0, 1.0)
    return linear_to_srgb(lin)


def apply_tone(rgb: np.ndarray, shadows: float = 0.0, highlights: float = 0.0, contrast: float = 0.0) -> np.ndarray:
    """Shadows lift, highlight recovery and an S-curve, all in gamma space."""
    if shadows == 0.0 and highlights == 0.0 and contrast == 0.0:
        return rgb
    y = luma(rgb)
    out = rgb.copy()
    if shadows:
        mask = np.clip(1.0 - y * 2.0, 0.0, 1.0) ** 2
        gain = (1.0 + 0.55 * shadows)
        out *= (1.0 + (gain - 1.0) * mask)[..., None]
    if highlights:
        mask = np.clip((y - 0.5) * 2.0, 0.0, 1.0) ** 1.5
        gain = (1.0 + 0.45 * highlights)
        out *= (1.0 + (gain - 1.0) * mask)[..., None]
    if contrast:
        c = float(np.clip(contrast, -1.0, 1.0))
        out = np.clip(out, 0.0, 1.0)
        if c >= 0:
            out = 0.5 + (out - 0.5) * (1.0 + 0.9 * c) - 0.5 * c * (out - 0.5) ** 3 * 2.0
        else:
            out = 0.5 + (out - 0.5) * (1.0 + 0.8 * c)
        out = np.clip(out, 0.0, 1.0)
    return out.astype(np.float32)


def apply_saturation(rgb: np.ndarray, saturation: float = 1.0, vibrance: float = 0.0) -> np.ndarray:
    if saturation == 1.0 and vibrance == 0.0:
        return rgb
    y = luma(rgb)[..., None]
    out = y + (rgb - y) * np.float32(saturation)
    if vibrance:
        sat = np.abs(rgb - y).max(axis=2, keepdims=True)
        boost = 1.0 + vibrance * (1.0 - np.clip(sat * 3.0, 0.0, 1.0))
        out = y + (out - y) * boost
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def _to_image(rgb: np.ndarray) -> Image.Image:
    return Image.fromarray((np.clip(rgb, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8))


def _from_image(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0


def apply_detail(rgb: np.ndarray, clarity: float = 0.0, sharpen: float = 0.0, denoise: float = 0.0) -> np.ndarray:
    """Clarity/sharpen are unsharp masks; denoise is a feathered median blend."""
    img = _to_image(rgb)
    if denoise > 0:
        amount = float(np.clip(denoise, 0.0, 1.0))
        smoothed = img.filter(ImageFilter.MedianFilter(3))
        img = Image.blend(img, smoothed, amount * 0.9)
    if clarity > 0:
        radius = max(3, int(min(img.size) * 0.006))
        img = _unsharp(img, radius, clarity * 1.2)
    if sharpen > 0:
        img = _unsharp(img, 1.2, float(np.clip(sharpen, 0.0, 3.0)))
    return _from_image(img)


def _unsharp(img: Image.Image, radius: float, amount: float) -> Image.Image:
    if amount <= 0:
        return img
    arr = np.asarray(img, dtype=np.float32)
    blurred = np.asarray(img.filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32)
    out = np.clip(arr + (arr - blurred) * amount, 0.0, 255.0)
    return Image.fromarray(out.astype(np.uint8))


def crop_aspect(rgb: np.ndarray, aspect: float | None, crop: tuple[float, float, float, float] | None) -> np.ndarray:
    h, w = rgb.shape[:2]
    if crop:
        l, t, r, b = [float(np.clip(v, 0.0, 1.0)) for v in crop]
        x0, x1 = int(l * w), int(r * w)
        y0, y1 = int(t * h), int(b * h)
    else:
        x0, y0, x1, y1 = 0, 0, w, h
    if aspect:
        cw, ch = x1 - x0, y1 - y0
        target = aspect
        if cw / ch > target:
            nw = int(ch * target)
            x0 += (cw - nw) // 2
            x1 = x0 + nw
        else:
            nh = int(cw / target)
            y0 += (ch - nh) // 2
            y1 = y0 + nh
    if (x0, y0, x1, y1) == (0, 0, w, h):
        return rgb
    return rgb[y0:y1, x0:x1]


def rotate_flip(rgb: np.ndarray, angle: float = 0.0, flip: str | None = None) -> np.ndarray:
    img = _to_image(rgb)
    if flip == "h":
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    elif flip == "v":
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    if angle:
        img = img.rotate(-angle, resample=Image.BICUBIC, expand=False)
    return _from_image(img)


def remove_spots(rgb: np.ndarray, spots: list[tuple[int, int, int, int, int]]) -> np.ndarray:
    """Clone-stamp style spot removal: (x, y, radius, src_x, src_y) in source pixels."""
    out = rgb.copy()
    h, w = rgb.shape[:2]
    for x, y, r, sx, sy in spots:
        r = max(1, int(r))
        x0, x1 = max(0, x - r), min(w, x + r)
        y0, y1 = max(0, y - r), min(h, y + r)
        sw, sh = x1 - x0, y1 - y0
        dx0, dy0 = max(0, sx - r), max(0, sy - r)
        patch = rgb[dy0 : dy0 + sh, dx0 : dx0 + sw]
        if patch.shape[:2] != (sh, sw):
            continue
        yy, xx = np.mgrid[0:sh, 0:sw]
        dist = np.sqrt((xx - (x - x0)) ** 2 + (yy - (y - y0)) ** 2) / max(1.0, float(r))
        mask = np.clip(1.0 - dist, 0.0, 1.0)[..., None]
        mask = (mask ** 0.6).astype(np.float32)
        region = out[y0:y1, x0:x1]
        out[y0:y1, x0:x1] = region * (1.0 - mask) + patch * mask
    return out


# --------------------------------------------------------------------------- #
# scoring
# --------------------------------------------------------------------------- #


def _tile_sharpness(gray: np.ndarray, tiles: int = 6) -> float:
    """90th percentile of per-tile Laplacian variance: rewards any in-focus area.

    A shallow depth-of-field shot with a crisp subject still scores high, while a
    frame that is soft everywhere (defocus or motion blur) scores low.
    """
    h, w = gray.shape
    values = []
    for ty in range(tiles):
        for tx in range(tiles):
            y0, y1 = h * ty // tiles, h * (ty + 1) // tiles
            x0, x1 = w * tx // tiles, w * (tx + 1) // tiles
            if y1 - y0 < 8 or x1 - x0 < 8:
                continue
            values.append(_laplacian_variance(gray[y0:y1, x0:x1]))
    return float(np.percentile(values, 90)) if values else 0.0


def _laplacian_variance(gray: np.ndarray) -> float:
    g = gray.astype(np.float32)
    lap = (
        -4.0 * g
        + np.roll(g, 1, 0)
        + np.roll(g, -1, 0)
        + np.roll(g, 1, 1)
        + np.roll(g, -1, 1)
    )[1:-1, 1:-1]
    return float(lap.var())


def _dhash(img: Image.Image, size: int = 16) -> int:
    small = img.convert("L").resize((size + 1, size), Image.LANCZOS)
    px = np.asarray(small, dtype=np.int16)
    bits = (px[:, 1:] > px[:, :-1]).flatten()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return value


def score_image(path: Path, preview_edge: int = 1120, thumb_path: Path | None = None) -> dict:
    try:
        img = load_preview(path, preview_edge)
    except Exception as exc:  # unreadable file is itself a cull signal
        return {"file": str(path), "error": str(exc), "flags": ["unreadable"]}
    if thumb_path is not None:
        try:
            thumb = img.copy()
            thumb.thumbnail((360, 360), Image.LANCZOS)
            thumb.save(thumb_path, "JPEG", quality=85)
        except Exception:
            pass
    gray = np.asarray(img.convert("L"), dtype=np.float32) / 255.0
    sharpness = _tile_sharpness(gray)
    mean = float(gray.mean())
    p_black = float((gray < 0.02).mean())
    p_white = float((gray > 0.98).mean())
    return {
        "file": str(path),
        "folder": path.parent.name,
        "name": path.name,
        "size": list(img.size),
        "sharpness": round(sharpness, 5),
        "mean": round(mean, 4),
        "clip_black": round(p_black, 4),
        "clip_white": round(p_white, 4),
        "dhash": _dhash(img),
        "flags": [],
    }


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _score_pair(item) -> dict:
    path, thumb = item
    return score_image(path, 1120, thumb)


def _score_all(files: list[Path], jobs: int, thumb_dir: Path | None = None) -> list[dict]:
    if thumb_dir is not None:
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumbs = [thumb_dir / f"{i:05d}.jpg" for i in range(len(files))]
    else:
        thumbs = [None] * len(files)
    items = list(zip(files, thumbs))
    if jobs > 1 and len(files) > 4:
        import multiprocessing as mp
        from concurrent.futures import ProcessPoolExecutor

        # rawpy/OpenMP deadlocks with fork; spawn workers instead.
        if mp.get_start_method(allow_none=True) != "spawn":
            mp.set_start_method("spawn", force=True)
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            return [rec for rec in pool.map(_score_pair, items, chunksize=2)]
    return [_score_pair(item) for item in items]


def cull(
    root: Path,
    out_dir: Path,
    folders: list[str] | None,
    limit: int | None,
    dup_distance: int = 10,
    jobs: int = 1,
    thumb_dir: Path | None = None,
) -> dict:
    files = list(iter_images(root, folders))
    if limit:
        files = files[:limit]
    records = _score_all(files, jobs, thumb_dir)

    ok = [r for r in records if "error" not in r]
    sharp_values = sorted(r["sharpness"] for r in ok)
    median_sharp = sharp_values[len(sharp_values) // 2] if sharp_values else 0.0
    for i, rec in enumerate(ok):
        flags = rec["flags"]
        if median_sharp and rec["sharpness"] < 0.15 * median_sharp:
            flags.append("blurry")
        if rec["mean"] < 0.08:
            flags.append("dark")
        if rec["mean"] > 0.92:
            flags.append("bright")
        if rec["clip_white"] > 0.08:
            flags.append("blown")
        if rec["clip_black"] > 0.35:
            flags.append("crushed")
        for prev in ok[:i]:
            if (
                prev["folder"] == rec["folder"]
                and hamming(prev["dhash"], rec["dhash"]) <= dup_distance
                and abs(prev["mean"] - rec["mean"]) < 0.04
            ):
                flags.append("duplicate")
                rec["duplicate_of"] = prev["name"]
                break

    out_dir.mkdir(parents=True, exist_ok=True)
    rejected = [r for r in records if r["flags"]]
    report = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "root": str(root),
        "count": len(records),
        "rejected": len(rejected),
        "median_sharpness": round(median_sharp, 5),
        "images": records,
    }
    (out_dir / "cull_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    with (out_dir / "cull_report.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["file", "sharpness", "mean", "clip_black", "clip_white", "flags", "duplicate_of"],
            extrasaction="ignore",
        )
        writer.writeheader()
        for rec in records:
            row = dict(rec)
            row["flags"] = ",".join(rec.get("flags", []))
            writer.writerow(row)
    return report


# --------------------------------------------------------------------------- #
# outputs
# --------------------------------------------------------------------------- #


def save_jpeg(img: Image.Image, dst: Path, quality: int, long_edge: int | None, strip_gps: bool, keep_meta: dict | None) -> None:
    if long_edge and max(img.size) > long_edge:
        img = img.copy()
        img.thumbnail((long_edge, long_edge), Image.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    exif = None
    if keep_meta:
        exif = Image.Exif()
        for tag, value in keep_meta.items():
            if strip_gps and int(tag) == GPS_IFD_TAG:
                continue
            try:
                exif[int(tag)] = value
            except Exception:
                pass
    kwargs = {"quality": quality, "optimize": True}
    if exif is not None:
        kwargs["exif"] = exif
    img.save(dst, "JPEG", **kwargs)


def make_sheet(files: list[Path], dst: Path, cols: int = 6, cell: int = 320, labels: bool = True) -> Path:
    return make_sheet_with_labels([(f, f.name) for f in files], dst, cols, cell, labels)


def make_sheet_with_labels(items: list[tuple[Path, str]], dst: Path, cols: int = 6, cell: int = 320, labels: bool = True) -> Path:
    if not items:
        raise SystemExit("no images for contact sheet")
    thumbs = []
    for path, label in items:
        try:
            img = load_preview(path, cell)
        except Exception:
            continue
        canvas = Image.new("RGB", (cell, cell), (24, 24, 24))
        img.thumbnail((cell - 8, cell - 8), Image.LANCZOS)
        canvas.paste(img, ((cell - img.width) // 2, (cell - img.height) // 2))
        if labels:
            draw = ImageDraw.Draw(canvas)
            draw.text((6, cell - 18), label[:34], fill=(235, 235, 235))
        thumbs.append(canvas)
    rows = math.ceil(len(thumbs) / cols)
    sheet = Image.new("RGB", (cols * cell, rows * cell), (16, 16, 16))
    for i, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((i % cols) * cell, (i // cols) * cell))
    dst.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dst, "JPEG", quality=88, optimize=True)
    return dst


# --------------------------------------------------------------------------- #
# subcommands
# --------------------------------------------------------------------------- #


def cmd_inventory(args) -> int:
    root = Path(args.root)
    files = list(iter_images(root, args.folders))
    by_ext: dict[str, int] = {}
    by_folder: dict[str, int] = {}
    total_bytes = 0
    for path in files:
        ext = path.suffix.lower()
        by_ext[ext] = by_ext.get(ext, 0) + 1
        by_folder[path.parent.name] = by_folder.get(path.parent.name, 0) + 1
        total_bytes += path.stat().st_size
    print(f"root: {root}")
    print(f"images: {len(files)}  size: {total_bytes / 1e9:.1f} GB  folders: {len(by_folder)}")
    for ext, count in sorted(by_ext.items(), key=lambda kv: -kv[1]):
        print(f"  {ext}: {count}")
    if args.by_folder:
        for folder, count in sorted(by_folder.items()):
            print(f"  {folder}: {count}")
    return 0


def cmd_cull(args) -> int:
    out_dir = Path(args.out) if args.out else DEFAULT_OUT / "_cull" / datetime.now().strftime("%Y%m%d-%H%M%S")
    thumb_dir = out_dir / ".thumbs" if args.sheet else None
    report = cull(Path(args.root), out_dir, args.folders, args.limit, args.dup_distance, args.jobs, thumb_dir)
    rejected = [r for r in report["images"] if r.get("flags")]
    print(f"scored {report['count']} images, flagged {len(rejected)}")
    for rec in rejected[:40]:
        print(f"  [{','.join(rec['flags'])}] {rec.get('name', rec.get('file'))}")
    print(f"report: {out_dir / 'cull_report.json'}")
    if args.sheet and rejected:
        index = {r["file"]: i for i, r in enumerate(report["images"])}
        pairs = [
            (thumb_dir / f"{index[r['file']]:05d}.jpg", Path(r["file"]).name)
            for r in rejected
            if r.get("file") in index and (thumb_dir / f"{index[r['file']]:05d}.jpg").exists()
        ]
        if pairs:
            sheet = make_sheet_with_labels(pairs, out_dir / "rejects.jpg", cols=args.sheet_cols)
            print(f"rejects sheet: {sheet}")
    return 0


def build_pipeline(args) -> tuple[np.ndarray, dict]:
    rgb, meta = load_rgb(Path(args.input))
    meta["params"] = {
        "ev": args.ev,
        "warmth": args.warmth,
        "tint": args.tint,
        "shadows": args.shadows,
        "highlights": args.highlights,
        "contrast": args.contrast,
        "saturation": args.saturation,
        "vibrance": args.vibrance,
        "clarity": args.clarity,
        "sharpen": args.sharpen,
        "denoise": args.denoise,
        "crop": args.crop,
        "aspect": args.aspect,
        "rotate": args.rotate,
        "flip": args.flip,
        "spots": args.spot,
    }
    if args.spot:
        rgb = remove_spots(rgb, parse_spots(args.spot))
    rgb = rotate_flip(rgb, args.rotate, args.flip)
    rgb = crop_aspect(rgb, args.aspect, args.crop)
    rgb = apply_exposure_wb(rgb, args.ev, args.warmth, args.tint)
    rgb = apply_tone(rgb, args.shadows, args.highlights, args.contrast)
    rgb = apply_saturation(rgb, args.saturation, args.vibrance)
    rgb = apply_detail(rgb, args.clarity, args.sharpen, args.denoise)
    return rgb, meta


def parse_spots(specs: list[str]) -> list[tuple[int, int, int, int, int]]:
    spots = []
    for spec in specs:
        parts = [int(float(v)) for v in spec.replace(" ", "").split(",")]
        if len(parts) == 3:
            x, y, r = parts
            sx, sy = x + r + 2, y
        elif len(parts) == 5:
            x, y, r, sx, sy = parts
        else:
            raise SystemExit(f"bad --spot value: {spec}")
        spots.append((x, y, r, sx, sy))
    return spots


def cmd_develop(args) -> int:
    src = Path(args.input)
    rgb, meta = build_pipeline(args)
    img = _to_image(rgb)
    if args.out:
        dst = Path(args.out)
    else:
        stem = src.stem + (args.suffix or "_edit")
        dst = (Path(args.out_dir) if args.out_dir else DEFAULT_OUT / datetime.now().strftime("%Y-%m-%d")) / (stem + ".jpg")
    if dst.exists() and not args.force:
        raise SystemExit(f"refusing to overwrite {dst} (use --force)")
    save_jpeg(img, dst, args.quality, args.long_edge, not args.keep_gps, meta.get("exif"))
    sidecar = dst.with_suffix(".json")
    sidecar.write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str))
    print(f"wrote {dst} {img.width}x{img.height} -> {Image.open(dst).size}")
    print(f"sidecar {sidecar}")
    return 0


def cmd_export(args) -> int:
    src = Path(args.input)
    img = Image.open(src)
    img = img.convert("RGB")
    if args.border:
        w, h = img.size
        b = int(min(w, h) * args.border)
        canvas = Image.new("RGB", (w + 2 * b, h + 2 * b), tuple(args.border_color))
        canvas.paste(img, (b, b))
        img = canvas
    if args.watermark:
        draw = ImageDraw.Draw(img)
        text = args.watermark
        tw = draw.textlength(text)
        draw.text((img.width - tw - 24, img.height - 40), text, fill=(255, 255, 255))
    dst = Path(args.out)
    if dst.exists() and not args.force:
        raise SystemExit(f"refusing to overwrite {dst} (use --force)")
    save_jpeg(img, dst, args.quality, args.long_edge, not args.keep_gps, None)
    print(f"wrote {dst} {Image.open(dst).size}")
    return 0


def cmd_sheet(args) -> int:
    files = list(iter_images(Path(args.root), args.folders))
    if args.limit:
        files = files[: args.limit]
    dst = Path(args.out) if args.out else DEFAULT_OUT / "_cull" / "sheet.jpg"
    out = make_sheet(files, dst, args.cols, args.cell, not args.no_labels)
    print(f"wrote {out} from {len(files)} images")
    return 0


# --------------------------------------------------------------------------- #
# cli
# --------------------------------------------------------------------------- #


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("inventory", help="count files by type and folder")
    p.add_argument("--root", default=str(DEFAULT_ROOT))
    p.add_argument("--folders", nargs="*", help="limit to date folders, e.g. 11841020")
    p.add_argument("--by-folder", action="store_true")
    p.set_defaults(func=cmd_inventory)

    p = sub.add_parser("cull", help="score images and flag rejects")
    p.add_argument("--root", default=str(DEFAULT_ROOT))
    p.add_argument("--folders", nargs="*")
    p.add_argument("--out", help="report directory (default: <out root>/_cull/<timestamp>)")
    p.add_argument("--limit", type=int)
    p.add_argument("--dup-distance", type=int, default=10, help="256-bit dHash distance treated as a duplicate")
    p.add_argument("--jobs", type=int, default=1, help="parallel workers (each ~1 GB RAM)")
    p.add_argument("--sheet", action="store_true", help="also render a contact sheet of rejects")
    p.add_argument("--sheet-cols", type=int, default=6)
    p.set_defaults(func=cmd_cull)

    p = sub.add_parser("sheet", help="contact sheet for review")
    p.add_argument("--root", default=str(DEFAULT_ROOT))
    p.add_argument("--folders", nargs="*")
    p.add_argument("--out")
    p.add_argument("--limit", type=int, default=36)
    p.add_argument("--cols", type=int, default=6)
    p.add_argument("--cell", type=int, default=320)
    p.add_argument("--no-labels", action="store_true")
    p.set_defaults(func=cmd_sheet)

    for name, func in (("develop", cmd_develop), ("export", cmd_export)):
        p = sub.add_parser(name, help="grade a RAW/HEIF/JPEG" if name == "develop" else "finish a JPEG for sharing")
        p.add_argument("input")
        p.add_argument("--out")
        p.add_argument("--out-dir", default=str(DEFAULT_OUT))
        p.add_argument("--quality", type=int, default=92)
        p.add_argument("--long-edge", type=int, default=None if name == "export" else 2048)
        p.add_argument("--keep-gps", action="store_true")
        p.add_argument("--force", action="store_true")
        if name == "develop":
            p.add_argument("--suffix", default="_edit")
            p.add_argument("--ev", type=float, default=0.0)
            p.add_argument("--warmth", type=float, default=0.0, help="-100..100, positive = warmer")
            p.add_argument("--tint", type=float, default=0.0, help="-100..100, positive = magenta")
            p.add_argument("--shadows", type=float, default=0.0, help="-1..1")
            p.add_argument("--highlights", type=float, default=0.0, help="-1..1, negative recovers")
            p.add_argument("--contrast", type=float, default=0.0, help="-1..1")
            p.add_argument("--saturation", type=float, default=1.0)
            p.add_argument("--vibrance", type=float, default=0.0)
            p.add_argument("--clarity", type=float, default=0.0)
            p.add_argument("--sharpen", type=float, default=0.4)
            p.add_argument("--denoise", type=float, default=0.0)
            p.add_argument("--crop", type=float, nargs=4, metavar=("L", "T", "R", "B"), help="fractions 0..1")
            p.add_argument("--aspect", type=float, help="e.g. 1.5 for 3:2")
            p.add_argument("--rotate", type=float, default=0.0, help="degrees, positive = clockwise")
            p.add_argument("--flip", choices=["h", "v"])
            p.add_argument("--spot", action="append", help="x,y,r[,sx,sy] clone-stamp spot removal")
        else:
            p.add_argument("--border", type=float, default=0.0, help="border fraction, e.g. 0.02")
            p.add_argument("--border-color", type=int, nargs=3, default=[255, 255, 255])
            p.add_argument("--watermark")
        p.set_defaults(func=func)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
