#!/usr/bin/env python3
"""
TIFF → jpegli Batch Converter
Phase 4: True 16-bit pipeline — TIFF decoded via tifffile (uint16 preserved),
         temp PNG written at native bit depth via imagecodecs.

Run with:   .venv/bin/python3 converter_app.py
Requires:   bin/cjpegli  (built from github.com/google/jpegli)
            pip install Pillow tifffile imagecodecs
"""

import os
import shutil
import subprocess
import sys
import tempfile
import concurrent.futures
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import imagecodecs
import numpy as np
import tifffile
from PIL import Image

TIFF_SUFFIXES = {".tif", ".tiff"}
JPEG_SUFFIXES = {".jpg", ".jpeg"}
JXL_SUFFIXES  = {".jxl"}

RESIZE_MODES = [
    ("long_edge",  "Long Edge"),
    ("short_edge", "Short Edge"),
    ("percentage", "Percentage"),
    ("wh",         "Width & Height"),
]

# ---------------------------------------------------------------------------
# Binary detection
# ---------------------------------------------------------------------------

def _resource_root() -> Path:
    """Return the directory that contains bundled runtime resources."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


# Resolve the directory that contains runtime resources so bundled binaries are
# found both in development and in a frozen app.
_SCRIPT_DIR = _resource_root()

CJPEGLI_CANDIDATES = [
    str(_SCRIPT_DIR / "bin" / "cjpegli"),   # bundled binary (primary)
    "/opt/homebrew/bin/cjpegli",             # Apple Silicon system install
    "/usr/local/bin/cjpegli",               # Intel Mac system install
]


def find_cjpegli() -> str | None:
    for path in CJPEGLI_CANDIDATES:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    found = shutil.which("cjpegli")
    return found  # None if not installed


def find_exiftool() -> str | None:
    for path in [
        str(_SCRIPT_DIR / "bin" / "exiftool"),
        "/opt/homebrew/bin/exiftool",
        "/usr/local/bin/exiftool",
    ]:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return shutil.which("exiftool")


CJXL_CANDIDATES = [
    "/opt/homebrew/bin/cjxl",
    "/usr/local/bin/cjxl",
]


def find_cjxl() -> str | None:
    for path in CJXL_CANDIDATES:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return shutil.which("cjxl")


DJXL_CANDIDATES = [
    "/opt/homebrew/bin/djxl",
    "/usr/local/bin/djxl",
]


def find_djxl() -> str | None:
    for path in DJXL_CANDIDATES:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return shutil.which("djxl")


# ---------------------------------------------------------------------------
# Resize helper
# ---------------------------------------------------------------------------

def apply_resize(
    img: Image.Image,
    mode: str,
    value: int,
    w: int = 3000,
    h: int = 2000,
) -> Image.Image:
    """Return a resized copy of img, or the original if already within bounds."""
    orig_w, orig_h = img.size

    if mode == "long_edge":
        long = max(orig_w, orig_h)
        if long <= value:
            return img
        scale = value / long
        new_size = (round(orig_w * scale), round(orig_h * scale))
    elif mode == "short_edge":
        short = min(orig_w, orig_h)
        if short <= value:
            return img
        scale = value / short
        new_size = (round(orig_w * scale), round(orig_h * scale))
    elif mode == "percentage":
        if value == 100:
            return img
        scale = value / 100
        new_size = (round(orig_w * scale), round(orig_h * scale))
    else:  # wh
        if orig_w <= w and orig_h <= h:
            return img
        fit = img.copy()
        fit.thumbnail((w, h), Image.LANCZOS)
        return fit

    return img.resize(new_size, Image.LANCZOS)


# ---------------------------------------------------------------------------
# Image I/O helpers (16-bit aware)
# ---------------------------------------------------------------------------

def _extract_icc(src: Path) -> bytes | None:
    """Return the raw ICC profile bytes from a TIFF, or None."""
    try:
        img = Image.open(src)
        return img.info.get("icc_profile")
    except Exception:
        return None


def _read_tiff_array(src: Path) -> tuple[np.ndarray, bool]:
    """
    Read a TIFF using tifffile and return (array, is_16bit).
    array dtype is uint8 or uint16 depending on source bit depth.
    """
    arr = tifffile.imread(str(src))
    is_16bit = arr.dtype == np.uint16
    return arr, is_16bit


def _normalize_array(arr: np.ndarray) -> np.ndarray:
    """
    Normalise an image array to shape (H, W, 3) with dtype uint8 or uint16.
    Handles: RGB, RGBA (alpha-composited onto white), grayscale.
    """
    if arr.ndim == 2:
        # Grayscale → stack to RGB
        arr = np.stack([arr, arr, arr], axis=-1)
        return arr

    if arr.shape[2] == 4:
        # RGBA → composite onto white background at native bit depth
        maxval = 65535 if arr.dtype == np.uint16 else 255
        alpha = arr[:, :, 3:4].astype(np.float32) / maxval
        rgb = arr[:, :, :3].astype(np.float32)
        bg = np.full_like(rgb, float(maxval))
        composited = (rgb * alpha + bg * (1.0 - alpha))
        return composited.astype(arr.dtype)

    if arr.shape[2] == 3:
        return arr

    # Unexpected channel count — fall back to first 3 channels
    return arr[:, :, :3]


def _write_png_temp(arr: np.ndarray, path: str) -> None:
    """
    Write array to a temporary PNG file at its native bit depth.
    uint16 arrays are written as 16-bit PNG via imagecodecs;
    uint8 arrays fall back to Pillow for maximum compatibility.
    """
    if arr.dtype == np.uint16:
        encoded = imagecodecs.png_encode(arr)
        with open(path, "wb") as f:
            f.write(encoded)
    else:
        Image.fromarray(arr, mode="RGB").save(path, format="PNG")



# ---------------------------------------------------------------------------
# Conversion logic
# ---------------------------------------------------------------------------

def convert_tiff(src: Path, dst: Path, quality: int, cjpegli: str,
                 exiftool: str | None = None,
                 strip_metadata: bool = False,
                 resize_enabled: bool = False,
                 resize_mode: str = "long_edge",
                 resize_value: int = 3000,
                 resize_w: int = 3000,
                 resize_h: int = 2000) -> None:
    """
    Convert a single TIFF to JPEG via cjpegli, preserving all metadata.

    Pipeline:
      1. tifffile reads TIFF → numpy array (uint8 or uint16, bit depth preserved)
      2. normalize shape to (H, W, 3); alpha-composite RGBA at native depth
      3. optional resize via Pillow (round-trip through PIL Image)
      4. write temp PNG at native bit depth (imagecodecs for 16-bit, Pillow for 8-bit)
      5. cjpegli reads PNG → JPEG (receives 16-bit input when available)
      6. exiftool copies EXIF/IPTC/XMP from original TIFF → output JPEG
      7. exiftool embeds ICC profile extracted from original TIFF
    """
    icc_profile = _extract_icc(src)

    try:
        arr, is_16bit = _read_tiff_array(src)
    except Exception as exc:
        raise RuntimeError(f"Failed to read TIFF: {exc}") from exc

    arr = _normalize_array(arr)

    # Resize via Pillow (round-trip preserves dtype)
    if resize_enabled:
        pil_mode = "RGB" if arr.dtype == np.uint8 else "RGB"
        # Pillow only supports 8-bit RGB from uint8; for uint16 we must scale
        # down temporarily, resize, then restore.  Resize is geometric only so
        # the 8-bit precision during the resize step is fine.
        interp = Image.LANCZOS
        if arr.dtype == np.uint16:
            arr8 = (arr >> 8).astype(np.uint8)
            img_pil = Image.fromarray(arr8, mode="RGB")
        else:
            img_pil = Image.fromarray(arr, mode="RGB")
        img_pil = apply_resize(img_pil, resize_mode, resize_value, resize_w, resize_h)
        resized8 = np.array(img_pil)
        if arr.dtype == np.uint16 and resized8.shape[:2] != arr.shape[:2]:
            # Image was actually resized — scale back to uint16
            arr = (resized8.astype(np.uint16) << 8)
        elif arr.dtype == np.uint8:
            arr = resized8

    dst.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        _write_png_temp(arr, tmp_path)

        result = subprocess.run(
            [cjpegli, tmp_path, str(dst), f"--quality={quality}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "cjpegli failed")
    finally:
        os.unlink(tmp_path)

    # Copy EXIF, IPTC, XMP from original TIFF into the output JPEG
    if not strip_metadata and exiftool and dst.exists():
        subprocess.run(
            [
                exiftool,
                "-TagsFromFile", str(src),
                "-EXIF:all", "-IPTC:all", "-XMP:all",
                "-overwrite_original",
                "-quiet",
                str(dst),
            ],
            capture_output=True,
        )

        # Embed ICC profile from source TIFF
        if icc_profile:
            with tempfile.NamedTemporaryFile(suffix=".icc", delete=False) as icc_tmp:
                icc_tmp.write(icc_profile)
                icc_tmp_path = icc_tmp.name
            try:
                subprocess.run(
                    [
                        exiftool,
                        f"-ICC_Profile<={icc_tmp_path}",
                        "-overwrite_original",
                        "-quiet",
                        str(dst),
                    ],
                    capture_output=True,
                )
            finally:
                os.unlink(icc_tmp_path)


def convert_to_jxl(
    src: Path, dst: Path,
    quality: int, effort: int,
    cjxl: str,
    exiftool: str | None = None,
    strip_metadata: bool = False,
    resize_enabled: bool = False,
    resize_mode: str = "long_edge",
    resize_value: int = 3000,
    resize_w: int = 3000,
    resize_h: int = 2000,
) -> None:
    """
    Convert a single TIFF to JPEG XL via cjxl, preserving all metadata.

    Pipeline:
      1. tifffile reads TIFF → numpy array (uint8 or uint16, bit depth preserved)
      2. normalize shape to (H, W, 3); alpha-composite RGBA at native depth
      3. optional resize via Pillow (round-trip through PIL Image)
      4. write temp PNG at native bit depth (imagecodecs for 16-bit, Pillow for 8-bit)
      5. cjxl reads PNG → JXL  (--container=1 required for exiftool to write metadata)
      6. exiftool copies EXIF/IPTC/XMP from original TIFF → output JXL
      7. exiftool embeds ICC profile extracted from original TIFF

    When the source is a JPEG file, a lossless transcode path is used instead:
      cjxl input.jpg output.jxl --lossless_jpeg=1 --container=1
    The JPEG bitstream and all its metadata are preserved bit-for-bit.
    """
    # ── JPEG lossless transcode (no intermediate PNG, no re-encode) ──
    if src.suffix.lower() in JPEG_SUFFIXES:
        dst.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                cjxl, str(src), str(dst),
                "--lossless_jpeg=1",
                "--container=1",
                "--quiet",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "cjxl failed")
        return
    icc_profile = _extract_icc(src)

    try:
        arr, is_16bit = _read_tiff_array(src)
    except Exception as exc:
        raise RuntimeError(f"Failed to read TIFF: {exc}") from exc

    arr = _normalize_array(arr)

    if resize_enabled:
        if arr.dtype == np.uint16:
            arr8 = (arr >> 8).astype(np.uint8)
            img_pil = Image.fromarray(arr8, mode="RGB")
        else:
            img_pil = Image.fromarray(arr, mode="RGB")
        img_pil = apply_resize(img_pil, resize_mode, resize_value, resize_w, resize_h)
        resized8 = np.array(img_pil)
        if arr.dtype == np.uint16 and resized8.shape[:2] != arr.shape[:2]:
            arr = (resized8.astype(np.uint16) << 8)
        elif arr.dtype == np.uint8:
            arr = resized8

    dst.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        _write_png_temp(arr, tmp_path)

        result = subprocess.run(
            [
                cjxl, tmp_path, str(dst),
                f"--quality={quality}",
                f"--effort={effort}",
                "--container=1",
                "--quiet",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "cjxl failed")
    finally:
        os.unlink(tmp_path)

    if not strip_metadata and exiftool and dst.exists():
        subprocess.run(
            [
                exiftool,
                "-TagsFromFile", str(src),
                "-EXIF:all", "-IPTC:all", "-XMP:all",
                "-overwrite_original",
                "-quiet",
                str(dst),
            ],
            capture_output=True,
        )

        if icc_profile:
            with tempfile.NamedTemporaryFile(suffix=".icc", delete=False) as icc_tmp:
                icc_tmp.write(icc_profile)
                icc_tmp_path = icc_tmp.name
            try:
                subprocess.run(
                    [
                        exiftool,
                        f"-ICC_Profile<={icc_tmp_path}",
                        "-overwrite_original",
                        "-quiet",
                        str(dst),
                    ],
                    capture_output=True,
                )
            finally:
                os.unlink(icc_tmp_path)


def convert_jxl_to_jpeg(src: Path, dst: Path, djxl: str) -> None:
    """
    Reconstruct original JPEG from a JPEG XL file using djxl.
    Requires the JXL to have been created from a JPEG source with
    lossless reconstruction data (--lossless_jpeg=1, the default for JPEG input).
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [djxl, str(src), str(dst)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "djxl failed")


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class ConverterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TIFF → jpegli Converter")
        self.resizable(False, False)

        self.cjpegli = find_cjpegli()
        self.cjxl = find_cjxl()
        self.djxl = find_djxl()
        self.exiftool = find_exiftool()
        self._mode = tk.StringVar(value="folder")
        self._export_format = tk.StringVar(value="jpeg")
        self._input_hint_var = tk.StringVar(
            value="Input: TIFF or JXL  →  JPEG (round-trip reconstruct for JXL)"
        )
        self._jxl_effort = tk.IntVar(value=7)
        self._mirror_tree = tk.BooleanVar(value=False)
        self._strip_metadata = tk.BooleanVar(value=False)
        self._resize_enabled = tk.BooleanVar(value=False)
        self._resize_mode = tk.StringVar(value="long_edge")
        self._resize_value = tk.StringVar(value="3000")
        self._percentage_default_set = False
        self._resize_w = tk.StringVar(value="3000")
        self._resize_h = tk.StringVar(value="2000")
        self._input_file: Path | None = None
        self._input_dir: Path | None = None
        self._output_dir: Path | None = None
        self._tiff_files: list[Path] = []
        self._worker_count = tk.IntVar(value=2)
        self._running = False

        self._build_ui()
        self._on_format_change()
        self._check_binary()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        PAD_X = 12

        # ── Mode selector ─────────────────────────────────────────────
        frm_mode = ttk.LabelFrame(self, text="Mode")
        frm_mode.grid(row=0, column=0, sticky="ew", padx=PAD_X, pady=(12, 4))

        ttk.Radiobutton(
            frm_mode,
            text="Single File",
            value="file",
            variable=self._mode,
            command=self._on_mode_change,
        ).grid(row=0, column=0, padx=(8, 6), pady=6)
        ttk.Radiobutton(
            frm_mode,
            text="Single Folder",
            value="folder",
            variable=self._mode,
            command=self._on_mode_change,
        ).grid(row=0, column=1, padx=6, pady=6)
        ttk.Radiobutton(
            frm_mode,
            text="All Subfolders",
            value="tree",
            variable=self._mode,
            command=self._on_mode_change,
        ).grid(row=0, column=2, padx=6, pady=6)

        # ── Input picker ──────────────────────────────────────────────
        self._frm_in = ttk.LabelFrame(self, text="Input folder (TIFF files)")

        self._in_var = tk.StringVar(value="(no folder selected)")
        ttk.Label(self._frm_in, textvariable=self._in_var, width=52,
                  anchor="w").grid(row=0, column=0, padx=8, pady=4)
        self._input_btn = ttk.Button(self._frm_in, text="Browse…",
                                     command=self._pick_input)
        self._input_btn.grid(row=0, column=1, padx=(0, 8))

        # ── Output folder ─────────────────────────────────────────────
        self._frm_out = ttk.LabelFrame(self, text="Output folder")

        self._out_var = tk.StringVar(value="(same as input / converted)")
        ttk.Label(self._frm_out, textvariable=self._out_var, width=52,
                  anchor="w").grid(row=0, column=0, padx=8, pady=4)
        ttk.Button(self._frm_out, text="Browse…",
                   command=self._pick_output).grid(row=0, column=1, padx=(0, 8))

        # ── Quality slider ────────────────────────────────────────────
        self._frm_q = ttk.LabelFrame(self, text="Quality")

        self._quality = tk.IntVar(value=85)
        slider = ttk.Scale(self._frm_q, from_=1, to=100, orient="horizontal",
                           variable=self._quality, length=340,
                           command=self._update_quality_label)
        slider.grid(row=0, column=0, padx=10, pady=(6, 2))

        self._q_label = ttk.Label(self._frm_q, text=self._quality_label_text(), width=44)
        self._q_label.grid(row=1, column=0, padx=10, pady=(0, 6))

        # ── Export format ─────────────────────────────────────────────
        self._frm_format = ttk.LabelFrame(self, text="Export format")

        ttk.Radiobutton(
            self._frm_format,
            text="JPEG",
            value="jpeg",
            variable=self._export_format,
            command=self._on_format_change,
        ).grid(row=0, column=0, padx=(8, 6), pady=6)
        ttk.Radiobutton(
            self._frm_format,
            text="JXL",
            value="jxl",
            variable=self._export_format,
            command=self._on_format_change,
        ).grid(row=0, column=1, padx=6, pady=6)

        self._input_hint_lbl = ttk.Label(
            self._frm_format, textvariable=self._input_hint_var,
            foreground="gray",
        )
        self._input_hint_lbl.grid(row=1, column=0, columnspan=2, padx=8, pady=(0, 6), sticky="w")

        # ── JXL Encode Effort ─────────────────────────────────────────
        self._frm_effort = ttk.LabelFrame(self, text="JXL Encode Effort")

        effort_slider = ttk.Scale(
            self._frm_effort, from_=1, to=9, orient="horizontal",
            variable=self._jxl_effort, length=340,
            command=self._update_effort_label,
        )
        effort_slider.grid(row=0, column=0, padx=10, pady=(6, 2))

        self._effort_label = ttk.Label(
            self._frm_effort, text=self._effort_label_text(), width=52,
        )
        self._effort_label.grid(row=1, column=0, padx=10, pady=(0, 6))

        # ── Folder structure options ─────────────────────────────────
        self._frm_structure = ttk.LabelFrame(self, text="Folder structure")

        self._mirror_chk = ttk.Checkbutton(
            self._frm_structure,
            text="Mirror folder structure to output folder",
            variable=self._mirror_tree,
            command=self._scan_files,
        )
        self._mirror_chk.grid(row=0, column=0, sticky="w", padx=8, pady=6)

        # ── Image Sizing ──────────────────────────────────────────────
        self._frm_size = ttk.LabelFrame(self, text="Image Sizing")

        ttk.Checkbutton(
            self._frm_size,
            text="Resize images",
            variable=self._resize_enabled,
            command=self._on_resize_toggle,
        ).grid(row=0, column=0, columnspan=5, sticky="w", padx=8, pady=(6, 2))

        self._resize_row = ttk.Frame(self._frm_size)
        self._resize_row.grid(row=1, column=0, sticky="w", padx=8, pady=(0, 6))

        mode_labels = [label for _, label in RESIZE_MODES]
        self._resize_combo = ttk.Combobox(
            self._resize_row, values=mode_labels, state="readonly", width=16
        )
        self._resize_combo.set("Long Edge")
        self._resize_combo.grid(row=0, column=0, padx=(0, 8))
        self._resize_combo.bind("<<ComboboxSelected>>", self._on_resize_mode_change)

        self._resize_val_entry = ttk.Entry(
            self._resize_row, textvariable=self._resize_value, width=7
        )
        self._resize_val_entry.grid(row=0, column=1)

        self._resize_w_entry = ttk.Entry(
            self._resize_row, textvariable=self._resize_w, width=7
        )
        self._resize_w_entry.grid(row=0, column=1)

        self._resize_mul_lbl = ttk.Label(self._resize_row, text="x")
        self._resize_mul_lbl.grid(row=0, column=2, padx=4)

        self._resize_h_entry = ttk.Entry(
            self._resize_row, textvariable=self._resize_h, width=7
        )
        self._resize_h_entry.grid(row=0, column=3)

        self._resize_unit_lbl = ttk.Label(self._resize_row, text="px", width=3)
        self._resize_unit_lbl.grid(row=0, column=4, padx=(4, 0))

        # Start hidden; shown when checkbox is ticked
        self._resize_row.grid_remove()

        # ── Metadata options ─────────────────────────────────────────
        self._frm_metadata = ttk.LabelFrame(self, text="Metadata")

        self._strip_meta_chk = ttk.Checkbutton(
            self._frm_metadata,
            text="Strip all metadata",
            variable=self._strip_metadata,
            command=self._update_metadata_status_visibility,
        )
        self._strip_meta_chk.grid(row=0, column=0, sticky="w", padx=8, pady=6)

        # ── File list ─────────────────────────────────────────────────
        self._frm_list = ttk.LabelFrame(self, text="Files found")

        self._listbox = tk.Listbox(self._frm_list, height=8, width=62,
                                   selectmode="browse", font=("Menlo", 11))
        scrollbar = ttk.Scrollbar(self._frm_list, orient="vertical",
                                  command=self._listbox.yview)
        self._listbox.configure(yscrollcommand=scrollbar.set)
        self._listbox.grid(row=0, column=0, padx=(8, 0), pady=6)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=6)

        self._count_label = ttk.Label(self._frm_list, text="No files selected.")
        self._count_label.grid(row=1, column=0, columnspan=2,
                                padx=8, pady=(0, 6), sticky="w")

        # ── Progress ──────────────────────────────────────────────────
        self._frm_prog = ttk.Frame(self)

        self._progress = ttk.Progressbar(self._frm_prog, length=400, mode="determinate")
        self._progress.grid(row=0, column=0, padx=(0, 10))

        self._status_var = tk.StringVar(value="Ready.")
        ttk.Label(self._frm_prog, textvariable=self._status_var, width=18,
                  anchor="w").grid(row=0, column=1)

        # ── Metadata status ───────────────────────────────────────────
        self._frm_meta = ttk.Frame(self)
        self._frm_meta.grid(row=8, column=0, sticky="w", padx=PAD_X, pady=(0, 4))
        self._meta_var = tk.StringVar()
        ttk.Label(self._frm_meta, textvariable=self._meta_var,
                  foreground="gray").grid(row=0, column=0)

        # ── Parallel conversions ──────────────────────────────────────
        self._frm_workers = ttk.LabelFrame(self, text="Parallel conversions")

        for value, label in [(1, "1  (sequential)"), (2, "2  (recommended)"), (4, "4  (fast)"), (6, "6  (fastest)")]:
            ttk.Radiobutton(
                self._frm_workers,
                text=label,
                value=value,
                variable=self._worker_count,
            ).grid(row=0, column=value - 1, padx=(8 if value == 1 else 6, 6), pady=6)

        # ── Convert button ────────────────────────────────────────────
        self._convert_btn = ttk.Button(self, text="Convert",
                                       command=self._start_conversion)

        self.columnconfigure(0, weight=1)
        self._on_mode_change()
        self._update_metadata_status_visibility()

    def _apply_mode_layout(self):
        PAD_X = 12
        mode = self._mode.get()

        row = 1

        self._frm_in.grid(row=row, column=0, sticky="ew", padx=PAD_X, pady=4)
        row += 1

        if mode == "file":
            self._frm_out.grid_remove()
        else:
            self._frm_out.grid(row=row, column=0, sticky="ew", padx=PAD_X, pady=4)
            row += 1

        self._frm_format.grid(row=row, column=0, sticky="ew", padx=PAD_X, pady=4)
        row += 1

        self._frm_q.grid(row=row, column=0, sticky="ew", padx=PAD_X, pady=4)
        row += 1

        if self._export_format.get() == "jxl":
            self._frm_effort.grid(row=row, column=0, sticky="ew", padx=PAD_X, pady=4)
            row += 1
        else:
            self._frm_effort.grid_remove()

        if mode == "tree":
            self._frm_structure.grid(row=row, column=0, sticky="ew", padx=PAD_X, pady=4)
            row += 1
        else:
            self._frm_structure.grid_remove()

        self._frm_size.grid(row=row, column=0, sticky="ew", padx=PAD_X, pady=4)
        row += 1

        self._frm_metadata.grid(row=row, column=0, sticky="ew", padx=PAD_X, pady=4)
        row += 1

        self._frm_list.grid(row=row, column=0, sticky="ew", padx=PAD_X, pady=4)
        row += 1

        self._frm_prog.grid(row=row, column=0, sticky="ew", padx=PAD_X, pady=4)
        row += 1

        self._frm_meta.grid(row=row, column=0, sticky="w", padx=PAD_X, pady=(0, 4))
        row += 1

        self._frm_workers.grid(row=row, column=0, sticky="ew", padx=PAD_X, pady=4)
        row += 1

        self._convert_btn.grid(row=row, column=0, pady=(4, 14))

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _check_binary(self):
        if not self.cjpegli:
            messagebox.showerror(
                "cjpegli not found",
                "cjpegli was not found.\n\n"
                "Expected location:  bin/cjpegli\n\n"
                "Build it from source:\n"
                "  https://github.com/google/jpegli\n\n"
                "See plan.md for full build instructions.",
            )
            self._convert_btn.state(["disabled"])

        if self.exiftool:
            self._meta_var.set("✓ Metadata transfer enabled (EXIF · IPTC · XMP · ICC)")
        else:
            self._meta_var.set("⚠ exiftool not found — ICC profile only, no EXIF/XMP transfer.")

        self._update_metadata_status_visibility()

    def _on_resize_toggle(self):
        if self._resize_enabled.get():
            self._resize_row.grid()
            self._on_resize_mode_change()
        else:
            self._resize_row.grid_remove()

    def _on_resize_mode_change(self, _event=None):
        label = self._resize_combo.get()
        mode = next((k for k, v in RESIZE_MODES if v == label), "long_edge")
        self._resize_mode.set(mode)
        if mode == "wh":
            self._resize_val_entry.grid_remove()
            self._resize_w_entry.grid()
            self._resize_mul_lbl.grid()
            self._resize_h_entry.grid()
            self._resize_unit_lbl.config(text="px")
        elif mode == "percentage":
            if not self._percentage_default_set:
                self._resize_value.set("100")
                self._percentage_default_set = True
            self._resize_w_entry.grid_remove()
            self._resize_mul_lbl.grid_remove()
            self._resize_h_entry.grid_remove()
            self._resize_val_entry.grid()
            self._resize_unit_lbl.config(text="%")
        else:
            self._resize_w_entry.grid_remove()
            self._resize_mul_lbl.grid_remove()
            self._resize_h_entry.grid_remove()
            self._resize_val_entry.grid()
            self._resize_unit_lbl.config(text="px")

    def _update_metadata_status_visibility(self):
        if self._strip_metadata.get():
            self._frm_meta.grid_remove()
        else:
            self._frm_meta.grid()

    def _on_mode_change(self):
        mode = self._mode.get()
        fmt = self._export_format.get()

        if fmt == "jxl":
            folder_label = "Input folder (TIFF + JPEG files)"
            tree_label   = "Input root folder (recursive TIFF + JPEG scan)"
            file_label   = "Input TIFF or JPEG file"
        else:
            folder_label = "Input folder (TIFF + JXL files)"
            tree_label   = "Input root folder (recursive TIFF + JXL scan)"
            file_label   = "Input TIFF or JXL file"

        if mode == "file":
            self._frm_in.config(text=file_label)
            self._in_var.set(str(self._input_file) if self._input_file else "(no file selected)")
            self._mirror_tree.set(False)
            if self._output_dir is None:
                self._out_var.set("(same as input / converted)")
        elif mode == "folder":
            self._frm_in.config(text=folder_label)
            self._in_var.set(str(self._input_dir) if self._input_dir else "(no folder selected)")
            self._mirror_tree.set(False)
            if self._output_dir is None:
                self._out_var.set("(same as input / converted)")
        else:
            self._frm_in.config(text=tree_label)
            self._in_var.set(str(self._input_dir) if self._input_dir else "(no folder selected)")
            if self._output_dir is None:
                self._out_var.set("(same as input folders in /converted)")

        self._apply_mode_layout()
        self._scan_files()

    def _pick_input(self):
        fmt = self._export_format.get()
        if fmt == "jxl":
            filetypes = [
                ("TIFF / JPEG files", "*.tif *.tiff *.jpg *.jpeg"),
                ("All files", "*"),
            ]
            file_title = "Select a TIFF or JPEG file"
        else:
            filetypes = [
                ("TIFF / JXL files", "*.tif *.tiff *.jxl"),
                ("All files", "*"),
            ]
            file_title = "Select a TIFF or JXL file"

        if self._mode.get() == "file":
            file_path = filedialog.askopenfilename(
                title=file_title,
                filetypes=filetypes,
            )
            if not file_path:
                return
            self._input_file = Path(file_path)
            self._input_dir = self._input_file.parent
            self._in_var.set(str(self._input_file))
            self._scan_files()
            return

        d = filedialog.askdirectory(title="Select folder containing TIFF files")
        if not d:
            return
        self._input_dir = Path(d)
        self._input_file = None
        self._in_var.set(str(self._input_dir))

        if self._output_dir is None and self._mode.get() == "folder":
            default_out = self._input_dir / "converted"
            self._output_dir = default_out
            self._out_var.set(str(default_out))
        elif self._output_dir is None and self._mode.get() == "tree":
            self._out_var.set("(same as input folders in /converted)")

        self._scan_files()

    def _pick_output(self):
        d = filedialog.askdirectory(title="Select output folder")
        if d:
            self._output_dir = Path(d)
            self._out_var.set(str(self._output_dir))

    def _scan_files(self):
        mode = self._mode.get()
        fmt = self._export_format.get()

        if fmt == "jxl":
            accepted = TIFF_SUFFIXES | JPEG_SUFFIXES
        else:
            accepted = TIFF_SUFFIXES | JXL_SUFFIXES

        if mode == "file":
            files = [self._input_file] if self._input_file and self._input_file.exists() else []
        elif mode == "folder":
            if not self._input_dir:
                files = []
            else:
                files = sorted(
                    p for p in self._input_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in accepted
                )
        else:
            if not self._input_dir:
                files = []
            else:
                files = sorted(
                    p for p in self._input_dir.rglob("*")
                    if p.is_file() and p.suffix.lower() in accepted
                )

        self._tiff_files = files
        self._listbox.delete(0, tk.END)
        for f in files:
            if mode == "tree" and self._input_dir:
                self._listbox.insert(tk.END, str(f.relative_to(self._input_dir)))
            else:
                self._listbox.insert(tk.END, f.name)
        n = len(files)
        self._count_label.config(
            text=f"{n} file{'s' if n != 1 else ''} found."
        )

    def _compute_output_path(self, src: Path) -> Path:
        ext = ".jxl" if self._export_format.get() == "jxl" else ".jpg"
        mode = self._mode.get()

        if mode == "file":
            return src.parent / (src.stem + ext)

        if mode == "folder":
            if not self._output_dir:
                raise RuntimeError("Output folder not set")
            return self._output_dir / (src.stem + ext)

        if self._mirror_tree.get():
            if not self._output_dir or not self._input_dir:
                raise RuntimeError("Output or input folder not set")
            rel_parent = src.relative_to(self._input_dir).parent
            return self._output_dir / rel_parent / (src.stem + ext)

        return src.parent / "converted" / (src.stem + ext)

    def _update_quality_label(self, _=None):
        self._q_label.config(text=self._quality_label_text())

    def _quality_label_text(self) -> str:
        q = int(self._quality.get())
        if self._export_format.get() == "jxl":
            if q == 100:
                desc = "Lossless (exact pixel reproduction)"
            elif q >= 90:
                desc = "Visually lossless"
            elif q >= 75:
                desc = "High quality"
            elif q >= 68:
                desc = "Good quality (recommended range)"
            else:
                desc = "Compressed"
        else:
            labels = {
                range(90, 101): "Maximum quality",
                range(70, 90):  "High quality",
                range(40, 70):  "Balanced",
                range(1, 40):   "Smaller files",
            }
            desc = next((v for k, v in labels.items() if q in k), "")
        return f"Quality: {q} / 100  —  {desc}"

    def _effort_label_text(self) -> str:
        e = int(self._jxl_effort.get())
        names = {
            1: "lightning", 2: "thunder", 3: "falcon", 4: "cheetah",
            5: "hare", 6: "wombat", 7: "squirrel", 8: "kitten", 9: "tortoise",
        }
        name = names.get(e, str(e))
        if e < 7:
            hint = "  (faster encode)"
        elif e == 7:
            hint = "  (default; recommended)"
        else:
            hint = "  (slower, better compression)"
        return f"Effort: {e} / 9  —  {name}{hint}"

    def _update_effort_label(self, _=None):
        self._effort_label.config(text=self._effort_label_text())

    def _on_format_change(self):
        fmt = self._export_format.get()
        if fmt == "jxl":
            self._quality.set(90)
            self._input_hint_var.set("Input: TIFF or JPEG  →  JXL (lossless transcode for JPEG)")
            if self.cjxl:
                self._convert_btn.state(["!disabled"])
            else:
                self._convert_btn.state(["disabled"])
        else:
            self._quality.set(85)
            self._input_hint_var.set("Input: TIFF or JXL  →  JPEG (round-trip reconstruct for JXL)")
            if self.cjpegli:
                self._convert_btn.state(["!disabled"])
            else:
                self._convert_btn.state(["disabled"])
        self._update_quality_label()
        self._apply_mode_layout()
        self._scan_files()

    def _parse_resize_params(self) -> tuple[bool, str, int, int, int]:
        """Validate and return (enabled, mode, value, w, h). Raises ValueError on bad input."""
        if not self._resize_enabled.get():
            return False, "", 0, 0, 0
        mode = self._resize_mode.get()
        try:
            if mode == "wh":
                w = int(self._resize_w.get())
                h = int(self._resize_h.get())
                if w <= 0 or h <= 0:
                    raise ValueError
                return True, mode, 0, w, h
            else:
                val = int(self._resize_value.get())
                if val <= 0:
                    raise ValueError
                return True, mode, val, 0, 0
        except ValueError as exc:
            label = next((v for k, v in RESIZE_MODES if k == mode), mode)
            detail = str(exc) if str(exc) else "Enter a valid positive number."
            raise ValueError(f"Image Sizing — {label}: {detail}") from None

    def _start_conversion(self):
        if self._running:
            return
        if not self._tiff_files:
            messagebox.showwarning("No files", "No files found for the selected mode.")
            return

        mode = self._mode.get()
        if mode == "folder" and not self._output_dir:
            messagebox.showwarning("No output", "Please choose an output folder.")
            return
        if mode == "tree" and self._mirror_tree.get() and not self._output_dir:
            messagebox.showwarning("No output", "Please choose an output folder for mirrored output.")
            return

        fmt = self._export_format.get()
        if fmt == "jxl" and not self.cjxl:
            messagebox.showerror(
                "cjxl not found",
                "cjxl was not found.\n\n"
                "Install it with:\n"
                "  brew install jpeg-xl",
            )
            return
        if fmt == "jpeg" and not self.cjpegli:
            messagebox.showerror(
                "cjpegli not found",
                "cjpegli is required for JPEG export but was not found.",
            )
            return
        if fmt == "jpeg" and not self.djxl:
            has_jxl_input = any(
                f.suffix.lower() in JXL_SUFFIXES for f in self._tiff_files
            )
            if has_jxl_input:
                messagebox.showerror(
                    "djxl not found",
                    "djxl is required to reconstruct JPEG from JXL files but was not found.\n\n"
                    "Install it with:\n"
                    "  brew install jpeg-xl",
                )
                return

        try:
            self._parse_resize_params()
        except ValueError as exc:
            messagebox.showwarning("Invalid resize setting", str(exc))
            return

        self._running = True
        self._convert_btn.state(["disabled"])
        for child in self._frm_workers.winfo_children():
            child.state(["disabled"])
        threading.Thread(target=self._run_conversion, daemon=True).start()

    def _convert_one(self, src: Path, fmt: str, quality: int, effort: int,
                      strip_metadata: bool, resize_enabled: bool,
                      resize_mode: str, resize_value: int,
                      resize_w: int, resize_h: int) -> None:
        """Convert a single file. Runs inside a worker thread."""
        dst = self._compute_output_path(src)
        src_ext = src.suffix.lower()
        if fmt == "jxl":
            convert_to_jxl(
                src, dst, quality, effort, self.cjxl,
                self.exiftool,
                strip_metadata=strip_metadata,
                resize_enabled=resize_enabled,
                resize_mode=resize_mode,
                resize_value=resize_value,
                resize_w=resize_w,
                resize_h=resize_h,
            )
        elif src_ext in JXL_SUFFIXES:
            convert_jxl_to_jpeg(src, dst, self.djxl)
        else:
            convert_tiff(
                src, dst, quality, self.cjpegli, self.exiftool,
                strip_metadata=strip_metadata,
                resize_enabled=resize_enabled,
                resize_mode=resize_mode,
                resize_value=resize_value,
                resize_w=resize_w,
                resize_h=resize_h,
            )

    def _run_conversion(self):
        files = self._tiff_files
        total = len(files)
        quality = int(self._quality.get())
        effort = int(self._jxl_effort.get())
        fmt = self._export_format.get()
        strip_metadata = self._strip_metadata.get()
        workers = self._worker_count.get()
        resize_enabled, resize_mode, resize_value, resize_w, resize_h = self._parse_resize_params()
        errors: list[str] = []

        self._set_progress(0, total)
        self._update_status(f"0 / {total}")

        lock = threading.Lock()
        done_count = [0]  # mutable container for closure

        def run_one(src: Path):
            self._convert_one(
                src, fmt, quality, effort, strip_metadata,
                resize_enabled, resize_mode, resize_value, resize_w, resize_h,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_src = {pool.submit(run_one, src): src for src in files}
            for future in concurrent.futures.as_completed(future_to_src):
                src = future_to_src[future]
                try:
                    future.result()
                except Exception as exc:
                    errors.append(f"{src.name}: {exc}")
                with lock:
                    done_count[0] += 1
                    count = done_count[0]
                self.after(0, lambda c=count: self._set_progress(c, total))
                self.after(0, lambda c=count: self._update_status(f"{c} / {total}"))

        self._running = False
        self.after(0, self._on_done, total, errors)

    def _set_progress(self, value: int, maximum: int):
        pct = int(value / maximum * 100) if maximum else 0
        self.after(0, lambda: self._progress.config(value=pct))

    def _update_status(self, text: str):
        self.after(0, lambda: self._status_var.set(text))

    def _on_done(self, total: int, errors: list[str]):
        self._convert_btn.state(["!disabled"])
        for child in self._frm_workers.winfo_children():
            child.state(["!disabled"])
        self._update_status("Done.")

        ok = total - len(errors)
        msg = f"Converted {ok} of {total} file{'s' if total != 1 else ''} successfully."
        if errors:
            msg += f"\n\n{len(errors)} error{'s' if len(errors) != 1 else ''}:\n"
            msg += "\n".join(f"  • {e}" for e in errors)
            messagebox.showwarning("Conversion complete", msg)
        else:
            messagebox.showinfo("Conversion complete", msg)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = ConverterApp()
    app.mainloop()
