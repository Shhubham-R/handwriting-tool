import json
import math
import random
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import svgwrite

from style_presets import PRESET_STYLES

Point = Tuple[float, float]
Stroke = List[Point]


DEFAULT_STYLE = {
    "name": "default",
    "sample_text": "",
    "slant_degrees": -6.0,
    "stroke_width": 2.2,
    "letter_spacing": 0.0,
    "word_spacing": 16.0,
    "baseline_jitter": 2.0,
    "pressure_variance": 0.3,
    "size_scale": 1.0,
    "seed_bias": 0.5,
    "roundness": 0.55,
    "connectedness": 0.7,
    "tallness": 1.0,
    "chaos": 0.35,
    "angle_variance": 0.18,
}


def load_styles_catalog(styles_dir: Path):
    styles = []
    styles_dir.mkdir(parents=True, exist_ok=True)
    default_present = False
    for path in sorted(styles_dir.glob("*.npz")):
        try:
            data = np.load(path, allow_pickle=True)
            meta = json.loads(str(data["metadata"].item()))
            styles.append(meta)
            if meta.get("name") == "default":
                default_present = True
        except Exception:
            continue
    if not default_present:
        styles.insert(0, DEFAULT_STYLE.copy())
    return styles


class HandwritingSynthesizer:
    def __init__(self, styles_dir: Path):
        self.styles_dir = Path(styles_dir)
        self.styles_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_default_style()

    def _ensure_default_style(self):
        default_path = self.styles_dir / "default.npz"
        if not default_path.exists():
            self.save_style(DEFAULT_STYLE.copy())
        for preset in PRESET_STYLES:
            self.save_style(preset.copy())

    def _style_path(self, style_name: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in style_name.strip())
        if not safe:
            safe = "default"
        return self.styles_dir / f"{safe}.npz"

    def save_style(self, style_data: Dict):
        style = DEFAULT_STYLE.copy()
        style.update(style_data)
        style_name = style["style_name"] if "style_name" in style else style.get("name", "default")
        style["name"] = style_name
        path = self._style_path(style_name)

        vector = np.array([
            float(style.get("slant_degrees", 0.0)),
            float(style.get("stroke_width", 2.2)),
            float(style.get("letter_spacing", 0.0)),
            float(style.get("word_spacing", 16.0)),
            float(style.get("baseline_jitter", 2.0)),
            float(style.get("pressure_variance", 0.3)),
            float(style.get("size_scale", 1.0)),
            float(style.get("seed_bias", 0.5)),
            float(style.get("roundness", 0.55)),
            float(style.get("connectedness", 0.7)),
            float(style.get("tallness", 1.0)),
            float(style.get("chaos", 0.35)),
            float(style.get("angle_variance", 0.18)),
        ], dtype=np.float32)
        np.savez(path, style_vector=vector, metadata=json.dumps(style))
        return style

    def load_style(self, style_name: str) -> Dict:
        path = self._style_path(style_name)
        if not path.exists():
            raise FileNotFoundError(f"Style '{style_name}' was not found")
        data = np.load(path, allow_pickle=True)
        meta = json.loads(str(data["metadata"].item()))
        return meta

    def create_style_from_sample_image(self, style_name: str, image, sample_text: str = ""):
        arr = np.asarray(image, dtype=np.float32)
        if arr.ndim != 2:
            raise ValueError("Expected a grayscale handwriting image")
        ink = 255.0 - arr
        mask = ink > max(20.0, ink.mean() * 0.7)
        coords = np.argwhere(mask)
        if coords.size == 0:
            raise ValueError("No handwriting strokes were detected in the image")

        y = coords[:, 0].astype(np.float32)
        x = coords[:, 1].astype(np.float32)
        y_centered = y - y.mean()
        x_centered = x - x.mean()
        var_y = float(np.var(y_centered)) + 1e-6
        var_x = float(np.var(x_centered)) + 1e-6
        cov = float(np.mean(x_centered * y_centered))
        slope = cov / var_y
        darkness = float(ink[mask].mean() / 255.0)
        coverage = float(mask.mean())
        height_span = float((y.max() - y.min() + 1) / max(1, image.height))
        width_span = float((x.max() - x.min() + 1) / max(1, image.width))

        row_density = mask.mean(axis=1)
        transitions = np.abs(np.diff(mask.astype(np.int8), axis=1)).mean()

        style = DEFAULT_STYLE.copy()
        style.update({
            "name": style_name,
            "sample_text": sample_text,
            "slant_degrees": float(np.clip(-math.degrees(math.atan(slope)) * 1.6, -28, 28)),
            "stroke_width": float(np.clip(1.4 + darkness * 2.6 + coverage * 4.0, 1.2, 5.0)),
            "letter_spacing": float(np.clip(6.0 - coverage * 24.0 - transitions * 8.0, -2.0, 8.0)),
            "word_spacing": float(np.clip(14.0 + width_span * 8.0, 10.0, 28.0)),
            "baseline_jitter": float(np.clip(1.0 + np.std(row_density) * 22.0, 0.8, 8.0)),
            "pressure_variance": float(np.clip(0.18 + darkness * 0.7, 0.15, 0.9)),
            "size_scale": float(np.clip(0.7 + height_span * 1.5, 0.65, 1.8)),
            "seed_bias": 0.5,
            "roundness": float(np.clip(1.0 - transitions * 2.2, 0.15, 0.95)),
            "connectedness": float(np.clip(0.25 + coverage * 6.0, 0.15, 0.98)),
            "tallness": float(np.clip(0.65 + height_span * 2.2, 0.7, 1.9)),
            "chaos": float(np.clip(0.2 + np.std(row_density) * 18.0 + transitions * 0.8, 0.15, 1.1)),
            "angle_variance": float(np.clip(0.08 + abs(slope) * 0.35, 0.06, 0.6)),
        })
        return self.save_style(style)

    def generate(self, text: str, style_name: str = "default"):
        style = self.load_style(style_name)
        rng = random.Random()
        rng.seed()

        size_scale = float(style.get("size_scale", 1.0))
        stroke_width = float(style.get("stroke_width", 2.2))
        baseline_jitter = float(style.get("baseline_jitter", 2.0))
        word_spacing = float(style.get("word_spacing", 16.0))
        letter_spacing = float(style.get("letter_spacing", 0.0))
        slant_degrees = float(style.get("slant_degrees", -6.0))
        pressure_variance = float(style.get("pressure_variance", 0.3))
        bias = float(style.get("seed_bias", 0.5))
        roundness = float(style.get("roundness", 0.55))
        connectedness = float(style.get("connectedness", 0.7))
        tallness = float(style.get("tallness", 1.0))
        chaos = float(style.get("chaos", 0.35))
        angle_variance = float(style.get("angle_variance", 0.18))

        line_height = 86 * size_scale * tallness
        margin = 24
        estimated_width = max(640, int(len(text) * 28 * size_scale) + margin * 2)
        estimated_height = int(line_height * max(2, text.count("\n") + 1) + margin * 2)

        dwg = svgwrite.Drawing(size=(estimated_width, estimated_height), viewBox=f"0 0 {estimated_width} {estimated_height}")
        dwg.add(dwg.rect(insert=(0, 0), size=(estimated_width, estimated_height), fill="#0d0d0d"))

        x = margin
        y = margin + line_height * 0.7
        slant = math.tan(math.radians(slant_degrees))

        for line in text.splitlines() or [""]:
            for word in line.split(" "):
                if not word:
                    x += word_spacing
                    continue
                word_group = dwg.g()
                local_x = x
                word_seed = rng.random() + bias
                for char in word:
                    strokes, advance = self._glyph(char, local_x, y, size_scale, rng, slant, baseline_jitter, word_seed, roundness, connectedness, tallness, chaos, angle_variance)
                    for stroke in strokes:
                        color = "#ead7b7"
                        width = max(0.8, stroke_width + rng.uniform(-pressure_variance, pressure_variance))
                        path_data = self._stroke_to_path(stroke)
                        word_group.add(dwg.path(d=path_data, fill="none", stroke=color, stroke_width=width, stroke_linecap="round", stroke_linejoin="round"))
                    local_x += advance + letter_spacing + rng.uniform(-2.0, 2.0)
                dwg.add(word_group)
                x = local_x + word_spacing + rng.uniform(-2.0, 2.0)
            x = margin
            y += line_height + rng.uniform(-3.0, 4.0)

        svg = dwg.tostring()
        return {"svg": svg, "style": style_name, "text": text, "engine": "local-professional-preset-svg"}

    def _glyph(self, char: str, x: float, y: float, scale: float, rng: random.Random, slant: float, baseline_jitter: float, word_seed: float, roundness: float, connectedness: float, tallness: float, chaos: float, angle_variance: float):
        c = char.lower()
        if c == " ":
            return [], 16 * scale

        base_y = y + rng.uniform(-baseline_jitter, baseline_jitter)
        h = 22 * scale * tallness
        w = 14 * scale * (0.85 + roundness * 0.45)
        amp = 0.92 + min(0.95, word_seed * (0.12 + chaos * 0.06))

        def sx(px: float, py: float):
            local_slant = slant + rng.uniform(-angle_variance, angle_variance)
            jitter_x = rng.uniform(-(0.8 + chaos * 2.4), (0.8 + chaos * 2.4))
            jitter_y = rng.uniform(-(0.8 + chaos * 2.6), (0.8 + chaos * 2.6))
            px = px * (0.85 + roundness * 0.35)
            py = py * tallness
            slanted_x = x + px * scale + (py * scale * local_slant)
            return (slanted_x + jitter_x, base_y + py * scale + jitter_y)

        glyphs = {
            "a": [[(0, -8), (2, -13), (8, -13), (10, -8), (8, -2), (2, -2), (0, -8)], [(10, -8), (10, 2)]],
            "b": [[(0, -22), (0, 2)], [(0, -11), (5, -14), (10, -11), (9, -4), (3, -2), (0, -5)]],
            "c": [[(10, -12), (6, -14), (2, -12), (0, -7), (2, -2), (8, 0)]],
            "d": [[(10, -22), (10, 2)], [(10, -10), (6, -14), (1, -12), (0, -7), (2, -1), (8, 0), (10, -4)]],
            "e": [[(10, -8), (2, -8), (0, -12), (2, -16), (8, -14), (10, -8), (8, -2), (2, -1)]],
            "f": [[(8, -22), (4, -20), (3, -15), (3, 2)], [(0, -10), (8, -10)]],
            "g": [[(9, -12), (5, -15), (1, -12), (0, -7), (2, -2), (8, -2), (10, -6), (9, 6), (4, 12), (0, 10)]],
            "h": [[(0, -22), (0, 2)], [(0, -9), (4, -13), (9, -10), (10, 2)]],
            "i": [[(1, -12), (1, 2)], [(1, -18), (1, -18.2)]],
            "j": [[(5, -12), (5, 5), (3, 10), (0, 11)], [(5, -18), (5, -18.2)]],
            "k": [[(0, -22), (0, 2)], [(9, -14), (0, -5), (9, 2)]],
            "l": [[(2, -22), (2, 2)]],
            "m": [[(0, -12), (0, 2)], [(0, -9), (4, -14), (7, -10), (7, 2)], [(7, -10), (11, -14), (14, -10), (14, 2)]],
            "n": [[(0, -12), (0, 2)], [(0, -9), (4, -14), (9, -10), (10, 2)]],
            "o": [[(2, -12), (7, -14), (11, -10), (11, -4), (7, 0), (2, -2), (0, -8), (2, -12)]],
            "p": [[(0, -12), (0, 12)], [(0, -11), (5, -14), (9, -11), (8, -4), (2, -2), (0, -5)]],
            "q": [[(10, -12), (5, -14), (1, -12), (0, -7), (2, -2), (8, -2), (10, 2), (10, 10)]],
            "r": [[(0, -12), (0, 2)], [(0, -10), (4, -14), (9, -11)]],
            "s": [[(10, -13), (5, -15), (1, -11), (6, -8), (10, -5), (8, -1), (2, 0), (0, -1)]],
            "t": [[(4, -20), (4, 2)], [(0, -10), (8, -10)]],
            "u": [[(0, -12), (0, -3), (2, 1), (7, 1), (10, -2), (10, -12)]],
            "v": [[(0, -12), (4, 2), (10, -12)]],
            "w": [[(0, -12), (3, 2), (7, -8), (10, 2), (14, -12)]],
            "x": [[(0, -12), (10, 2)], [(10, -12), (0, 2)]],
            "y": [[(0, -12), (5, -2), (10, -12)], [(5, -2), (2, 7), (0, 10)]],
            "z": [[(0, -12), (10, -12), (0, 2), (10, 2)]],
        }

        if c.isdigit():
            digit_strokes = {
                "0": [[(2, -16), (8, -16), (10, -8), (8, 0), (2, 0), (0, -8), (2, -16)]],
                "1": [[(5, -16), (5, 0)]],
                "2": [[(1, -12), (5, -16), (9, -13), (1, 0), (10, 0)]],
                "3": [[(1, -14), (9, -14), (5, -8), (9, -3), (1, -1)]],
                "4": [[(8, -16), (8, 0)], [(1, -6), (10, -6), (1, -16)]],
                "5": [[(9, -16), (2, -16), (1, -9), (7, -9), (10, -4), (8, 0), (2, -1)]],
                "6": [[(9, -14), (4, -16), (0, -8), (3, 0), (8, -1), (10, -6), (6, -10), (1, -8)]],
                "7": [[(0, -16), (10, -16), (3, 0)]],
                "8": [[(3, -16), (8, -15), (9, -11), (5, -8), (1, -11), (3, -16)], [(3, -7), (8, -6), (9, -2), (5, 1), (1, -2), (3, -7)]],
                "9": [[(9, -8), (6, -14), (1, -14), (0, -8), (4, -4), (9, -7), (8, 2), (3, 6)]],
            }
            raw = digit_strokes[c]
        elif c in {".", ",", "!", "?", "-", "'", '"', ":", ";"}:
            punctuation = {
                ".": [[(2, 0), (2, 0.2)]],
                ",": [[(2, 0), (1, 3)]],
                "!": [[(2, -14), (2, -2)], [(2, 2), (2, 2.2)]],
                "?": [[(0, -12), (4, -16), (9, -13), (6, -8), (5, -4)], [(5, 2), (5, 2.2)]],
                "-": [[(0, -5), (8, -5)]],
                "'": [[(2, -16), (1, -12)]],
                '"': [[(1, -16), (0, -12)], [(5, -16), (4, -12)]],
                ":": [[(2, -8), (2, -8.2)], [(2, 0), (2, 0.2)]],
                ";": [[(2, -8), (2, -8.2)], [(2, 0), (1, 3)]],
            }
            raw = punctuation[c]
            w = 7 * scale
        else:
            raw = glyphs.get(c)

        if raw is None:
            raw = [[(0, -12), (0, 2), (10, 2), (10, -12), (0, -12)]]

        strokes = []
        for idx, stroke in enumerate(raw):
            varied = []
            for px, py in stroke:
                px2 = px * amp + rng.uniform(-(0.3 + chaos), (0.3 + chaos))
                py2 = py * amp + rng.uniform(-(0.3 + chaos), (0.3 + chaos))
                varied.append(sx(px2, py2))
            if idx > 0 and connectedness > 0.6 and strokes:
                prev_end = strokes[-1][-1]
                current_start = varied[0]
                bridge = [
                    prev_end,
                    ((prev_end[0] + current_start[0]) / 2, (prev_end[1] + current_start[1]) / 2 + rng.uniform(-1.5, 1.5)),
                    current_start,
                ]
                strokes.append(bridge)
            strokes.append(varied)

        advance = (w + rng.uniform(-1.5, 3.5) + connectedness * 1.5 - chaos * 0.8) * amp
        return strokes, advance

    def _stroke_to_path(self, stroke: Stroke) -> str:
        if not stroke:
            return ""
        if len(stroke) == 1:
            x, y = stroke[0]
            return f"M {x:.2f} {y:.2f}"

        d = [f"M {stroke[0][0]:.2f} {stroke[0][1]:.2f}"]
        for idx in range(1, len(stroke)):
            prev = stroke[idx - 1]
            curr = stroke[idx]
            cx = (prev[0] + curr[0]) / 2
            cy = (prev[1] + curr[1]) / 2
            d.append(f"Q {prev[0]:.2f} {prev[1]:.2f} {cx:.2f} {cy:.2f}")
        last = stroke[-1]
        d.append(f"T {last[0]:.2f} {last[1]:.2f}")
        return " ".join(d)
