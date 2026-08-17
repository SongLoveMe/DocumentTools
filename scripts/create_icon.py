from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    root = Path(__file__).parents[1]
    assets = root / "assets"
    assets.mkdir(exist_ok=True)
    size = 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((18, 18, 238, 238), radius=42, fill="#eef5ff", outline="#b9d3f5", width=5)
    draw.rounded_rectangle((57, 48, 191, 205), radius=12, fill="#ffffff", outline="#2463eb", width=7)
    draw.line((83, 88, 166, 88), fill="#94a3b8", width=8)
    draw.line((83, 115, 166, 115), fill="#94a3b8", width=8)
    draw.line((83, 142, 146, 142), fill="#94a3b8", width=8)
    draw.polygon([(145, 158), (218, 158), (218, 181), (145, 181)], fill="#2463eb")
    draw.polygon([(145, 150), (132, 170), (145, 190)], fill="#2463eb")
    image.save(assets / "documenttools.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    main()
