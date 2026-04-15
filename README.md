# TIFF → jpegli Converter

A macOS desktop app that converts TIFF files to high-quality JPEG using Google's [jpegli](https://github.com/google/jpegli) encoder.

jpegli is currently one of the strongest JPEG encoders available for real-world photo export workflows because it improves quality-per-byte while remaining 100% baseline JPEG compatible. In practice, compared with older libjpeg-style encoders used in many photo apps and pipelines, jpegli typically delivers:

- smaller files at the same visual quality (often around 20-35%, and in some cases more)
- better detail and smoother tonal transitions at the same file size
- improved handling of high-precision source data before final JPEG quantization

Important precision note: final JPEG files are still standard 8-bit JPEG (for maximum compatibility), but jpegli can encode from higher-precision source buffers internally. In this app, 16-bit TIFF input is preserved through a 16-bit temporary PNG into jpegli, so the encoder starts from higher-fidelity source data instead of an early 8-bit truncation.

By default, metadata is preserved in the output — EXIF (camera make/model, exposure, GPS, etc.), IPTC, XMP, and ICC colour profile. You can also force metadata stripping with one checkbox.

---

## Requirements

- macOS (Apple Silicon or Intel)
- Python 3.12+ with `tkinter` — install via `brew install python-tk`
- `tifffile` and `imagecodecs` (installed via `requirements.txt`)
- [ExifTool](https://exiftool.org) — `brew install exiftool` (optional, enables metadata transfer)

The `cjpegli` encoder binary is bundled in `bin/cjpegli` — no separate install needed.

---

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/halebop17/jpegli-converter.git
cd jpegli-converter

# 2. Create a virtual environment and install dependencies
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

---

## Running the app

**Double-click** `TIFF Converter.app` in the project folder.

Or from the terminal:

```bash
.venv/bin/python3 converter_app.py
```

---

## Interface

| Setting | Description |
|---|---|
| **Mode** | `Single File`, `Single Folder`, or `All Subfolders`. |
| **Input** | In `Single File` mode, choose one `.tif/.tiff` file. In folder modes, choose a folder. |
| **Output folder** | Used in `Single Folder` mode and in recursive mirror mode. |
| **Mirror folder structure to output folder** | Only for `All Subfolders` mode. Recreates the full input folder tree inside the selected output folder. |
| **Resize images** | Optional image sizing with modes: `Long Edge`, `Short Edge`, `Percentage`, `Width & Height`. |
| **Strip all metadata** | When checked, output JPEGs contain no EXIF/IPTC/XMP/ICC metadata. Default is unchecked (metadata preserved). |
| **Quality** | JPEG quality from 1 (smallest) to 100 (best). The recommended range is **75–95**. At 85 you get excellent results with ~30–50 % smaller files than standard JPEG at the same setting. |
| **Metadata status** | Shows ✓ if ExifTool is detected (EXIF · IPTC · XMP · ICC will be transferred) or ⚠ if it is missing. |

Click **Convert** to start. A progress bar tracks each file as it is processed.

---

## How it works

1. The app finds TIFF files based on the selected mode (single file, top folder only, or recursive).
2. `tifffile` reads each TIFF into a NumPy array (preserving source bit depth, including 16-bit TIFF data).
3. The app normalizes channels (RGB / grayscale / RGBA compositing) and applies optional resize.
4. The image is written to a temporary PNG intermediary:
	- 16-bit TIFF source -> 16-bit PNG intermediary
	- 8-bit TIFF source -> 8-bit PNG intermediary
5. `cjpegli` encodes that PNG to JPEG at the chosen quality.
6. If `Strip all metadata` is unchecked, ExifTool copies EXIF/IPTC/XMP and embeds ICC.
7. If `Strip all metadata` is checked, metadata copy/embed is skipped.
8. The temporary PNG is deleted.

---

## Notes

- RGBA TIFFs are composited onto a white background before encoding (JPEG does not support transparency).
- The intermediary PNG is lossless. For 16-bit TIFFs, the intermediary is explicitly written as 16-bit PNG, so `cjpegli` receives high-precision input.
- Final output is still standard JPEG (8-bit format), but jpegli processes from the higher-precision source path when available.
- If ExifTool is not installed, conversion still works — only metadata transfer is skipped.
- In `All Subfolders` mode with mirror disabled, each source folder gets its own `converted/` subfolder.
