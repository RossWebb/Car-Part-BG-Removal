# Part-Out Cutter — Catalogue Edition

A Windows desktop app for batch AI background removal, built for preparing product images for catalogues and part listings.

Powered by [rembg](https://github.com/danielgatis/rembg) and [onnxruntime](https://onnxruntime.ai/).

---

## Features

- Batch process entire folders of images in one go
- Multiple AI models selectable at runtime
- Adjustable background removal settings with named presets
- Alpha matting controls for fine edge detail
- Optional solid background fill (with colour picker)
- Saves output as PNG with transparency preserved
- Configurable output folder

### Presets

| Preset | Best for |
|---|---|
| Standard | General product shots |
| Conservative (reflective parts) | Parts with mirrors, chrome, or shiny surfaces |
| Clean edges | Hair, fur, fine detail |
| White background | Catalogue / e-commerce use |

---

## Running from source

### Requirements

- Windows (64-bit)
- Python 3.13 64-bit — **must be 64-bit**, rembg and onnxruntime require it
- Dependencies:

```
pip install rembg pillow onnxruntime tqdm pooch pymatting scikit-image scipy
```

### Run

```
python app.py
```

On first run the app will download the default AI model weights (~170 MB) and cache them in `%USERPROFILE%\.u2net\`. An internet connection is required for this one-time download only.

---

## Building a standalone executable

The included `build.bat` script packages the app into a self-contained folder using PyInstaller — no Python installation required on the target machine.

### Prerequisites

64-bit Python 3.13 with all dependencies installed (see above). The script is hardcoded to:

```
C:\Users\rnlwe\AppData\Local\Programs\Python\Python313\python.exe
```

If your Python path differs, update the `PYTHON=` line near the top of `build.bat`.

### Build

```
build.bat
```

Output is written to `dist\PartOutCutter\`. Zip that folder and distribute it.

### Distributing to a colleague

1. Zip `dist\PartOutCutter\`
2. Send the zip — no Python or other tools needed on their machine
3. On first launch the app downloads model weights (~170 MB) — an internet connection is required that one time only

---

## Models

| Model | Best for |
|---|---|
| `isnet-general-use` | General objects and products (default) |
| `u2net` | Good all-rounder, slightly faster |
| `u2net_human_seg` | People and clothing |
| `silueta` | Fast, lower memory usage |
| `isnet-anime` | Illustrated or anime-style art |

Model weights are downloaded on demand and cached in `%USERPROFILE%\.u2net\`.

---

## Settings reference

| Setting | Description |
|---|---|
| Alpha matting | Improves edge quality, especially on fine detail. Slower. |
| Foreground threshold | Lower = more ambiguous pixels kept (helps with reflective surfaces) |
| Background threshold | Higher = more conservative background removal |
| Erode size | Shrinks the uncertain edge region |
| Post-process mask | Applies a soft blur to smooth hard edges |
| Background fill | Replace transparency with a solid colour |

---

## Notes

- Output files are saved as `originalname_nobg.png` alongside the source images, or in a chosen output folder
- The app window may take several seconds to appear on first launch — PyInstaller is unpacking the bundled runtime
- If the app fails to start, check `error.log` in the `PartOutCutter` folder for a full traceback
