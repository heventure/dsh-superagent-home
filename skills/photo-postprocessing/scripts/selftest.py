#!/usr/bin/env python3
"""Self-check for the photo toolkit. Runs on synthetic images, no photo library needed.

Usage: python scripts/selftest.py
Exit code 0 means every check passed.
"""

import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import photo  # noqa: E402

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'ok  ' if cond else 'FAIL'} {name}{(' — ' + detail) if detail and not cond else ''}")
    if not cond:
        FAILS.append(name)


def gradient(w: int = 240, h: int = 160) -> np.ndarray:
    x = np.linspace(0.05, 0.95, w, dtype=np.float32)[None, :]
    y = np.linspace(0.2, 0.8, h, dtype=np.float32)[:, None]
    base = (x * 0.6 + y * 0.4).astype(np.float32)
    rgb = np.stack([base, base * 0.9, base * 0.8], axis=-1)
    return np.clip(rgb, 0.0, 1.0)


def main() -> int:
    rgb = gradient()

    brighter = photo.apply_exposure_wb(rgb, ev=1.0)
    check("exposure raises luminance", photo.luma(brighter).mean() > photo.luma(rgb).mean() + 0.05)

    warm = photo.apply_exposure_wb(rgb, warmth=60)
    check("warmth increases red/blue ratio",
          warm[..., 0].mean() / max(1e-6, warm[..., 2].mean()) > rgb[..., 0].mean() / rgb[..., 2].mean())

    lifted = photo.apply_tone(rgb, shadows=0.8)
    check("shadows lift dark pixels", lifted.min() > rgb.min())
    recovered = photo.apply_tone(np.clip(rgb * 1.6, 0, 1), highlights=-0.8)
    check("highlight recovery lowers peaks", recovered.max() <= 1.0 and recovered.mean() < np.clip(rgb * 1.6, 0, 1).mean())

    contrasty = photo.apply_tone(rgb, contrast=0.6)
    check("contrast changes spread", abs(float(contrasty.std()) - float(rgb.std())) > 0.005)

    saturated = photo.apply_saturation(rgb, 1.0, 0.0)
    check("saturation 1.0 is a no-op", np.allclose(saturated, rgb, atol=1e-5))

    cropped = photo.crop_aspect(rgb, 1.0, None)
    check("aspect crop produces square", cropped.shape[0] == cropped.shape[1], str(cropped.shape))

    cropped2 = photo.crop_aspect(rgb, None, (0.25, 0.0, 0.75, 1.0))
    check("fractional crop halves width", cropped2.shape[1] == rgb.shape[1] // 2, str(cropped2.shape))

    rotated = photo.rotate_flip(rgb, flip="h")
    check("flip mirrors pixels", np.allclose(rotated[:, ::-1], rgb, atol=0.01))

    dotted = rgb.copy()
    dotted[60:80, 60:80] = 0.0
    cleaned = photo.remove_spots(dotted, [(70, 70, 14, 120, 70)])
    check("spot removal fills the dot", cleaned[70, 70].mean() > 0.1, str(cleaned[70, 70]))

    sharp = np.zeros((160, 240, 3), dtype=np.uint8)
    sharp[40:120, 60:180] = 255
    soft = np.asarray(Image.fromarray(sharp).filter(ImageFilter.GaussianBlur(6)))
    sharp_score = photo._tile_sharpness(sharp[..., 0].astype(np.float32) / 255)
    soft_score = photo._tile_sharpness(soft[..., 0].astype(np.float32) / 255)
    check("sharpness separates sharp and blurred", sharp_score > soft_score * 3, f"{sharp_score:.3f} vs {soft_score:.3f}")

    img_a = Image.fromarray((rgb * 255).astype(np.uint8))
    img_b = img_a.copy()
    rng = np.random.default_rng(7)
    noisy = rng.random(rgb.shape).astype(np.float32)
    img_c = Image.fromarray((noisy * 255).astype(np.uint8))
    h_a, h_b, h_c = photo._dhash(img_a), photo._dhash(img_b), photo._dhash(img_c)
    check("dhash identical", photo.hamming(h_a, h_b) == 0)
    check("dhash differs for different image", photo.hamming(h_a, h_c) > 10, str(photo.hamming(h_a, h_c)))

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / "a.jpg"
        img_a.save(src, quality=95)
        out = tmp / "out.jpg"
        photo.save_jpeg(img_a, out, 90, 120, True, None)
        check("jpeg export respects long edge", max(Image.open(out).size) == 120, str(Image.open(out).size))
        solo = tmp / "solo"
        solo.mkdir()
        img_a.save(solo / "b.jpg", quality=95)
        report = photo.cull(solo, tmp / "cull", None, None, 10, 1)
        check("cull reports the image", report["count"] == 1, str(report["count"]))
        sheet = photo.make_sheet([src], tmp / "sheet.jpg", cols=2, cell=120)
        check("sheet written", sheet.exists() and Image.open(sheet).size[0] == 240, str(Image.open(sheet).size))

        dst = tmp / "dev.jpg"
        sys.argv = [
            "photo.py", "develop", str(src), "--out", str(dst),
            "--ev", "0.2", "--crop", "0.1", "0.1", "0.9", "0.9",
            "--aspect", "1.0", "--long-edge", "100", "--force",
        ]
        photo.main(sys.argv[1:])
        check("develop writes jpeg", dst.exists() and dst.with_suffix(".json").exists())
        check("develop output is square", Image.open(dst).width == Image.open(dst).height)

    if FAILS:
        print(f"\n{len(FAILS)} check(s) failed: {', '.join(FAILS)}")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
