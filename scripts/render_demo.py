"""Render an honest data-summary GIF, not a browser screenshot.

Optional documentation tool: pip install Pillow
Usage: python scripts/render_demo.py
The simulator and offline HTML have no dependency on this tool.
"""

from pathlib import Path
import argparse
import json
import math

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
COLORS = {"aegis": "#a4f5cb", "unhedged": "#b8a2e9", "symmetric": "#e9c881", "delayed": "#8dbdd8"}
BG, PANEL, LINE, TEXT, MUTED, RED = "#081111", "#0d1819", "#203233", "#e5eeeb", "#819694", "#fa9295"


def font(size: int, mono: bool = False):
    names = ("DejaVuSansMono.ttf", "Consolas.ttf") if mono else ("DejaVuSans.ttf", "Arial.ttf")
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def money(value: float, decimals: int = 0) -> str:
    return ("−" if value < 0 else "") + f"${abs(value):,.{decimals}f}"


def render(data: dict, experiment: dict, index: int) -> Image.Image:
    image = Image.new("RGB", (1000, 590), BG)
    draw = ImageDraw.Draw(image)
    runs = experiment["runs"]
    selected = runs[0]["snapshots"][index]
    ms = selected["ms"]
    end = max(run["snapshots"][-1]["ms"] for run in runs)
    values = [s["pnl"] for run in runs for s in run["snapshots"]]
    lo, hi = min(0, min(values)), max(0, max(values))
    pad = max(20, (hi - lo) * 0.1)
    lo, hi = lo - pad, hi + pad
    left, right, top, bottom = 88, 954, 228, 452
    x = lambda timestamp: left + timestamp / end * (right - left)
    y = lambda value: top + (hi - value) / (hi - lo) * (bottom - top)

    draw.text((30, 22), "AEGIS", font=font(24), fill=COLORS["aegis"])
    draw.text((151, 29), "OPTIONS MARKET MICROSTRUCTURE LAB", font=font(11, True), fill=MUTED)
    draw.rounded_rectangle((801, 21, 970, 50), radius=4, outline="#365d48", fill="#14291f")
    draw.text((815, 30), "SYNTHETIC DATA", font=font(11, True), fill=COLORS["aegis"])
    draw.line((30, 67, 970, 67), fill=LINE)
    draw.text((30, 82), "Between signal and fill, everything can change.", font=font(23), fill=TEXT)
    draw.text((30, 119), f"SEED {data['seed']}  /  VOLATILITY SHOCK  /  EXPORTED DATA SUMMARY", font=font(10, True), fill=MUTED)

    delta = selected["risk_exposure"]["delta"]
    metrics = (("AEGIS MARKED P&L", money(selected["pnl"], 2)),
               ("SPOT / IMPLIED VOL", f"${selected['spot']:.2f} / {selected['iv'] * 100:.1f}%"),
               ("OBSERVED NET DELTA", f"{delta:+,.0f} shares"),
               ("RISK STATE", selected["state"].replace("_", " ")))
    for number, (label, value) in enumerate(metrics):
        origin = 30 + 238 * number
        draw.rounded_rectangle((origin, 146, origin + 226, 207), radius=6, fill=PANEL, outline=LINE)
        draw.text((origin + 13, 157), label, font=font(9, True), fill=MUTED)
        color = RED if number == 3 and selected["state"] == "DRAWDOWN" else TEXT
        draw.text((origin + 13, 178), value, font=font(17 if number != 3 else 15, True), fill=color)

    draw.rectangle((x(data["ticks"] * 500), top, right, bottom), fill="#172021")
    for grid in range(5):
        value = lo + (hi - lo) * grid / 4
        height = y(value)
        draw.line((left, height, right, height), fill=LINE)
        label = money(value)
        draw.text((left - 13, height), label, font=font(10, True), fill=MUTED, anchor="rm")
    shock = x(data["ticks"] * 500)
    for height in range(top, bottom, 10):
        draw.line((shock, height, shock, height + 4), fill="#99716e")
    draw.text((shock + 10, top + 9), "SPOT −4% / IV +18 POINTS", font=font(10, True), fill=RED)
    for run in reversed(runs):
        points = [(x(s["ms"]), y(s["pnl"])) for s in run["snapshots"] if s["ms"] <= ms]
        if len(points) > 1:
            draw.line(points, fill=COLORS[run["policy"]["name"]], width=3 if run["policy"]["name"] == "aegis" else 2)
    cursor = x(ms)
    draw.line((cursor, top, cursor, bottom), fill="#c2d3c8")
    cy = y(selected["pnl"])
    draw.ellipse((cursor - 4, cy - 4, cursor + 4, cy + 4), fill=COLORS["aegis"])
    for n in range(6):
        timestamp = data["ticks"] * 1000 * n / 5
        seconds = int(timestamp / 1000)
        draw.text((x(timestamp), bottom + 11), f"{seconds // 60:02d}:{seconds % 60:02d}", font=font(10, True), fill=MUTED, anchor="mt")

    for number, run in enumerate(runs):
        origin = 40 + number * 238
        eligible = [s for s in run["snapshots"] if s["ms"] <= ms]
        last = eligible[-1]
        draw.ellipse((origin, 493, origin + 6, 499), fill=COLORS[run["policy"]["name"]])
        draw.text((origin + 14, 490), run["policy"]["label"], font=font(11), fill=TEXT)
        draw.text((origin + 14, 509), money(last["pnl"]), font=font(12, True), fill=COLORS[run["policy"]["name"]])

    draw.line((30, 537, 970, 537), fill=LINE)
    message = "Quotes use delayed observations; resting and in-flight orders still reserve risk."
    if ms >= data["ticks"] * 500:
        message = "The loss latch blocks new orders. Delayed cancels drain; inventory stays exposed."
    draw.text((30, 550), message, font=font(12), fill=MUTED)
    seconds = int(ms / 1000)
    draw.text((970, 550), f"{seconds // 60:02d}:{seconds % 60:02d}", font=font(12, True), fill=TEXT, anchor="rt")
    return image


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", type=Path, default=ROOT / "artifacts/replay.json")
    parser.add_argument("--out", type=Path, default=ROOT / "docs")
    args = parser.parse_args()
    data = json.loads(args.replay.read_text())
    experiment = next(exp for exp in data["experiments"] if exp["scenario"] == "vol_shock")
    count = len(experiment["runs"][0]["snapshots"])
    fractions = [0, .08, .16, .24, .32, .4, .44, .46, .48, .49, .50, .51, .52, .55, .6, .68, .76, .84, .92, 1]
    indices = sorted({min(count - 1, math.floor((count - 1) * f)) for f in fractions})
    frames = [render(data, experiment, index) for index in indices]
    args.out.mkdir(parents=True, exist_ok=True)
    # Use one palette across frames so chart colors remain stable.
    palette = frames[-1].quantize(colors=128)
    gif_frames = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    durations = [420] * len(frames)
    durations[0], durations[-1] = 900, 1600
    gif_frames[0].save(args.out / "replay.gif", save_all=True, append_images=gif_frames[1:], duration=durations, loop=0, optimize=False, disposal=2)
    preview_index = next(i for i, index in enumerate(indices) if experiment['runs'][0]['snapshots'][index]['ms'] >= data['ticks'] * 500)
    frames[preview_index].save(args.out / "preview.png")
    print(f"Rendered {len(frames)} frames: {args.out / 'replay.gif'}")


if __name__ == "__main__":
    main()
