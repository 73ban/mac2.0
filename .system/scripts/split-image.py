#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def split_image(path: Path, output_dir: Path | None, parts: int) -> list[Path]:
    path = path.expanduser().resolve()
    out_dir = (output_dir.expanduser().resolve() if output_dir else path.parent)
    out_dir.mkdir(parents=True, exist_ok=True)

    image = Image.open(path)
    width, height = image.size
    strip_height = height // parts
    outputs: list[Path] = []

    for index in range(parts):
        top = index * strip_height
        bottom = (index + 1) * strip_height if index < parts - 1 else height
        strip = image.crop((0, top, width, bottom))
        out_path = out_dir / f"{path.stem}_strip_{index + 1:02d}.png"
        strip.save(out_path)
        outputs.append(out_path)
        print(f"Saved {out_path} ({top}-{bottom})")
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="把长图按横向分段切成 PNG，方便 OCR 或人工阅读。")
    parser.add_argument("image", help="本机图片路径")
    parser.add_argument("--output-dir", help="输出目录；默认写到原图目录")
    parser.add_argument("--parts", type=int, default=4, help="切分段数，默认 4")
    args = parser.parse_args()

    if args.parts <= 0:
        raise ValueError("--parts 必须大于 0")
    split_image(Path(args.image), Path(args.output_dir) if args.output_dir else None, args.parts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
