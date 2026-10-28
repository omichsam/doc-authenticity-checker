"""Inference and image helpers for the document-tampering Streamlit app."""
from __future__ import annotations

import io
import random
from pathlib import Path
from typing import BinaryIO

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision
from PIL import Image, ImageDraw, ImageFont, ImageOps

WORK_SIDE = 1024
DEFAULT_CROP = 384
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

QUALITY_CUTOFFS = {"POOR": 40, "GOOD": 70}
QUALITY_FACTORS = {
    "sharpness": (0.45, "Fine detail and edge clarity"),
    "contrast": (0.25, "Separation between text and background"),
    "brightness": (0.15, "Distance from the preferred page brightness"),
    "resolution": (0.15, "Available pixel height"),
}
TRAIN_TYPES = ["field_edit", "copy_move", "splice"]
TEST_TYPES = TRAIN_TYPES + ["erase"]
FORGERY_INFO = {
    "field_edit": "Replace a text field with a different value.",
    "copy_move": "Copy a text patch to another location on the page.",
    "splice": "Paste a text patch from a different page.",
    "erase": "Remove text with inpainting (not used during training).",
}


def load_image(source: bytes | bytearray | str | Path | BinaryIO) -> np.ndarray:
    """Load image bytes or a path as an EXIF-corrected RGB uint8 array."""
    try:
        if isinstance(source, (bytes, bytearray)):
            image_source = io.BytesIO(source)
        else:
            image_source = source
        with Image.open(image_source) as image:
            return np.asarray(ImageOps.exif_transpose(image).convert("RGB")).copy()
    except (OSError, ValueError) as exc:
        raise ValueError("The uploaded file could not be decoded as an image.") from exc


def resize_long(img: np.ndarray, side: int = WORK_SIDE) -> np.ndarray:
    scale = min(1.0, side / max(img.shape[:2]))
    if scale == 1.0:
        return img
    return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)


def quality(img: np.ndarray) -> tuple[float, str, dict[str, float]]:
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    gray = resize_long(gray)
    parts = {
        "sharpness": np.clip(
            (np.log10(cv2.Laplacian(gray, cv2.CV_64F).var() + 1) - 1) / 2.5, 0, 1
        ),
        "contrast": np.clip(gray.std() / 70, 0, 1),
        "brightness": 1 - np.clip(abs(gray.mean() - 180) / 120, 0, 1),
        "resolution": np.clip(min(img.shape[:2]) / 800, 0, 1),
    }
    score = 100 * sum(QUALITY_FACTORS[key][0] * parts[key] for key in parts)
    category = "POOR" if score < QUALITY_CUTOFFS["POOR"] else (
        "GOOD" if score >= QUALITY_CUTOFFS["GOOD"] else "ACCEPTABLE"
    )
    return float(score), category, {key: float(value) for key, value in parts.items()}


class Up(nn.Module):
    def __init__(self, cin: int, cskip: int, cout: int) -> None:
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(cin + cskip, cout, 3, padding=1, bias=False),
            nn.BatchNorm2d(cout),
            nn.ReLU(inplace=True),
            nn.Conv2d(cout, cout, 3, padding=1, bias=False),
            nn.BatchNorm2d(cout),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor, skip: torch.Tensor) -> torch.Tensor:
        upsampled = F.interpolate(
            x, size=skip.shape[-2:], mode="bilinear", align_corners=False
        )
        return self.conv(torch.cat([upsampled, skip], dim=1))


class TamperUNet(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        encoder = torchvision.models.efficientnet_b0(weights=None)
        self.enc = encoder.features[:8]
        self.u4 = Up(320, 112, 128)
        self.u3 = Up(128, 40, 64)
        self.u2 = Up(64, 24, 48)
        self.u1 = Up(48, 16, 32)
        self.head = nn.Conv2d(32, 1, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        skips: dict[int, torch.Tensor] = {}
        hidden = x
        for index, block in enumerate(self.enc):
            hidden = block(hidden)
            if index in (1, 2, 3, 5):
                skips[index] = hidden
        hidden = self.u1(
            self.u2(
                self.u3(self.u4(hidden, skips[5]), skips[3]),
                skips[2],
            ),
            skips[1],
        )
        return F.interpolate(
            self.head(hidden), size=x.shape[-2:], mode="bilinear", align_corners=False
        )


def _to_tensor(image: np.ndarray) -> torch.Tensor:
    normalized = (image.astype(np.float32) / 255.0 - MEAN) / STD
    return torch.from_numpy(normalized.transpose(2, 0, 1).copy())


def _predict_map(
    model: TamperUNet, image: np.ndarray, device: torch.device, crop: int, batch_size: int = 4
) -> np.ndarray:
    height, width = image.shape[:2]
    stride = max(1, crop * 3 // 4)
    padded = cv2.copyMakeBorder(
        image,
        0,
        max(0, crop - height),
        0,
        max(0, crop - width),
        cv2.BORDER_CONSTANT,
        value=(255, 255, 255),
    )
    padded_height, padded_width = padded.shape[:2]
    ys = sorted({*range(0, padded_height - crop + 1, stride), padded_height - crop})
    xs = sorted({*range(0, padded_width - crop + 1, stride), padded_width - crop})
    tiles = [(y, x) for y in ys for x in xs]
    accum = np.zeros((padded_height, padded_width), dtype=np.float32)
    counts = np.zeros_like(accum)

    model.eval()
    with torch.inference_mode():
        for start in range(0, len(tiles), batch_size):
            chunk = tiles[start:start + batch_size]
            inputs = torch.stack(
                [_to_tensor(padded[y:y + crop, x:x + crop]) for y, x in chunk]
            ).to(device)
            with torch.autocast(device.type, enabled=device.type == "cuda"):
                logits = model(inputs)
            probabilities = torch.sigmoid(logits.float())[:, 0].cpu().numpy()
            for (y, x), prediction in zip(chunk, probabilities):
                accum[y:y + crop, x:x + crop] += prediction
                counts[y:y + crop, x:x + crop] += 1
    probability_map = accum / np.maximum(counts, 1)
    return probability_map[:height, :width]


class Checker:
    def __init__(
        self,
        model: TamperUNet,
        device: torch.device,
        crop: int,
        work_side: int,
        threshold: float,
        meta: dict[str, object] | None = None,
    ) -> None:
        self.model = model
        self.device = device
        self.crop = crop
        self.work_side = work_side
        self.threshold = threshold
        self.meta = meta or {}

    @classmethod
    def load(cls, path: str | Path) -> "Checker":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        checkpoint = torch.load(path, map_location=device, weights_only=True)
        if not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("state"), dict):
            raise ValueError("The model checkpoint does not contain a valid state dictionary.")

        model = TamperUNet().to(device)
        model.load_state_dict(checkpoint["state"])
        model.eval()
        return cls(
            model=model,
            device=device,
            crop=int(checkpoint.get("crop", DEFAULT_CROP)),
            work_side=int(checkpoint.get("work_side", WORK_SIDE)),
            threshold=float(checkpoint.get("threshold", 0.5)),
            meta=checkpoint.get("meta", {}),
        )

    def predict(self, image: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        work_image = resize_long(image, self.work_side)
        probability_map = _predict_map(
            self.model, work_image, self.device, self.crop
        )
        score = float(cv2.GaussianBlur(probability_map, (9, 9), 0).max())
        return work_image, probability_map, score


def heat_overlay(image: np.ndarray, probability: np.ndarray, alpha: float = 0.6) -> np.ndarray:
    heat = cv2.applyColorMap(
        np.clip(probability * 255, 0, 255).astype(np.uint8), cv2.COLORMAP_JET
    )
    heat = cv2.cvtColor(heat, cv2.COLOR_BGR2RGB)
    return cv2.addWeighted(image, 1 - alpha, heat, alpha, 0)


def suspicious_regions(
    probability: np.ndarray, thr: float = 0.5
) -> list[tuple[int, int, int, int, float]]:
    binary = (probability >= thr).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    regions = []
    for label in range(1, count):
        x, y, width, height, area = stats[label]
        if area < 4:
            continue
        peak = float(probability[labels == label].max())
        regions.append((int(x), int(y), int(width), int(height), peak))
    return sorted(regions, key=lambda region: region[4], reverse=True)


def draw_boxes(
    image: np.ndarray, regions: list[tuple[int, int, int, int, float]]
) -> np.ndarray:
    result = image.copy()
    for x, y, width, height, _ in regions:
        cv2.rectangle(result, (x, y), (x + width, y + height), (255, 210, 0), 2)
    return result


def mask_outline(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    result = image.copy()
    binary = (mask > 0).astype(np.uint8)
    outline = cv2.morphologyEx(
        binary, cv2.MORPH_GRADIENT, np.ones((3, 3), dtype=np.uint8)
    ).astype(bool)
    result[outline] = (0, 220, 80)
    return result


def _text_boxes(image: np.ndarray) -> list[tuple[int, int, int, int]]:
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )[1]
    contours, _ = cv2.findContours(
        cv2.dilate(binary, np.ones((3, 9), dtype=np.uint8)),
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    return [
        box for box in map(cv2.boundingRect, contours)
        if 15 < box[2] < image.shape[1] // 3 and 7 < box[3] < 40
    ]


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("arial.ttf", "times.ttf", "cour.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_forgery(
    image: np.ndarray,
    kind: str,
    rng: random.Random,
    donor: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    if kind not in TEST_TYPES:
        raise ValueError(f"Unknown edit type: {kind}")
    forged = image.copy()
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    boxes = _text_boxes(forged)
    if not boxes:
        return forged, mask

    x, y, width, height = rng.choice(boxes)
    if kind == "field_edit":
        above = forged[max(0, y - 4):y, x:x + width].reshape(-1, 3)
        below = forged[y + height:y + height + 4, x:x + width].reshape(-1, 3)
        surrounding = np.concatenate([above, below])
        background = np.median(surrounding, axis=0) if len(surrounding) else 255
        forged[y:y + height, x:x + width] = background
        pil_image = Image.fromarray(forged)
        draw = ImageDraw.Draw(pil_image)
        font = _font(max(8, int(height * 0.9)))
        text = rng.choice([
            f"{rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/20{rng.randint(10, 26)}",
            str(rng.randint(10, 99999)),
            f"{rng.randint(10, 100)}%",
        ])
        draw.text((x, y), text, fill=(30, 30, 30), font=font)
        forged = np.asarray(pil_image).copy()
        mask[y:y + height, x:x + width] = 1
    elif kind == "copy_move":
        source_x, source_y, source_w, source_h = rng.choice(boxes)
        target_x = rng.randint(0, max(0, image.shape[1] - source_w))
        target_y = rng.randint(0, max(0, image.shape[0] - source_h))
        forged[target_y:target_y + source_h, target_x:target_x + source_w] = (
            image[source_y:source_y + source_h, source_x:source_x + source_w]
        )
        mask[target_y:target_y + source_h, target_x:target_x + source_w] = 1
    elif kind == "splice" and donor is not None:
        donor_boxes = _text_boxes(donor)
        if donor_boxes:
            source_x, source_y, source_w, source_h = rng.choice(donor_boxes)
            copy_h = min(source_h, image.shape[0] - y)
            copy_w = min(source_w, image.shape[1] - x)
            forged[y:y + copy_h, x:x + copy_w] = donor[
                source_y:source_y + copy_h, source_x:source_x + copy_w
            ]
            mask[y:y + copy_h, x:x + copy_w] = 1
    elif kind == "erase":
        roi = cv2.cvtColor(
            forged[y:y + height, x:x + width], cv2.COLOR_RGB2GRAY
        )
        ink = np.zeros(image.shape[:2], dtype=np.uint8)
        ink[y:y + height, x:x + width] = cv2.threshold(
            roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )[1]
        forged = cv2.inpaint(
            forged, cv2.dilate(ink, np.ones((3, 3), dtype=np.uint8)), 3,
            cv2.INPAINT_TELEA,
        )
        mask[y:y + height, x:x + width] = 1
    return forged, mask


def post_process(image: np.ndarray, rng: random.Random) -> np.ndarray:
    candidate = cv2.GaussianBlur(image, (3, 3), 0) if rng.random() < 0.3 else image
    quality_value = rng.randint(60, 95)
    ok, encoded = cv2.imencode(
        ".jpg", candidate[..., ::-1],
        [cv2.IMWRITE_JPEG_QUALITY, quality_value],
    )
    if not ok:
        raise RuntimeError("Could not encode the image for the lab comparison.")
    decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if decoded is None:
        raise RuntimeError("Could not decode the lab comparison image.")
    return decoded[..., ::-1].copy()
