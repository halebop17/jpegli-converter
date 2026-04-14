# TIFF → jpegli Converter

A macOS desktop app that batch-converts TIFF files to high-quality JPEG using Google's [jpegli](https://github.com/google/jpegli) encoder. jpegli produces smaller files than standard libjpeg at the same perceived quality, while staying fully compatible with every JPEG decoder.

All metadata is preserved in the output — EXIF (camera make/model, exposure, GPS, etc.), IPTC, XMP, and ICC colour profile.

---

## Requirements

- macOS (Apple Silicon or Intel)
- Python 3.12+ with `tkinter` — install via `brew install python-tk`
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
| **Input folder** | Folder containing `.tif` / `.tiff` files to convert. All TIFF files in the folder are listed automatically. |
| **Output folder** | Where the converted JPEGs are saved. Defaults to an `output/` subfolder inside the input folder if left blank. |
| **Quality** | JPEG quality from 1 (smallest) to 100 (best). The recommended range is **75–95**. At 85 you get excellent results with ~30–50 % smaller files than standard JPEG at the same setting. |
| **Metadata status** | Shows ✓ if ExifTool is detected (EXIF · IPTC · XMP · ICC will be transferred) or ⚠ if it is missing. |

Click **Convert** to start. A progress bar tracks each file as it is processed.

---

## How it works

1. Pillow opens each TIFF and extracts the embedded ICC colour profile.
2. The image is written to a temporary PNG (lossless intermediary).
3. `cjpegli` encodes the PNG to JPEG at the chosen quality.
4. ExifTool copies EXIF, IPTC and XMP tags from the original TIFF into the JPEG.
5. The ICC profile bytes are embedded directly into the JPEG via ExifTool.
6. The temporary PNG is deleted.

---

## Notes

- RGBA TIFFs are composited onto a white background before encoding (JPEG does not support transparency).
- 16-bit TIFFs are handled correctly by Pillow before being passed to cjpegli.
- If ExifTool is not installed, conversion still works — only metadata transfer is skipped.
