#!/usr/bin/env python3
"""
TIFF → jpegli Batch Converter
Phase 1: Convert .tif/.tiff files to high-quality JPEG using cjpegli.

Run with:   .venv/bin/python3 converter_app.py
Requires:   bin/cjpegli  (built from github.com/google/jpegli)
            pip install Pillow numpy
"""

import os
import shutil
import subprocess
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image

# ---------------------------------------------------------------------------
# Binary detection
# ---------------------------------------------------------------------------

# Resolve the directory where this script lives, so bin/cjpegli is found
# regardless of the working directory.
_SCRIPT_DIR = Path(__file__).resolve().parent

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


# ---------------------------------------------------------------------------
# Conversion logic
# ---------------------------------------------------------------------------

def convert_tiff(src: Path, dst: Path, quality: int, cjpegli: str) -> None:
    """Convert a single TIFF file to JPEG via cjpegli using a temp PPM."""
    img = Image.open(src)

    # Ensure RGB (handles grayscale, RGBA, palette, etc.)
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # Detect bit depth
    arr = np.array(img)
    if arr.dtype == np.uint16:
        # Write 16-bit PPM (P6 with maxval 65535)
        with tempfile.NamedTemporaryFile(suffix=".ppm", delete=False) as tmp:
            tmp_path = tmp.name
        _write_ppm16(arr, tmp_path)
    else:
        # Convert to uint8 if needed, write 8-bit PPM
        if arr.dtype != np.uint8:
            arr = (arr / arr.max() * 255).astype(np.uint8)
        with tempfile.NamedTemporaryFile(suffix=".ppm", delete=False) as tmp:
            tmp_path = tmp.name
        _write_ppm8(arr, tmp_path)

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [cjpegli, tmp_path, str(dst), f"--quality={quality}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "cjpegli failed")
    finally:
        os.unlink(tmp_path)


def _write_ppm8(arr: np.ndarray, path: str) -> None:
    h, w, _ = arr.shape
    with open(path, "wb") as f:
        f.write(f"P6\n{w} {h}\n255\n".encode())
        f.write(arr.tobytes())


def _write_ppm16(arr: np.ndarray, path: str) -> None:
    h, w, _ = arr.shape
    with open(path, "wb") as f:
        f.write(f"P6\n{w} {h}\n65535\n".encode())
        # PPM requires big-endian 16-bit
        f.write(arr.astype(">u2").tobytes())


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class ConverterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TIFF → jpegli Converter")
        self.resizable(False, False)

        self.cjpegli = find_cjpegli()
        self._input_dir: Path | None = None
        self._output_dir: Path | None = None
        self._tiff_files: list[Path] = []
        self._running = False

        self._build_ui()
        self._check_binary()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        PAD_X = 12

        # ── Input folder ──────────────────────────────────────────────
        frm_in = ttk.LabelFrame(self, text="Input folder (TIFF files)")
        frm_in.grid(row=0, column=0, sticky="ew", padx=PAD_X, pady=(12, 4))

        self._in_var = tk.StringVar(value="(no folder selected)")
        ttk.Label(frm_in, textvariable=self._in_var, width=52,
                  anchor="w").grid(row=0, column=0, padx=8, pady=4)
        ttk.Button(frm_in, text="Browse…",
                   command=self._pick_input).grid(row=0, column=1, padx=(0, 8))

        # ── Output folder ─────────────────────────────────────────────
        frm_out = ttk.LabelFrame(self, text="Output folder")
        frm_out.grid(row=1, column=0, sticky="ew", padx=PAD_X, pady=4)

        self._out_var = tk.StringVar(value="(same as input / converted)")
        ttk.Label(frm_out, textvariable=self._out_var, width=52,
                  anchor="w").grid(row=0, column=0, padx=8, pady=4)
        ttk.Button(frm_out, text="Browse…",
                   command=self._pick_output).grid(row=0, column=1, padx=(0, 8))

        # ── Quality slider ────────────────────────────────────────────
        frm_q = ttk.LabelFrame(self, text="Quality")
        frm_q.grid(row=2, column=0, sticky="ew", padx=PAD_X, pady=4)

        self._quality = tk.IntVar(value=85)
        slider = ttk.Scale(frm_q, from_=1, to=100, orient="horizontal",
                           variable=self._quality, length=340,
                           command=self._update_quality_label)
        slider.grid(row=0, column=0, padx=10, pady=(6, 2))

        self._q_label = ttk.Label(frm_q, text=self._quality_label_text(), width=32)
        self._q_label.grid(row=1, column=0, padx=10, pady=(0, 6))

        # ── File list ─────────────────────────────────────────────────
        frm_list = ttk.LabelFrame(self, text="Files found")
        frm_list.grid(row=3, column=0, sticky="ew", padx=PAD_X, pady=4)

        self._listbox = tk.Listbox(frm_list, height=8, width=62,
                                   selectmode="browse", font=("Menlo", 11))
        scrollbar = ttk.Scrollbar(frm_list, orient="vertical",
                                  command=self._listbox.yview)
        self._listbox.configure(yscrollcommand=scrollbar.set)
        self._listbox.grid(row=0, column=0, padx=(8, 0), pady=6)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=6)

        self._count_label = ttk.Label(frm_list, text="No files selected.")
        self._count_label.grid(row=1, column=0, columnspan=2,
                                padx=8, pady=(0, 6), sticky="w")

        # ── Progress ──────────────────────────────────────────────────
        frm_prog = ttk.Frame(self)
        frm_prog.grid(row=4, column=0, sticky="ew", padx=PAD_X, pady=4)

        self._progress = ttk.Progressbar(frm_prog, length=400, mode="determinate")
        self._progress.grid(row=0, column=0, padx=(0, 10))

        self._status_var = tk.StringVar(value="Ready.")
        ttk.Label(frm_prog, textvariable=self._status_var, width=18,
                  anchor="w").grid(row=0, column=1)

        # ── Convert button ────────────────────────────────────────────
        self._convert_btn = ttk.Button(self, text="Convert",
                                       command=self._start_conversion)
        self._convert_btn.grid(row=5, column=0, pady=(4, 14))

        self.columnconfigure(0, weight=1)

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

    def _pick_input(self):
        d = filedialog.askdirectory(title="Select folder containing TIFF files")
        if not d:
            return
        self._input_dir = Path(d)
        self._in_var.set(str(self._input_dir))

        # Default output = input/converted/
        if self._output_dir is None:
            default_out = self._input_dir / "converted"
            self._output_dir = default_out
            self._out_var.set(str(default_out))

        self._scan_files()

    def _pick_output(self):
        d = filedialog.askdirectory(title="Select output folder")
        if d:
            self._output_dir = Path(d)
            self._out_var.set(str(self._output_dir))

    def _scan_files(self):
        if not self._input_dir:
            return
        files = sorted(
            p for p in self._input_dir.iterdir()
            if p.suffix.lower() in {".tif", ".tiff"}
        )
        self._tiff_files = files
        self._listbox.delete(0, tk.END)
        for f in files:
            self._listbox.insert(tk.END, f.name)
        n = len(files)
        self._count_label.config(
            text=f"{n} TIFF file{'s' if n != 1 else ''} found."
        )

    def _update_quality_label(self, _=None):
        self._q_label.config(text=self._quality_label_text())

    def _quality_label_text(self) -> str:
        q = int(self._quality.get())
        labels = {
            range(90, 101): "Maximum quality",
            range(70, 90):  "High quality",
            range(40, 70):  "Balanced",
            range(1, 40):   "Smaller files",
        }
        desc = next((v for k, v in labels.items() if q in k), "")
        return f"Quality: {q} / 100  —  {desc}"

    def _start_conversion(self):
        if self._running:
            return
        if not self._tiff_files:
            messagebox.showwarning("No files", "No TIFF files found in the input folder.")
            return
        if not self._output_dir:
            messagebox.showwarning("No output", "Please choose an output folder.")
            return

        self._running = True
        self._convert_btn.state(["disabled"])
        threading.Thread(target=self._run_conversion, daemon=True).start()

    def _run_conversion(self):
        files = self._tiff_files
        total = len(files)
        quality = int(self._quality.get())
        errors: list[str] = []

        self._set_progress(0, total)

        for i, src in enumerate(files, start=1):
            dst = self._output_dir / (src.stem + ".jpg")
            self._update_status(f"{i - 1} / {total}")
            try:
                convert_tiff(src, dst, quality, self.cjpegli)
            except Exception as exc:
                errors.append(f"{src.name}: {exc}")
            self._set_progress(i, total)
            self._update_status(f"{i} / {total}")

        self._running = False
        self.after(0, self._on_done, total, errors)

    def _set_progress(self, value: int, maximum: int):
        pct = int(value / maximum * 100) if maximum else 0
        self.after(0, lambda: self._progress.config(value=pct))

    def _update_status(self, text: str):
        self.after(0, lambda: self._status_var.set(text))

    def _on_done(self, total: int, errors: list[str]):
        self._convert_btn.state(["!disabled"])
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
