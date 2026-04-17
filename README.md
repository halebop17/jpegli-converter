# JPG Master - JPEGLI & JXL Converter

A macOS desktop app that converts TIFF and JPEG sources to high-quality JPEG or JPEG XL.

Built around Google's [jpegli](https://github.com/google/jpegli) encoder and JPEG XL tooling, the app supports TIFF→JPEG, TIFF→JXL, JPEG→JXL lossless transcode, and JXL→JPEG round-trip reconstruction. That JPEG→JXL lossless path is a special workflow not found in most converters, because it preserves JPEG data exactly while migrating it into the JXL container.

jpegli is currently one of the strongest JPEG encoders available for real-world photo export workflows because it improves quality-per-byte while remaining 100% baseline JPEG compatible. In practice, compared with older libjpeg-style encoders used in many photo apps and pipelines, jpegli typically delivers:

- smaller files at the same visual quality (often around 20-35%, and in some cases more)
- better detail and smoother tonal transitions at the same file size
- improved handling of high-precision source data before final JPEG quantization

Important precision note: final JPEG files are still standard 8-bit JPEG (for maximum compatibility), but jpegli can encode from higher-precision source buffers internally. In this app, 16-bit TIFF input is preserved through a 16-bit temporary PNG into jpegli, so the encoder starts from higher-fidelity source data instead of an early 8-bit truncation.

By default, metadata is preserved in the output — EXIF (camera make/model, exposure, GPS, etc.), IPTC, XMP, and ICC colour profile. You can also force metadata stripping with one checkbox.

## What this app does

- Converts TIFF sources to high-quality JPEG using Google's `jpegli` encoder.
- Supports JPEG XL export, including TIFF→JXL and JPEG→JXL lossless transcode.
- Supports JXL input when exporting JPEG, using round-trip reconstruct for JXL files.
- Automatically filters accepted source filenames based on the chosen export format.
- Offers selectable parallel conversion worker counts: 1, 2, 4, or 6.
- Preserves metadata by default, with an optional metadata strip mode.
- Supports single file, single folder, and recursive folder scans with folder-tree mirroring.

---

## Requirements

- macOS (Apple Silicon or Intel)
- Python 3.12+ with `tkinter` — install via `brew install python-tk`
- `tifffile` and `imagecodecs` (installed via `requirements.txt`)
- [ExifTool](https://exiftool.org) — `brew install exiftool` (optional, enables metadata transfer)
- `cjxl`/`djxl` for JXL workflows if you want JXL export or JXL→JPEG reconstruct; the app will auto-detect Homebrew installs if available.

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

**Double-click** `JPG Master - JPEGLI & JXL Converter.app` in the project folder.

Or from the terminal:

```bash
.venv/bin/python3 converter_app.py
```

---

## Interface

| Setting | Description |
|---|---|
| **Mode** | `Single File`, `Single Folder`, or `All Subfolders`. |
| **Input** | In `Single File` mode, choose one source file. In folder modes, choose a folder. |
| **Output folder** | In `Single Folder` mode, defaults to `/converted/` in the source folder. In `All Subfolders` mode, defaults to `/converted/` inside each source folder. |
| **Mirror folder structure to output folder** | Only for `All Subfolders` mode. Recreates the full input folder tree inside the selected output folder. |
| **Export format** | `JPEG` or `JXL`. The selected format controls accepted source types and output extension. |
| **JXL Encode Effort** | Only shown for `JXL` export. Range 1–9: lower is faster, higher gives better compression. |
| **Resize images** | Optional image sizing with modes: `Long Edge`, `Short Edge`, `Percentage`, `Width & Height`. |
| **Strip all metadata** | When checked, output files contain no EXIF/IPTC/XMP/ICC metadata. Default is unchecked (metadata preserved). |
| **Parallel conversions** | Choose 1, 2, 4, or 6 worker threads for batch processing. More workers speed up multi-file jobs on multi-core machines. |
| **Quality** | JPEG quality from 1 (smallest) to 100 (best). The recommended range is **75–95**. At 85 you get excellent results with ~30–50 % smaller files than standard JPEG at the same setting. |
| **Metadata status** | Shows ✓ if ExifTool is detected (EXIF · IPTC · XMP · ICC will be transferred) or ⚠ if it is missing. |

Click **Convert** to start. A progress bar tracks each file as it is processed.

---

## How it works

1. The app scans the selected source in `Single File`, `Single Folder`, or `All Subfolders` mode.
2. The accepted input file types change with the selected export format:
	- `JPEG` export accepts TIFF and JXL sources.
	- `JXL` export accepts TIFF and JPEG sources.
3. When the source is TIFF, the app reads it with `tifffile` and preserves the original source bit depth.
4. TIFF content is normalized to RGB/grayscale and optionally resized.
5. The image is written to a temporary PNG intermediary:
	- 16-bit TIFF source → 16-bit PNG intermediary
	- 8-bit TIFF source → 8-bit PNG intermediary
6. The selected encoder converts the PNG:
	- `cjpegli` encodes JPEG output.
	- `cjxl` encodes JXL output, with an effort slider for faster or smaller results.
7. For JPEG→JXL export, the app performs a lossless JPEG transcode when possible.
8. For JXL→JPEG export, the app uses round-trip reconstruction for accurate JPEG output.
9. If metadata transfer is enabled and ExifTool is available, EXIF/IPTC/XMP and ICC profiles are preserved.
10. The temporary PNG is deleted after conversion.

---

## Notes

- RGBA TIFFs are composited onto a white background before encoding (JPEG does not support transparency).
- The intermediary PNG is lossless. For 16-bit TIFFs, the intermediary is explicitly written as 16-bit PNG, so `cjpegli` receives high-precision input.
- Final output is still standard JPEG (8-bit format), but jpegli processes from the higher-precision source path when available.
- If ExifTool is not installed, conversion still works — only metadata transfer is skipped.
- Export format determines accepted source files: `JPEG` mode scans TIFF and JXL, while `JXL` mode scans TIFF and JPEG.
- The JXL effort slider controls encoding speed versus compression efficiency for JXL export.
- Parallel conversions use multiple worker threads. Choosing 2, 4, or 6 workers improves batch throughput on multi-core systems.
- In `All Subfolders` mode with mirror disabled, each source folder gets its own `converted/` subfolder.
