# Arch Linux Packaging for OCR PDF Layer Tool

This directory contains the packaging files to build and install **OCR PDF Layer Tool** (`ocrtool`) natively on Arch Linux and Arch-based distributions (Manjaro, EndeavourOS, Garuda, etc.).

---

## Files

- **`PKGBUILD`**: The standard Arch build definition file for `makepkg`.
- **`ocrtool.desktop`**: Freedesktop application entry for desktop menus and file managers (`application/pdf` handler).
- **`ocrtool.sh`**: Launch wrapper installed to `/usr/bin/ocrtool`.
- **`ocrtool.svg`**: Application icon installed to `/usr/share/icons/hicolor/scalable/apps/`.

---

## Prerequisites (Arch Linux)

Install the required base build tools and upstream dependencies from official Arch repositories:

```bash
sudo pacman -S --needed base-devel python tk ocrmypdf tesseract ghostscript tesseract-data-eng
```

> **Note**: `tk` provides the Python `tkinter` GUI runtime, and `tesseract-data-eng` provides default English OCR training data. For other languages, install `tesseract-data-<lang>` (e.g. `tesseract-data-deu`, `tesseract-data-fra`).

---

## Building and Installing Locally

From the root of this repository:

```bash
cd arch
makepkg -si
```

This will:
1. Validate package dependencies.
2. Package the application, desktop entry, launcher, and icon.
3. Install the resulting `.pkg.tar.zst` package via `pacman`.

---

## Launching

Once installed, you can launch OCRTool:
- **Application Menu**: Search for **OCR PDF Layer Tool**.
- **File Manager**: Right-click any `.pdf` file and choose **Open With -> OCR PDF Layer Tool**.
- **Terminal**: Run `ocrtool` or pass one or more files directly:
  ```bash
  ocrtool document.pdf scan2.pdf
  ```

---

## Generating `.SRCINFO` for AUR

If maintaining an AUR package:

```bash
cd arch
makepkg --printsrcinfo > .SRCINFO
```
