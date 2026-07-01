#!/usr/bin/env python3
"""Generate assets/demo.gif — Sprint 1 GTM placeholder demo animation.

Simulates a Code Review Room Telegram session. Replace with a real screen
recording when VPS/Telegram is available (see docs/plans/demo-gif-storyboard.md).
"""

from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise SystemExit("Install Pillow: pip install pillow")

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "demo.gif"

W, H = 800, 520
BG = (24, 24, 32)
ACCENT = (99, 102, 241)
USER = (59, 130, 246)
CLAUDE = (167, 139, 250)
CODEX = (34, 197, 94)

FRAMES = [
    ("ZeroRelay — Code Review Room", []),
    ("You", "@claude write a 10-line Python email validator"),
    ("Claude", "Done. @codex review for edge cases"),
    ("Codex", "3 issues: intl domains, quoted locals, length check"),
    ("You", "Thanks — shipping it."),
    ("ZeroRelay", "github.com/zeroshotstudio/ZeroRelay"),
]


def load_font(size: int):
    for name in ("Helvetica.ttc", "Arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_frame(title: str, body: str) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    title_font = load_font(22)
    body_font = load_font(18)
    small = load_font(14)

    draw.rounded_rectangle((20, 20, W - 20, H - 20), radius=16, fill=(32, 32, 44), outline=ACCENT, width=2)
    draw.text((40, 36), "ZeroRelay × Telegram", fill=(180, 180, 200), font=small)

    if not body:
        draw.text((40, 200), title, fill=(255, 255, 255), font=title_font)
        draw.text((40, 250), "Group chat for AI agents + cross-model MCP", fill=(160, 160, 180), font=body_font)
        return img

    color = USER
    if title == "Claude":
        color = CLAUDE
    elif title == "Codex":
        color = CODEX
    elif title == "ZeroRelay":
        color = ACCENT

    draw.text((40, 80), title, fill=color, font=title_font)
    y = 120
    for line in _wrap(body, 70):
        draw.text((48, y), line, fill=(230, 230, 240), font=body_font)
        y += 28
    return img


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if len(test) > width:
            if cur:
                lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines or [""]


def main():
    images = []
    for title, body in FRAMES:
        frame = draw_frame(title, body)
        for _ in range(12):  # ~1.2s per slide at 10fps
            images.append(frame.copy())

    OUT.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(
        OUT,
        save_all=True,
        append_images=images[1:],
        duration=100,
        loop=0,
        optimize=True,
    )
    size_kb = OUT.stat().st_size / 1024
    print(f"Wrote {OUT} ({size_kb:.0f} KB)")
    if size_kb > 5120:
        print("Warning: GIF exceeds 5MB — re-export with fewer frames")


if __name__ == "__main__":
    main()
