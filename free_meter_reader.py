from __future__ import annotations

import io
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, TypedDict

import cv2
import numpy as np
import pytesseract
from PIL import Image


class TrainingExample(TypedDict):
    filename: str
    reading: str
    int_count: int


class ReadingCandidate(TypedDict):
    int_count: int
    digits: list[str]
    avg_score: float
    score: float

TRAINING_EXAMPLES: list[TrainingExample] = [
    {"filename": "gazesskaititajs_LETA-1.jpg", "reading": "0736.530", "int_count": 4},
    {"filename": "skaititajs_slodze.jpg", "reading": "38880.067", "int_count": 5},
    {"filename": "50e8f28d-4d25-1f96.jpg", "reading": "25972.862", "int_count": 5},
    {"filename": "20260414_074504.jpg", "reading": "03874.405", "int_count": 5},
]

START_OFFSETS = [-0.35, -0.25, -0.15]
INT_COUNTS = [5, 4, 6]
ROTATION_ANGLES = [0, -8, 8]
RAW_READING_CONFIDENCE_THRESHOLD = 0.9


@dataclass
class MeterExtractionResult:
    meter_reading: str | None
    manufacturing_year: int | None
    serial_number: str | None
    confidence: float
    notes: list[str]


class FreeMeterReader:
    def __init__(self) -> None:
        self.base_dir = Path(__file__).resolve().parent
        self.examples_dir = self.base_dir / "examples"
        self.tesseract_available = self._configure_tesseract()
        self.template_bank = self._build_template_bank()

    def extract(self, image_bytes: bytes) -> MeterExtractionResult:
        image = self._decode_image(image_bytes)
        notes: list[str] = []
        if not self.tesseract_available:
            notes.append("Tesseract OCR nav pieejams PATH, tāpēc M gada un skaitītāja numura nolasīšana būs ierobežota.")

        panel, panel_note = self._find_front_panel(image)
        if panel_note:
            notes.append(panel_note)

        panel_reading, panel_conf, panel_meta = self._extract_meter_reading(panel)
        if panel_reading is not None and panel_conf >= RAW_READING_CONFIDENCE_THRESHOLD:
            meter_reading, reading_conf, reading_meta = panel_reading, panel_conf, panel_meta
        else:
            raw_reading, raw_conf, raw_meta = self._extract_meter_reading(image)
            if panel_conf >= raw_conf:
                meter_reading, reading_conf, reading_meta = panel_reading, panel_conf, panel_meta
            else:
                meter_reading, reading_conf, reading_meta = raw_reading, raw_conf, raw_meta
                notes.append("Rādījums paņemts no oriģinālā foto, jo tas tika nolasīts drošāk nekā no paneļa izgriezuma.")
        if reading_meta.get("note"):
            notes.append(str(reading_meta["note"]))

        year, serial, text_notes = self._extract_text_fields(panel)
        if year is None or serial is None:
            year2, serial2, text_notes2 = self._extract_text_fields(image)
            year = year if year is not None else year2
            serial = serial if serial is not None else serial2
            text_notes.extend(text_notes2)
        notes.extend(text_notes)

        if meter_reading is None:
            notes.append("Rādījumu neizdevās droši noteikt. Palīdz tuvāks foto bez atspīduma un ar visu paneli kadrā.")
        if year is None:
            notes.append("Izgatavošanas gadu neizdevās droši nolasīt. Parasti tas ir kvadrātā ar M un 2 cipariem.")
        if serial is None:
            notes.append("Skaitītāja numuru neizdevās droši nolasīt. Palīdz tuvāks foto no priekšas.")

        conf_parts = [reading_conf]
        if year is not None:
            conf_parts.append(0.88)
        if serial is not None:
            conf_parts.append(0.88)
        confidence = round(float(np.mean(conf_parts)), 3) if conf_parts else 0.0

        return MeterExtractionResult(
            meter_reading=meter_reading,
            manufacturing_year=year,
            serial_number=serial,
            confidence=confidence,
            notes=self._unique_keep_order(notes),
        )

    # ----------------------------
    # Front panel detection
    # ----------------------------
    def _find_front_panel(self, image: np.ndarray) -> tuple[np.ndarray, str | None]:
        candidates: list[tuple[float, np.ndarray, int]] = []
        for angle in ROTATION_ANGLES:
            rotated = self._rotate_bound(image, angle) if angle else image.copy()
            for red_box in self._find_red_boxes(rotated)[:2]:
                for crop in self._panel_crops_from_red(rotated, red_box):
                    candidates.append((self._panel_score(crop), crop, angle))
        if not candidates:
            return image.copy(), "Priekšējais panelis netika izolēts, izmantots viss foto."
        candidates.sort(key=lambda item: item[0], reverse=True)
        _, best, angle = candidates[0]
        note = "Priekšējais panelis atrasts automātiski."
        if angle:
            note += f" Foto tika pagriezts par {angle}° stabilākai nolasīšanai."
        return best, note

    def _find_red_boxes(self, image: np.ndarray) -> list[tuple[int, int, int, int]]:
        h, w = image.shape[:2]
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        lower_red_1 = np.array((0, 45, 45), dtype=np.uint8)
        upper_red_1 = np.array((15, 255, 255), dtype=np.uint8)
        lower_red_2 = np.array((160, 45, 45), dtype=np.uint8)
        upper_red_2 = np.array((180, 255, 255), dtype=np.uint8)
        mask = cv2.bitwise_or(
            cv2.inRange(hsv, lower_red_1, upper_red_1),
            cv2.inRange(hsv, lower_red_2, upper_red_2),
        )
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=2)
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        found: list[tuple[float, tuple[int, int, int, int]]] = []
        for i in range(1, num_labels):
            x, y, ww, hh, area = stats[i]
            ratio = ww / max(hh, 1)
            frac = area / float(w * h)
            if area < 500 or ratio < 1.4 or ratio > 5.5 or frac > 0.025:
                continue
            if y < 0.18 * h or y > 0.85 * h:
                continue
            cy = (y + hh / 2) / h
            score = float(area) - abs(cy - 0.55) * 3000 - abs(ratio - 2.6) * 500
            found.append((score, (int(x), int(y), int(ww), int(hh))))
        found.sort(key=lambda item: item[0], reverse=True)
        return [box for _, box in found]

    def _panel_crops_from_red(self, image: np.ndarray, red_box: tuple[int, int, int, int]) -> list[np.ndarray]:
        x, y, w, h = red_box
        H, W = image.shape[:2]
        crops: list[np.ndarray] = []
        for left_mul, right_mul, top_mul, bottom_mul in ((4.2, 2.8, 5.2, 1.25), (3.6, 3.0, 4.8, 1.45)):
            sx = max(0, int(x - left_mul * w))
            ex = min(W, int(x + right_mul * w))
            sy = max(0, int(y - top_mul * h))
            ey = min(H, int(y + bottom_mul * h))
            crop = image[sy:ey, sx:ex].copy()
            if crop.size > 0:
                crops.append(crop)
        return crops

    def _panel_score(self, image: np.ndarray) -> float:
        h, w = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        bright = float((gray > 145).mean())
        lower = gray[int(0.55 * h):, :]
        dark = float((lower < 110).mean())
        aspect = w / max(h, 1)
        red_bonus = 0.0
        red_boxes = self._find_red_boxes(image)
        if red_boxes:
            x, y, ww, hh = red_boxes[0]
            red_bonus = ww * hh * 0.7 - abs(((y + hh / 2) / h) - 0.72) * 1200
        return bright * 1400 + dark * 900 + red_bonus - abs(aspect - 2.0) * 180

    # ----------------------------
    # Reading extraction
    # ----------------------------
    def _extract_meter_reading(self, image: np.ndarray) -> tuple[str | None, float, dict[str, object]]:
        red_box = self._pick_red_box(image)
        if red_box is None:
            fallback = self._ocr_reading_fallback(image)
            if fallback:
                return fallback, 0.45, {"note": "Rādījums līdz komatam paņemts no OCR rezerves režīma, uzticamība zemāka."}
            return None, 0.0, {"note": "Neizdevās atrast sarkano decimāldaļu reģionu."}

        strip, crop_box = self._crop_counter_strip(image, red_box)
        band, _ = self._crop_digit_band(strip)
        local_red_x = red_box[0] - crop_box[0]
        red_w = red_box[2]

        best_candidate: ReadingCandidate | None = None
        for int_count in INT_COUNTS:
            for start_offset in START_OFFSETS:
                cells = self._extract_cells(band, local_red_x, red_w, int_count=int_count, start_offset=start_offset)
                if len(cells) != int_count + 3:
                    continue
                predicted_digits: list[str] = []
                raw_scores: list[float] = []
                for cell in cells:
                    proc = self._preprocess_cell(cell)
                    if proc is None:
                        predicted_digits.append("?")
                        raw_scores.append(0.0)
                        continue
                    digit, score = self._match_digit(proc)
                    predicted_digits.append(digit)
                    raw_scores.append(score)
                if "?" in predicted_digits:
                    continue
                avg_score = float(np.mean(raw_scores)) if raw_scores else 0.0
                score = avg_score
                if int_count == 5:
                    score += 0.03
                elif int_count == 4:
                    score += 0.015
                if predicted_digits and predicted_digits[0] in {"0", "1", "2", "3"}:
                    score += 0.01
                candidate: ReadingCandidate = {
                    "int_count": int_count,
                    "digits": predicted_digits,
                    "avg_score": avg_score,
                    "score": score,
                }
                if best_candidate is None or candidate["score"] > best_candidate["score"]:
                    best_candidate = candidate

        if best_candidate is None:
            fallback = self._ocr_reading_fallback(band)
            if fallback:
                return fallback, 0.45, {"note": "Rādījums līdz komatam noteikts ar OCR rezerves režīmu."}
            return None, 0.0, {"note": "Neizdevās sadalīt ciparu logus."}

        digits = list(best_candidate["digits"])
        int_count = int(best_candidate["int_count"])
        reading = ''.join(digits[:int_count])
        confidence = min(0.99, max(0.35, float(best_candidate["avg_score"])))
        note = None if confidence >= 0.78 else "Rādījums nolasīts, bet foto kvalitāte vai perspektīva pazemināja uzticamību."
        return reading, confidence, {"note": note}

    def _pick_red_box(self, image: np.ndarray) -> tuple[int, int, int, int] | None:
        boxes = self._find_red_boxes(image)
        return boxes[0] if boxes else None

    def _crop_counter_strip(self, image: np.ndarray, red_box: tuple[int, int, int, int]) -> tuple[np.ndarray, tuple[int, int, int, int]]:
        x, y, w, h = red_box
        H, W = image.shape[:2]
        sx = max(0, int(x - 2.8 * w))
        ex = min(W, int(x + 1.35 * w))
        sy = max(0, int(y - 0.65 * h))
        ey = min(H, int(y + 1.05 * h))
        return image[sy:ey, sx:ex].copy(), (sx, sy, ex, ey)

    def _crop_digit_band(self, strip: np.ndarray) -> tuple[np.ndarray, tuple[int, int]]:
        gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
        row_dark = (gray < 120).mean(axis=1)
        mask = row_dark > 0.42
        best_start, best_end, best_len = 0, strip.shape[0], 0
        i = 0
        while i < len(mask):
            if mask[i]:
                j = i
                while j < len(mask) and mask[j]:
                    j += 1
                if j - i > best_len:
                    best_start, best_end, best_len = i, j, j - i
                i = j
            else:
                i += 1
        y1 = max(0, best_start - 3)
        y2 = min(strip.shape[0], best_end + 3)
        return strip[y1:y2].copy(), (y1, y2)

    def _extract_cells(self, band: np.ndarray, local_red_x: int, red_w: int, int_count: int, start_offset: float) -> list[np.ndarray]:
        cell_w = red_w / 3.0
        int_start = int(round(local_red_x - int_count * cell_w + start_offset * cell_w))
        dec_start = int(round(local_red_x - 0.05 * cell_w))
        cells: list[np.ndarray] = []
        for i in range(int_count):
            s = int(round(int_start + i * cell_w))
            e = int(round(int_start + (i + 1) * cell_w))
            s = max(0, s)
            e = min(band.shape[1], e)
            if e - s >= 8:
                cells.append(band[:, s:e].copy())
        for i in range(3):
            s = int(round(dec_start + i * cell_w))
            e = int(round(dec_start + (i + 1) * cell_w))
            s = max(0, s)
            e = min(band.shape[1], e)
            if e - s >= 8:
                cells.append(band[:, s:e].copy())
        return cells

    def _preprocess_cell(self, cell: np.ndarray) -> np.ndarray | None:
        gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY) if cell.ndim == 3 else cell.copy()
        h, w = gray.shape[:2]
        if h < 10 or w < 10:
            return None
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4)).apply(gray)
        inv = 255 - cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11)
        inv[: max(1, int(h * 0.05)), :] = 0
        inv[h - max(1, int(h * 0.05)) :, :] = 0
        inv[:, : max(1, int(w * 0.10))] = 0
        inv[:, w - max(1, int(w * 0.10)) :] = 0
        num_labels, labels, stats, cents = cv2.connectedComponentsWithStats(inv, connectivity=8)
        keep_ids: list[int] = []
        for i in range(1, num_labels):
            x, y, ww, hh, area = stats[i]
            cx, _ = cents[i]
            if area < 10 or hh < h * 0.25 or ww < w * 0.05:
                continue
            if cx < 0.12 * w or cx > 0.88 * w:
                continue
            keep_ids.append(i)
        mask = np.zeros_like(inv)
        if keep_ids:
            for idx in keep_ids[:3]:
                mask[labels == idx] = 255
        else:
            mask = inv
        ys, xs = np.where(mask > 0)
        if len(xs) == 0:
            return None
        x1, x2 = xs.min(), xs.max() + 1
        y1, y2 = ys.min(), ys.max() + 1
        crop = mask[y1:y2, x1:x2]
        crop = cv2.copyMakeBorder(crop, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=0)
        crop = cv2.resize(crop, (40, 60), interpolation=cv2.INTER_NEAREST)
        return np.where(crop > 0, 255, 0).astype(np.uint8)

    def _match_digit(self, digit_mask: np.ndarray) -> tuple[str, float]:
        best_digit = "?"
        best_score = -1.0
        for digit, templates in self.template_bank.items():
            if not templates:
                continue
            score = max(self._mask_similarity(digit_mask, template) for template in templates)
            if score > best_score:
                best_score = score
                best_digit = digit
        return best_digit, float(best_score)

    def _ocr_single_digit(self, digit_mask: np.ndarray) -> str | None:
        if not self.tesseract_available:
            return None
        try:
            txt = pytesseract.image_to_string(cv2.resize(digit_mask, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_NEAREST), config="--psm 10 -c tessedit_char_whitelist=0123456789", timeout=1)
        except Exception:
            return None
        txt = re.sub(r"\D", "", txt)
        return txt[0] if len(txt) == 1 else None

    def _ocr_reading_fallback(self, image: np.ndarray) -> str | None:
        if not self.tesseract_available:
            return None
        texts: list[str] = []
        for variant in self._ocr_variants(image, scale=2.0)[:3]:
            try:
                txt = pytesseract.image_to_string(variant, config="--psm 8 -c tessedit_char_whitelist=0123456789.,", timeout=2)
            except Exception:
                txt = ""
            if txt:
                texts.append(txt)
        candidates: list[str] = []
        for text in texts:
            compact = re.sub(r"[^0-9.,]", "", text).replace(",", ".")
            match = re.search(r"(\d{4,6})\s*[,.]\s*\d{1,3}", compact)
            if match:
                candidates.append(match.group(1))
            digits = re.sub(r"\D", "", compact)
            if len(digits) >= 7:
                int_len = len(digits) - 3
                if 4 <= int_len <= 6:
                    candidates.append(digits[:int_len])
        return candidates[0] if candidates else None

    # ----------------------------
    # Year + serial extraction
    # ----------------------------
    def _extract_text_fields(self, image: np.ndarray) -> tuple[int | None, str | None, list[str]]:
        notes: list[str] = []
        red_box = self._pick_red_box(image)
        year = self._extract_year(image, red_box)
        if year is not None:
            notes.append(f"Izgatavošanas gads secināts no marķējuma M{str(year)[-2:]}." )
        serial = self._extract_serial(image, red_box)
        if serial is not None:
            notes.append("Skaitītāja numurs nolasīts no labās augšējās etiķetes zonas.")
        return year, serial, notes

    def _extract_year(self, image: np.ndarray, red_box: tuple[int, int, int, int] | None) -> int | None:
        if not self.tesseract_available:
            return None
        h, w = image.shape[:2]
        zones: list[np.ndarray] = []
        if red_box is not None:
            x, y, ww, hh = red_box
            sx = max(0, int(x - 4.0 * ww))
            ex = min(w, int(x - 0.8 * ww))
            sy = max(0, int(y - 1.0 * hh))
            ey = min(h, int(y + 1.6 * hh))
            if ex > sx and ey > sy:
                zones.append(image[sy:ey, sx:ex].copy())
        zones.append(image[int(0.46 * h): int(0.86 * h), int(0.02 * w): int(0.30 * w)].copy())
        for zone in zones:
            for crop in self._find_year_box_candidates(zone)[:4]:
                for variant in self._ocr_variants(crop, scale=4.0)[:3]:
                    for psm in (7, 8, 13):
                        try:
                            txt = pytesseract.image_to_string(variant, config=f"--psm {psm} -c tessedit_char_whitelist=M0123456789", timeout=1)
                        except Exception:
                            txt = ""
                        clean = re.sub(r"\s+", "", txt.upper())
                        m = re.search(r"M([0-3]\d)(?!\d)", clean)
                        if m:
                            return 2000 + int(m.group(1))
                        if re.fullmatch(r"[0-3]\d", clean):
                            return 2000 + int(clean)
        return None

    def _find_year_box_candidates(self, zone: np.ndarray) -> list[np.ndarray]:
        gray = cv2.cvtColor(zone, cv2.COLOR_BGR2GRAY)
        thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        edges = cv2.Canny(thr, 40, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        zh, zw = zone.shape[:2]
        found: list[tuple[float, np.ndarray]] = []
        for cnt in contours:
            x, y, ww, hh = cv2.boundingRect(cnt)
            area = ww * hh
            if area < 0.006 * zh * zw or area > 0.20 * zh * zw:
                continue
            aspect = ww / max(hh, 1)
            if not 0.7 <= aspect <= 2.4:
                continue
            if x > 0.85 * zw:
                continue
            pad_x = max(2, int(0.08 * ww))
            pad_y = max(2, int(0.10 * hh))
            crop = zone[max(0, y - pad_y): min(zh, y + hh + pad_y), max(0, x - pad_x): min(zw, x + ww + pad_x)]
            if crop.size == 0:
                continue
            score = -abs(aspect - 1.3) * 3 + area / 1000.0
            found.append((score, crop.copy()))
        found.sort(key=lambda item: item[0], reverse=True)
        return [crop for _, crop in found] or [zone]

    def _extract_serial(self, image: np.ndarray, red_box: tuple[int, int, int, int] | None) -> str | None:
        if not self.tesseract_available:
            return None
        h, w = image.shape[:2]
        zones: list[np.ndarray] = []
        if red_box is not None:
            x, y, ww, hh = red_box
            for sx, ex, sy, ey in (
                (int(x + 0.1 * ww), int(x + 5.0 * ww), int(y - 5.0 * hh), int(y - 0.7 * hh)),
                (int(x + 0.6 * ww), int(x + 4.6 * ww), int(y - 4.4 * hh), int(y - 1.0 * hh)),
            ):
                sx = max(0, sx); ex = min(w, ex); sy = max(0, sy); ey = min(h, ey)
                if ex > sx and ey > sy:
                    zones.append(image[sy:ey, sx:ex].copy())
        zones.append(image[int(0.04 * h): int(0.36 * h), int(0.52 * w): int(0.98 * w)].copy())
        candidates: list[tuple[float, str]] = []
        for zone in zones:
            for variant in self._ocr_variants(zone, scale=3.2)[:3]:
                for psm in (6, 7, 11):
                    try:
                        txt = pytesseract.image_to_string(variant, config=f"--psm {psm} -c tessedit_char_whitelist=0123456789", timeout=1)
                    except Exception:
                        txt = ""
                    for chunk in re.findall(r"(?:\d[\s-]?){7,12}", txt):
                        digits = re.sub(r"\D", "", chunk)
                        if len(digits) < 7 or len(digits) > 12:
                            continue
                        if digits in {"13591998", "13592007", "2006", "2007"}:
                            continue
                        variants = {digits}
                        if len(digits) > 8:
                            for i in range(0, len(digits) - 8 + 1):
                                variants.add(digits[i:i+8])
                        for item in variants:
                            score = 0.0
                            if len(item) == 8:
                                score += 3.0
                            elif len(item) == 7:
                                score += 1.8
                            elif len(item) == 9:
                                score += 0.9
                            if item.startswith("0"):
                                score += 0.4
                            candidates.append((score, item))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], -abs(len(item[1]) - 8), item[1]), reverse=True)
        return candidates[0][1]

    def _ocr_variants(self, image: np.ndarray, scale: float = 1.7) -> list[np.ndarray]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
        max_side = max(gray.shape[:2])
        if max_side > 1000:
            shrink = 1000 / float(max_side)
            gray = cv2.resize(gray, None, fx=shrink, fy=shrink, interpolation=cv2.INTER_AREA)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        normalized_gray = np.empty_like(gray)
        cv2.normalize(gray, normalized_gray, 0, 255, cv2.NORM_MINMAX)
        gray = normalized_gray
        otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11)
        return [gray, otsu, 255 - otsu, adaptive]

    # ----------------------------
    # Templates
    # ----------------------------
    def _build_template_bank(self) -> dict[str, list[np.ndarray]]:
        bank: dict[str, list[np.ndarray]] = {str(i): [] for i in range(10)}
        for meta in TRAINING_EXAMPLES:
            path = self.examples_dir / str(meta["filename"])
            if not path.exists():
                continue
            image = cv2.imread(str(path))
            if image is None:
                continue
            red_box = self._pick_red_box(image)
            if red_box is None:
                continue
            strip, crop_box = self._crop_counter_strip(image, red_box)
            band, _ = self._crop_digit_band(strip)
            local_red_x = red_box[0] - crop_box[0]
            cells = self._extract_cells(band, local_red_x, red_box[2], int_count=int(meta["int_count"]), start_offset=-0.25)
            labels = str(meta["reading"]).replace(".", "")
            for label, cell in zip(labels, cells):
                proc = self._preprocess_cell(cell)
                if proc is not None:
                    bank[label].append(proc)
        synthetic = self._build_synthetic_templates()
        for digit, masks in synthetic.items():
            bank[digit].extend(masks)
        return bank

    def _build_synthetic_templates(self) -> dict[str, list[np.ndarray]]:
        out: dict[str, list[np.ndarray]] = {str(i): [] for i in range(10)}
        fonts = [cv2.FONT_HERSHEY_SIMPLEX, cv2.FONT_HERSHEY_DUPLEX, cv2.FONT_HERSHEY_TRIPLEX]
        for digit in map(str, range(10)):
            for font in fonts:
                canvas = np.zeros((70, 50), dtype=np.uint8)
                cv2.putText(canvas, digit, (6, 56), font, 2.1, 255, 3, cv2.LINE_AA)
                mask = cv2.resize(canvas, (40, 60), interpolation=cv2.INTER_NEAREST)
                out[digit].append(np.where(mask > 32, 255, 0).astype(np.uint8))
        return out

    @staticmethod
    def _mask_similarity(a: np.ndarray, b: np.ndarray) -> float:
        aa = (a > 0).astype(np.uint8)
        bb = (b > 0).astype(np.uint8)
        best = 0.0
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                shifted = np.roll(np.roll(bb, dy, axis=0), dx, axis=1)
                score = float((aa == shifted).mean())
                if score > best:
                    best = score
        return best

    # ----------------------------
    # Utils
    # ----------------------------
    @staticmethod
    def _configure_tesseract() -> bool:
        configured = shutil.which("tesseract")
        if configured:
            pytesseract.pytesseract.tesseract_cmd = configured
            return True

        common_paths = [
            Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
            Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
        ]
        for path in common_paths:
            if path.exists():
                pytesseract.pytesseract.tesseract_cmd = str(path)
                return True
        return False

    @staticmethod
    def _decode_image(image_bytes: bytes) -> np.ndarray:
        file_bytes = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if image is None:
            pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            image = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        if image is None:
            raise ValueError("Attēlu neizdevās atvērt.")
        return image

    @staticmethod
    def _rotate_bound(image: np.ndarray, angle: float) -> np.ndarray:
        (h, w) = image.shape[:2]
        center = (w / 2, h / 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        cos = abs(M[0, 0])
        sin = abs(M[0, 1])
        nW = int((h * sin) + (w * cos))
        nH = int((h * cos) + (w * sin))
        M[0, 2] += (nW / 2) - center[0]
        M[1, 2] += (nH / 2) - center[1]
        return cv2.warpAffine(image, M, (nW, nH), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    @staticmethod
    def _unique_keep_order(items: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            item = item.strip()
            if not item or item in seen:
                continue
            seen.add(item)
            out.append(item)
        return out
