#!/usr/bin/env python3
"""Generate X-Copilot desktop icons using Pillow."""

from pathlib import Path

def generate_icons():
    assets_dir = Path(__file__).parent / "assets"
    assets_dir.mkdir(exist_ok=True)

    # SVG icon
    svg = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">
  <rect width="256" height="256" rx="48" fill="#1a1a2e"/>
  <rect x="32" y="56" width="192" height="144" rx="16" fill="#16213e" stroke="#0f3460" stroke-width="2"/>
  <circle cx="80" cy="96" r="12" fill="#e94560"/>
  <circle cx="128" cy="96" r="12" fill="#e94560"/>
  <circle cx="176" cy="96" r="12" fill="#e94560"/>
  <rect x="56" y="130" width="60" height="8" rx="4" fill="#0f3460"/>
  <rect x="56" y="148" width="100" height="8" rx="4" fill="#0f3460"/>
  <rect x="56" y="166" width="80" height="8" rx="4" fill="#0f3460"/>
  <rect x="140" y="130" width="60" height="8" rx="4" fill="#e94560" opacity="0.5"/>
  <text x="128" y="220" text-anchor="middle" fill="#e0e0e0" font-family="sans-serif" font-size="18" font-weight="bold">X</text>
</svg>
"""
    (assets_dir / "icon.svg").write_text(svg, encoding="utf-8")
    print(f"Written: {assets_dir / 'icon.svg'}")

    # Try Pillow for PNG
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new('RGBA', (256, 256), (26, 26, 46, 255))
        draw = ImageDraw.Draw(img)

        # Rounded rect background
        draw.rounded_rectangle([8, 8, 248, 248], radius=48, fill=(22, 33, 62, 255), outline=(15, 52, 96, 255), width=2)

        # Window dots
        for cx in [80, 128, 176]:
            draw.ellipse([cx-12, 80, cx+12, 104], fill=(233, 69, 96, 255))

        # Text lines
        for y, w in [(130, 60), (148, 100), (166, 80)]:
            draw.rounded_rectangle([56, y, 56+w, y+8], radius=4, fill=(15, 52, 96, 255))

        # Accent line
        draw.rounded_rectangle([140, 130, 200, 138], radius=4, fill=(233, 69, 96, 128))

        # X text
        draw.text((128, 200), "X", fill=(224, 224, 224, 255), anchor="mm", font=None)

        # Save PNG
        img.save(str(assets_dir / "icon.png"))
        print(f"Written: {assets_dir / 'icon.png'}")

        # Save ICO for Windows
        img.save(str(assets_dir / "icon.ico"))
        print(f"Written: {assets_dir / 'icon.ico'}")

    except ImportError:
        print("Pillow not installed — PNG/ICO not generated (SVG is available)")
        print("Install: pip install Pillow")

if __name__ == "__main__":
    generate_icons()