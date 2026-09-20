# Arch Linux Packaging & Installation for OCR PDF Layer Tool

This directory contains the packaging files to build and install **OCR PDF Layer Tool** (`ocrtool`) on Arch Linux and Arch-based distributions (Manjaro, EndeavourOS, Garuda, etc.).

---

## Why `pacman -S ocrmypdf` Fails
In Arch Linux:
- `python`, `tk`, `tesseract`, and `ghostscript` are in the **official Arch repositories**.
- **`ocrmypdf`** and **`python-customtkinter`** are in the **AUR (Arch User Repository)**.

Standard `pacman` cannot search or install AUR packages directly. To install them, use one of the methods below.

---

## Method 1: Automated Script (Recommended)

Run the included installer script, which automatically detects your AUR helper (`yay` or `paru`) or falls back to pip:

```bash
cd arch
chmod +x install_arch.sh
./install_arch.sh
```

---

## Method 2: Using an AUR Helper (`yay` or `paru`)

If you use `yay` or `paru`:

```bash
# 1. Install dependencies (handles both official and AUR packages)
yay -S --needed python tk tesseract ghostscript tesseract-data-eng ocrmypdf python-customtkinter

# 2. Build and install ocrtool
cd arch
makepkg -si
```

---

## Method 3: Without an AUR Helper (Manual pacman + pip)

If you prefer using vanilla `pacman`:

```bash
# 1. Install official system packages
sudo pacman -S --needed base-devel python tk tesseract ghostscript tesseract-data-eng python-pip

# 2. Install ocrmypdf and customtkinter via pip
sudo python -m pip install --break-system-packages ocrmypdf customtkinter darkdetect

# 3. Build and install ocrtool (bypassing AUR dependency check)
cd arch
makepkg -si --nodeps
```

---

## Launching

Once installed:
- **Application Menu**: Search for **OCR PDF Layer Tool**.
- **File Manager**: Right-click any PDF and select **Open With -> OCR PDF Layer Tool**.
- **Terminal**:
  ```bash
  ocrtool
  # or pass PDFs directly:
  ocrtool scan.pdf report.pdf
  ```
