# Runtime Binaries for Windows Installer Build

Place portable OCR runtime tools here before building the installer.

Required layout:

- `runtime/tesseract/` -> include `tesseract.exe` and its required data files (for example `tessdata`).
- `runtime/ghostscript/bin/` -> include Ghostscript executables and required DLLs.

These folders are bundled into the packaged app and added to PATH at runtime.

Do not commit proprietary or licensed binaries unless your distribution rights permit it.
