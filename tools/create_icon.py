"""
Generate a crystal-clear, modern, high-contrast app icon for OCR PDF Layer Tool.
Renders at 2048x2048 supersampled resolution and downscales cleanly to all icon mipmaps
(16, 24, 32, 48, 64, 128, 256, 512) with edge sharpening for small taskbar sizes.
"""
import os
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

def create_super_icon():
    size = 2048
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Base Squircle Shape (Fluent-style rounded rectangle)
    # Safe area margin: 120px on each side
    pad = 140
    rect = [pad, pad, size - pad, size - pad]
    radius = 380

    # Gradient background for squircle (Vibrant Royal Navy to Electric Indigo-Cyan)
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(rect, radius=radius, fill=255)

    # Create rich diagonal gradient: Rich Sapphire (#1e3a8a) -> Vivid Royal Blue (#2563eb) -> Electric Cyan (#0284c7)
    grad = Image.new("RGBA", (size, size), 0)
    grad_draw = ImageDraw.Draw(grad)
    c1 = (28, 58, 138)      # Rich deep sapphire
    c2 = (37, 99, 235)      # Vivid royal blue
    c3 = (2, 132, 199)      # Bright electric cyan
    for y in range(size):
        ratio = y / size
        if ratio < 0.5:
            r = int(c1[0] + (c2[0] - c1[0]) * (ratio / 0.5))
            g = int(c1[1] + (c2[1] - c1[1]) * (ratio / 0.5))
            b = int(c1[2] + (c2[2] - c1[2]) * (ratio / 0.5))
        else:
            r = int(c2[0] + (c3[0] - c2[0]) * ((ratio - 0.5) / 0.5))
            g = int(c2[1] + (c3[1] - c2[1]) * ((ratio - 0.5) / 0.5))
            b = int(c2[2] + (c3[2] - c2[2]) * ((ratio - 0.5) / 0.5))
        grad_draw.line([(0, y), (size, y)], fill=(r, g, b, 255))

    # Apply mask
    bg = Image.composite(grad, Image.new("RGBA", (size, size), (0, 0, 0, 0)), mask)

    # Subtle inner border for contrast against dark taskbars (Vivid Cyan border)
    border_mask = Image.new("L", (size, size), 0)
    bdraw = ImageDraw.Draw(border_mask)
    bdraw.rounded_rectangle(rect, radius=radius, outline=255, width=28)
    border_layer = Image.new("RGBA", (size, size), (56, 189, 248, 230)) # Cyan-400
    bg = Image.composite(border_layer, bg, border_mask)

    # 2. Document Page in Center
    # Dimensions: width=980, height=1280
    doc_w, doc_h = 980, 1280
    doc_x0 = (size - doc_w) // 2
    doc_y0 = (size - doc_h) // 2 + 20
    doc_x1 = doc_x0 + doc_w
    doc_y1 = doc_y0 + doc_h
    fold_size = 280

    # Draw document drop shadow
    shadow = Image.new("RGBA", (size, size), 0)
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle(
        [doc_x0 - 20, doc_y0 + 20, doc_x1 + 20, doc_y1 + 40],
        radius=40,
        fill=(0, 0, 0, 180)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(40))
    bg = Image.alpha_composite(bg, shadow)

    # Document body with folded corner (polygon)
    doc_pts = [
        (doc_x0 + 40, doc_y0),                   # top left
        (doc_x1 - fold_size, doc_y0),           # top fold start
        (doc_x1, doc_y0 + fold_size),           # right fold end
        (doc_x1, doc_y1 - 40),                   # bottom right
        (doc_x1 - 40, doc_y1),                   # bottom right curve
        (doc_x0 + 40, doc_y1),                   # bottom left curve
        (doc_x0, doc_y0 + 40),                   # bottom left
        (doc_x0, doc_y0 + 40),                   # top left curve
    ]

    doc_layer = Image.new("RGBA", (size, size), 0)
    ddraw = ImageDraw.Draw(doc_layer)
    # Bright crisp pure white paper for ultra contrast
    ddraw.polygon(doc_pts, fill=(255, 255, 255, 255))

    # Folded corner polygon
    fold_pts = [
        (doc_x1 - fold_size, doc_y0),
        (doc_x1 - fold_size, doc_y0 + fold_size),
        (doc_x1, doc_y0 + fold_size),
    ]
    # Subtle fold shadow
    fold_shadow_pts = [
        (doc_x1 - fold_size - 10, doc_y0 - 5),
        (doc_x1 - fold_size - 10, doc_y0 + fold_size + 15),
        (doc_x1 + 5, doc_y0 + fold_size + 15),
    ]
    ddraw.polygon(fold_shadow_pts, fill=(148, 163, 184, 200))
    # Folded flap
    ddraw.polygon(fold_pts, fill=(203, 213, 225, 255))
    # Highlight on fold crease
    ddraw.line([(doc_x1 - fold_size, doc_y0), (doc_x1, doc_y0 + fold_size)], fill=(100, 116, 139, 220), width=8)

    # Combine doc layer
    bg = Image.alpha_composite(bg, doc_layer)

    # 3. Document Content: Text lines (Representing scanned text layer)
    lines_draw = ImageDraw.Draw(bg)
    line_x0 = doc_x0 + 130
    line_x1 = doc_x1 - 130
    
    # Top header line (Navy)
    lines_draw.rounded_rectangle([line_x0, doc_y0 + 360, line_x0 + 380, doc_y0 + 410], radius=14, fill=(30, 41, 59, 240))
    
    # Text lines
    line_y = doc_y0 + 460
    line_spacing = 75
    for i in range(4):
        w_factor = [0.88, 0.95, 0.72, 0.85][i]
        curr_x1 = int(line_x0 + (line_x1 - line_x0) * w_factor)
        lines_draw.rounded_rectangle([line_x0, line_y, curr_x1, line_y + 36], radius=12, fill=(100, 116, 139, 200))
        line_y += line_spacing

    # 4. Bold Optical Character Recognition (OCR) Focus Emblem
    # Scanner box in bottom half of doc
    box_w = 740
    box_h = 340
    box_x0 = (size - box_w) // 2
    box_y0 = doc_y0 + 800
    box_x1 = box_x0 + box_w
    box_y1 = box_y0 + box_h
    corner_len = 110
    brk_thickness = 40

    # Glowing Cyan Scanner Brackets
    # Top-Left Bracket
    lines_draw.line([(box_x0, box_y0), (box_x0 + corner_len, box_y0)], fill=(6, 182, 212, 255), width=brk_thickness)
    lines_draw.line([(box_x0, box_y0), (box_x0, box_y0 + corner_len)], fill=(6, 182, 212, 255), width=brk_thickness)
    # Top-Right Bracket
    lines_draw.line([(box_x1, box_y0), (box_x1 - corner_len, box_y0)], fill=(6, 182, 212, 255), width=brk_thickness)
    lines_draw.line([(box_x1, box_y0), (box_x1, box_y0 + corner_len)], fill=(6, 182, 212, 255), width=brk_thickness)
    # Bottom-Left Bracket
    lines_draw.line([(box_x0, box_y1), (box_x0 + corner_len, box_y1)], fill=(6, 182, 212, 255), width=brk_thickness)
    lines_draw.line([(box_x0, box_y1), (box_x0, box_y1 - corner_len)], fill=(6, 182, 212, 255), width=brk_thickness)
    # Bottom-Right Bracket
    lines_draw.line([(box_x1, box_y1), (box_x1 - corner_len, box_y1)], fill=(6, 182, 212, 255), width=brk_thickness)
    lines_draw.line([(box_x1, box_y1), (box_x1, box_y1 - corner_len)], fill=(6, 182, 212, 255), width=brk_thickness)

    # 5. Bold "OCR" Text inside the scan brackets
    ocr_font = None
    for font_name in ["arialbd.ttf", "segoeuib.ttf", "calibrib.ttf", "arial.ttf"]:
        try:
            font_path = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", font_name)
            if os.path.exists(font_path):
                ocr_font = ImageFont.truetype(font_path, 210)
                break
        except Exception:
            pass

    if ocr_font:
        bbox = lines_draw.textbbox((0, 0), "OCR", font=ocr_font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = (size - tw) // 2
        ty = box_y0 + (box_h - th) // 2 - 25
        # Crisp deep navy blue for maximum contrast
        lines_draw.text((tx, ty), "OCR", font=ocr_font, fill=(15, 23, 42, 255))
    else:
        lines_draw.rounded_rectangle([box_x0 + 80, box_y0 + 130, box_x1 - 80, box_y0 + 200], radius=20, fill=(15, 23, 42, 255))

    # 6. Vibrant Laser Scan Beam Across the Document
    beam_y = box_y0 + 30
    glow = Image.new("RGBA", (size, size), 0)
    gdraw = ImageDraw.Draw(glow)
    # Intense cyan glow
    gdraw.line([(doc_x0 - 40, beam_y), (doc_x1 + 40, beam_y)], fill=(6, 182, 212, 160), width=70)
    glow = glow.filter(ImageFilter.GaussianBlur(26))
    bg = Image.alpha_composite(bg, glow)

    # Core bright white-cyan laser line
    ldraw = ImageDraw.Draw(bg)
    ldraw.line([(doc_x0 - 30, beam_y), (doc_x1 + 30, beam_y)], fill=(34, 211, 238, 255), width=22)
    ldraw.line([(doc_x0 - 10, beam_y), (doc_x1 + 10, beam_y)], fill=(255, 255, 255, 250), width=10)

    # Glow nodes at laser ends
    ldraw.ellipse([doc_x0 - 50, beam_y - 20, doc_x0 - 10, beam_y + 20], fill=(34, 211, 238, 255))
    ldraw.ellipse([doc_x1 + 10, beam_y - 20, doc_x1 + 50, beam_y + 20], fill=(34, 211, 238, 255))

    return bg

if __name__ == "__main__":
    out_dir = Path("assets")
    out_dir.mkdir(exist_ok=True)
    
    print("Generating 2048x2048 master icon...")
    master = create_super_icon()
    
    # Save 512x512 PNG
    png512 = master.resize((512, 512), Image.Resampling.LANCZOS)
    png512.save(out_dir / "icon.png", format="PNG", optimize=True)
    print("Saved assets/icon.png (512x512)")
    
    # Also save for arch linux
    arch_png = Path("arch") / "ocrtool.png"
    if arch_png.parent.exists():
        png512.save(arch_png, format="PNG", optimize=True)
        print("Saved arch/ocrtool.png")
        
    sizes = [16, 24, 32, 48, 64, 128, 256]
    mipmaps = []
    for s in sizes:
        res = master.resize((s, s), Image.Resampling.LANCZOS)
        if s <= 24:
            # High sharpening for 16 & 24 taskbar size
            res = res.filter(ImageFilter.UnsharpMask(radius=1.2, percent=180, threshold=2))
            enhancer = ImageEnhance.Contrast(res)
            res = enhancer.enhance(1.20)
        elif s <= 48:
            res = res.filter(ImageFilter.UnsharpMask(radius=1.0, percent=130, threshold=2))
            enhancer = ImageEnhance.Contrast(res)
            res = enhancer.enhance(1.10)
        mipmaps.append(res)
        
    ico_path = out_dir / "icon.ico"
    master256 = mipmaps[-1]
    master256.save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in sizes]
    )
    print(f"Saved assets/icon.ico with sizes: {sizes}")
