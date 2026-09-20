# OCR PDF Layer Tool

A lightweight, standalone Windows desktop application for adding a searchable OCR text layer to PDF documents.

Built on top of [OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF), this tool bundles all necessary runtime dependencies (Tesseract OCR & Ghostscript) into an intuitive Windows installer. End users do not need Python, terminal environments, or command-line configuration.

---

## Features

- **Modern Professional GUI**: Sleek CustomTkinter interface with native Dark, Light, and System theme switching.
- **Interactive Document Queue**: Scrollable file list displaying file names, formatted file sizes, and individual remove buttons.
- **Engine Health Indicator**: Real-time status chip showing detection of Tesseract OCR and Ghostscript dependencies.
- **Batch Processing**: Select one or multiple PDF documents simultaneously.
- **Advanced Processing Options**:
  - **Force OCR**: Re-rasterize and OCR documents that already contain text.
  - **Auto-Deskew**: Automatically detect and straighten rotated/crooked scanned pages.
- **OCR Engine Controls**: Preset language selector (`English`, `German`, `French`, `Spanish`, `Italian`, `Chinese Simplified`, `Japanese`, or custom codes) and DPI presets (150, 300, 400, 600).
- **Explorer & Desktop Integration**: Right-click context menu (**"OCR this PDF"**) and PDF file associations on Windows and Linux.
- **Live Activity Console**: Timestamped console with progress tracking, ETA timer, and one-click "Copy Logs" functionality.

---

## Installation & End-User Experience

1. Download the latest installer: `OCRTool-Setup-<version>.exe`.
2. Run the installer wizard.
3. *(Optional)* Select Explorer integration options:
   - **OCR this PDF**: Adds a right-click shell action to PDF files.
   - **Associate .pdf files**: Associates PDF files with OCR PDF Layer Tool.
4. Launch **OCR PDF Layer Tool** from the Start Menu or Desktop shortcut.
5. Select your PDF files and click **Run OCR**.

---

## Developer Guide

### Prerequisites

- **Windows 10 / 11** (64-bit)
- **Python 3.10+** (accessible via `python` or the `py` launcher)
- **PowerShell 5.1+** or PowerShell 7+
- **Inno Setup 6** (can be installed via `winget install JRSoftware.InnoSetup`)
- **Git**

---

### Local Development Run

To run the application locally from source:

```powershell
# 1. Create and activate a virtual environment
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements-build.txt

# 3. Ensure Tesseract and Ghostscript are on PATH, then run
python app.py
```

---

### Building the Windows Installer

The build pipeline automates runtime dependency collection, PyInstaller packaging, code signing, and Inno Setup installer compilation.

#### 1. Collect Runtime Binaries

Run the automated dependency collector once:

```powershell
./collect_runtime_windows.ps1 -InstallIfMissing
```

This script:
- Automatically installs Tesseract OCR and Ghostscript via `winget` if missing.
- Extracts and stages portable binaries into `runtime/tesseract/` and `runtime/ghostscript/`.

> [!NOTE]
> Staged runtime binaries in `runtime/` are ignored by Git to avoid checking heavy vendor binaries into source control.

#### 2. Build and Package

Compile the standalone executable and Inno Setup installer:

```powershell
./build_windows.ps1 -Version 1.1.4
```

The compiled installer will be located in:
```
installer/output/OCRTool-Setup-1.1.4.exe
```

#### 3. Code Signing (Optional)

`build_windows.ps1` automatically invokes `sign_windows.ps1`:
- **Local Dev / Testing**: Automatically generates a local self-signed code signing certificate if none exists.
- **Production / CI Release**: Pass a trusted PFX certificate and password:
  ```powershell
  ./build_windows.ps1 -Version 1.1.4 -PfxPath "C:\path\to\cert.pfx" -PfxPassword "secret"
  ```

---

### Packaging for Arch Linux

The [`arch/`](arch/) directory provides a native `PKGBUILD`, launcher script, SVG icon, and desktop entry for Arch Linux and Arch-based distributions (Manjaro, EndeavourOS, etc.).

#### 1. Install Build & Runtime Dependencies

```bash
sudo pacman -S --needed base-devel python tk ocrmypdf tesseract ghostscript tesseract-data-eng
```

#### 2. Build & Install via `makepkg`

```bash
cd arch
makepkg -si
```

This installs:
- Executable binary: `/usr/bin/ocrtool`
- Desktop integration: `/usr/share/applications/ocrtool.desktop` (with PDF right-click support)
- Vector icon: `/usr/share/icons/hicolor/scalable/apps/ocrtool.svg`

#### 3. AUR Maintenance

To generate or update `.SRCINFO` for AUR submission:
```bash
cd arch
makepkg --printsrcinfo > .SRCINFO
```

---

## Contributing & Development Guidelines

1. **Do not commit confidential or personal PDFs**:
   - `*.pdf` files are ignored in `.gitignore` by default.
   - If adding test documents, place sanitized, public-domain sample files under a dedicated `samples/` folder.
2. **Do not commit private certificates or keys**:
   - Ensure all `.pfx`, `.p12`, `.cer`, and `.key` files remain untracked.
3. **Line Endings & Formatting**:
   - Keep files using standard UTF-8 encoding.

---

## Third-Party Licenses & Disclaimers

This project integrates and redistributes several open-source libraries and utilities:

- **[OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF)**: Licensed under the [Mozilla Public License 2.0 (MPL-2.0)](https://www.mozilla.org/MPL/2.0/).
- **[Tesseract OCR](https://github.com/tesseract-ocr/tesseract)**: Licensed under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).
- **[Ghostscript](https://ghostscript.com/)**: Licensed under the [GNU Affero General Public License (AGPL v3)](https://www.gnu.org/licenses/agpl-3.0.html) / Artifex Commercial License.
- **[Inno Setup](https://jrsoftware.org/isinfo.php)**: Licensed under the Inno Setup License.

Please ensure compliance with upstream licenses (especially AGPL-3.0 regarding Ghostscript redistribution) when distributing compiled installer bundles.
