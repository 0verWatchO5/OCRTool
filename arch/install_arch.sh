#!/usr/bin/env bash
set -e

echo "=== OCR PDF Layer Tool - Arch Linux Installer ==="

# 1. Check if running on an Arch-based system
if ! command -v pacman >/dev/null 2>&1; then
    echo "Error: pacman not found. This script is intended for Arch Linux and Arch-based systems." >&2
    exit 1
fi

# 2. Check for AUR helper (yay or paru)
AUR_HELPER=""
if command -v yay >/dev/null 2>&1; then
    AUR_HELPER="yay"
elif command -v paru >/dev/null 2>&1; then
    AUR_HELPER="paru"
fi

if [ -n "$AUR_HELPER" ]; then
    echo "Detected AUR helper: $AUR_HELPER"
    echo "Installing official and AUR dependencies (ocrmypdf, python-customtkinter, etc.)..."
    $AUR_HELPER -S --needed python tk tesseract ghostscript tesseract-data-eng ocrmypdf python-customtkinter
    
    echo "Building and installing ocrtool..."
    makepkg -si --noconfirm
else
    echo "No AUR helper (yay/paru) detected."
    echo "Installing official Arch packages via pacman..."
    sudo pacman -S --needed base-devel python tk tesseract ghostscript tesseract-data-eng python-pip git

    echo "Notice: 'ocrmypdf' and 'python-customtkinter' are located in the Arch User Repository (AUR)."
    echo "Installing Python packages (ocrmypdf, customtkinter) via pip..."
    sudo python -m pip install --break-system-packages ocrmypdf customtkinter darkdetect

    echo "Building and installing ocrtool package..."
    makepkg -si --nodeps --noconfirm
fi

echo ""
echo "=== Installation Complete! ==="
echo "You can launch the tool from your application menu or by running:"
echo "  ocrtool [file.pdf ...]"
