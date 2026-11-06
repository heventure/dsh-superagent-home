"""Develop a RAW file to an sRGB JPEG for sharing.

Usage: python develop.py <input.raw> <output.jpg> [--long-edge 2048] [--quality 90]
"""

import argparse
import sys

import numpy as np
import rawpy
from PIL import Image


def develop(src, dst, long_edge=2048, quality=90):
    with rawpy.imread(src) as raw:
        # Camera white balance, 16-bit output, no auto-brightness to keep exposure predictable.
        rgb = raw.postprocess(
            use_camera_wb=True,
            output_bps=16,
            no_auto_bright=True,
            output_color=rawpy.ColorSpace.sRGB,
        )
    img = Image.fromarray((rgb / 256).astype(np.uint8))
    img.thumbnail((long_edge, long_edge), Image.LANCZOS)
    img.save(dst, "JPEG", quality=quality, optimize=True)
    return img.size


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("src")
    parser.add_argument("dst")
    parser.add_argument("--long-edge", type=int, default=2048)
    parser.add_argument("--quality", type=int, default=90)
    args = parser.parse_args(argv)
    size = develop(args.src, args.dst, args.long_edge, args.quality)
    print(f"wrote {args.dst} {size[0]}x{size[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
