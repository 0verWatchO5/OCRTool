import importlib
import multiprocessing
import os
import pkgutil
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk

import customtkinter as ctk

import ocrmypdf
import ocrmypdf._plugin_manager
import ocrmypdf.pluginspec
from ocrmypdf.exceptions import MissingDependencyError

APP_VERSION = "1.1.6"


def patch_subprocess_hide_console() -> None:
    """Prevent command prompt console windows from flashing on Windows when subprocesses run."""
    if sys.platform != "win32":
        return

    _orig_popen_init = subprocess.Popen.__init__

    def _hidden_popen_init(self, *args, **kwargs):
        flags = kwargs.get("creationflags", 0)
        flags |= subprocess.CREATE_NO_WINDOW
        kwargs["creationflags"] = flags

        startupinfo = kwargs.get("startupinfo")
        if startupinfo is None:
            startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo

        _orig_popen_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _hidden_popen_init


def patch_ocrmypdf_plugin_manager() -> None:
    """Ensure ocrmypdf registers builtin plugins even when frozen in PyInstaller."""
    from ocrmypdf._plugin_manager import OcrmypdfPluginManager
    import ocrmypdf.pluginspec as pluginspec
    import ocrmypdf.builtin_plugins

    if getattr(OcrmypdfPluginManager, "_is_bundled_patch_applied", False):
        return

    def _setup_plugins(self):
        self._pm.add_hookspecs(pluginspec)

        # 1. Register builtins
        if self._builtins:
            registered_any = False
            try:
                for module_info in sorted(
                    pkgutil.iter_modules(ocrmypdf.builtin_plugins.__path__)
                ):
                    name = f"ocrmypdf.builtin_plugins.{module_info.name}"
                    module = importlib.import_module(name)
                    if not self._pm.is_registered(module):
                        self._pm.register(module)
                        registered_any = True
            except Exception:
                pass

            if not registered_any:
                builtin_module_names = [
                    "ocrmypdf.builtin_plugins.concurrency",
                    "ocrmypdf.builtin_plugins.default_filters",
                    "ocrmypdf.builtin_plugins.ghostscript",
                    "ocrmypdf.builtin_plugins.null_ocr",
                    "ocrmypdf.builtin_plugins.optimize",
                    "ocrmypdf.builtin_plugins.pypdfium",
                    "ocrmypdf.builtin_plugins.tesseract_ocr",
                ]
                for name in builtin_module_names:
                    try:
                        module = importlib.import_module(name)
                        if not self._pm.is_registered(module):
                            self._pm.register(module)
                    except Exception:
                        pass

        # 2. Register setuptools plugins
        try:
            self._pm.load_setuptools_entrypoints("ocrmypdf")
        except Exception:
            pass

        # 3. Register plugins specified on command line
        for plugin in self._plugins:
            try:
                if isinstance(plugin, Path) or (isinstance(plugin, str) and plugin.endswith(".py")):
                    plugin_path = Path(plugin)
                    module_name = plugin_path.stem
                    spec = importlib.util.spec_from_file_location(module_name, plugin_path)
                    if spec is None or spec.loader is None:
                        raise ImportError(f"Could not load plugin from {plugin_path}")
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                else:
                    module = importlib.import_module(plugin)
                if not self._pm.is_registered(module):
                    self._pm.register(module)
            except Exception:
                pass

    OcrmypdfPluginManager._setup_plugins = _setup_plugins
    OcrmypdfPluginManager._is_bundled_patch_applied = True


# Apply patches immediately on startup
patch_subprocess_hide_console()
patch_ocrmypdf_plugin_manager()


def format_file_size(num_bytes: int) -> str:
    """Format bytes into a human-readable size string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if num_bytes < 1024.0:
            return f"{num_bytes:.1f} {unit}" if unit != "B" else f"{num_bytes} B"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"


class OCRGuiApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        # Window Setup
        self.title(f"OCR PDF Layer Tool v{APP_VERSION}")
        self.geometry("1060x720")
        self.minsize(980, 640)

        # State Variables
        self.selected_files: list[Path] = []
        self.output_dir = tk.StringVar(value=str(Path.cwd()))
        self.language_code = tk.StringVar(value="eng")
        self.dpi_val = tk.StringVar(value="300")
        self.force_ocr = tk.BooleanVar(value=False)
        self.deskew = tk.BooleanVar(value=True)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.start_time: float = 0.0
        self.is_processing: bool = False

        self.tess_ready: bool = False
        self.gs_ready: bool = False

        # Build UI & runtime
        self._setup_theme()
        self._set_window_icon()
        self._build_ui()
        self._prepare_runtime_paths()
        self._poll_logs()

    def _find_asset(self, filename: str) -> Path | None:
        candidates = [
            Path(getattr(sys, "_MEIPASS", "")) / "assets" / filename,
            Path(__file__).resolve().parent / "assets" / filename,
            Path(getattr(sys, "_MEIPASS", "")) / filename,
            Path(__file__).resolve().parent / filename,
        ]
        for cand in candidates:
            if cand.exists():
                return cand
        return None

    def _set_window_icon(self) -> None:
        ico_file = self._find_asset("icon.ico")
        png_file = self._find_asset("icon.png")

        if ico_file and sys.platform == "win32":
            try:
                self.iconbitmap(str(ico_file))
                return
            except Exception:
                pass

        if png_file:
            try:
                img = Image.open(png_file)
                self._photo_icon = ImageTk.PhotoImage(img)
                self.iconphoto(False, self._photo_icon)
            except Exception:
                pass

    def _setup_theme(self) -> None:
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # 1. TOP HEADER BAR
        header_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray92", "#181d24"))
        header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 10))
        header_frame.grid_columnconfigure(1, weight=1)

        # Brand Title & Version
        brand_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        brand_frame.grid(row=0, column=0, padx=16, pady=12, sticky="w")

        # Brand Icon
        icon_path = self._find_asset("icon.png")
        if icon_path:
            try:
                pil_icon = Image.open(icon_path)
                self.brand_img = ctk.CTkImage(light_image=pil_icon, dark_image=pil_icon, size=(30, 30))
                icon_lbl = ctk.CTkLabel(brand_frame, text="", image=self.brand_img)
                icon_lbl.pack(side="left", padx=(0, 10))
            except Exception:
                pass

        title_lbl = ctk.CTkLabel(
            brand_frame,
            text="OCR PDF Layer Tool",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title_lbl.pack(side="left")

        ver_badge = ctk.CTkLabel(
            brand_frame,
            text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#3B82F6", "#2563EB"),
            text_color="white",
            corner_radius=6,
            padx=8,
            pady=2,
        )
        ver_badge.pack(side="left", padx=(10, 0))

        # Engine Status Indicator Chip
        self.engine_chip = ctk.CTkLabel(
            header_frame,
            text="Detecting OCR Engine...",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("gray80", "#2d3748"),
            corner_radius=12,
            padx=12,
            pady=4,
        )
        self.engine_chip.grid(row=0, column=1, padx=10, pady=12)

        # Theme Switcher
        theme_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        theme_frame.grid(row=0, column=2, padx=16, pady=12, sticky="e")

        theme_lbl = ctk.CTkLabel(theme_frame, text="Theme:", font=ctk.CTkFont(size=12))
        theme_lbl.pack(side="left", padx=(0, 6))

        self.theme_menu = ctk.CTkOptionMenu(
            theme_frame,
            values=["Dark", "Light", "System"],
            width=90,
            height=28,
            command=self._change_appearance_mode,
        )
        self.theme_menu.set("Dark")
        self.theme_menu.pack(side="left")

        # 2. MAIN SPLIT CONTENT AREA (Left: Queue & Output, Right: Settings & Actions)
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 10))
        content_frame.grid_columnconfigure(0, weight=6)
        content_frame.grid_columnconfigure(1, weight=5)
        content_frame.grid_rowconfigure(0, weight=1)

        # --- LEFT COLUMN: File Queue & Output Path ---
        left_col = ctk.CTkFrame(content_frame, fg_color="transparent")
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=0)
        left_col.grid_columnconfigure(0, weight=1)
        left_col.grid_rowconfigure(1, weight=1)

        # Queue Header Card
        queue_header = ctk.CTkFrame(left_col, corner_radius=10)
        queue_header.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 8))
        queue_header.grid_columnconfigure(0, weight=1)

        q_title_box = ctk.CTkFrame(queue_header, fg_color="transparent")
        q_title_box.grid(row=0, column=0, sticky="w", padx=12, pady=10)

        ctk.CTkLabel(
            q_title_box,
            text="Document Queue",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(side="left")

        self.queue_count_badge = ctk.CTkLabel(
            q_title_box,
            text="0 files",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("gray75", "#374151"),
            corner_radius=10,
            padx=8,
            pady=2,
        )
        self.queue_count_badge.pack(side="left", padx=(8, 0))

        # Queue Action Buttons
        btn_box = ctk.CTkFrame(queue_header, fg_color="transparent")
        btn_box.grid(row=0, column=1, sticky="e", padx=12, pady=10)

        self.btn_add = ctk.CTkButton(
            btn_box,
            text="+ Add PDFs",
            width=100,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.add_pdfs,
        )
        self.btn_add.pack(side="left", padx=(0, 6))

        self.btn_clear = ctk.CTkButton(
            btn_box,
            text="Clear All",
            width=80,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color=("gray70", "#374151"),
            hover_color=("gray60", "#4b5563"),
            command=self.clear_files,
        )
        self.btn_clear.pack(side="left")

        # Scrollable File List Card
        self.file_scroll_frame = ctk.CTkScrollableFrame(
            left_col,
            corner_radius=10,
            label_text="",
        )
        self.file_scroll_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=(0, 8))
        self.file_scroll_frame.grid_columnconfigure(0, weight=1)

        # Empty State Placeholder
        self.empty_label = ctk.CTkLabel(
            self.file_scroll_frame,
            text="📄 No PDF documents selected.\nClick '+ Add PDFs' to add files or launch with files pre-selected.",
            font=ctk.CTkFont(size=13),
            text_color=("gray50", "gray60"),
            justify="center",
        )
        self.empty_label.pack(pady=40, padx=20)

        # Output Folder Card
        out_card = ctk.CTkFrame(left_col, corner_radius=10)
        out_card.grid(row=2, column=0, sticky="ew", padx=0, pady=0)
        out_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            out_card,
            text="Destination:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, padx=(12, 6), pady=10, sticky="w")

        self.out_entry = ctk.CTkEntry(
            out_card,
            textvariable=self.output_dir,
            height=32,
            font=ctk.CTkFont(size=12),
        )
        self.out_entry.grid(row=0, column=1, sticky="ew", padx=6, pady=10)

        ctk.CTkButton(
            out_card,
            text="Browse",
            width=75,
            height=32,
            font=ctk.CTkFont(size=12),
            command=self.pick_output_folder,
        ).grid(row=0, column=2, padx=4, pady=10)

        ctk.CTkButton(
            out_card,
            text="Open",
            width=65,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color=("gray70", "#374151"),
            hover_color=("gray60", "#4b5563"),
            command=self.open_output_folder,
        ).grid(row=0, column=3, padx=(0, 12), pady=10)

        # --- RIGHT COLUMN: Settings & Execution Card ---
        right_col = ctk.CTkFrame(content_frame, corner_radius=10)
        right_col.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=0)
        right_col.grid_columnconfigure(0, weight=1)

        # Settings Card Title
        ctk.CTkLabel(
            right_col,
            text="OCR Configuration",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(14, 10))

        # 1. Language Selection
        lang_box = ctk.CTkFrame(right_col, fg_color="transparent")
        lang_box.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(
            lang_box,
            text="Recognition Language:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(anchor="w")

        self.lang_presets = {
            "English (eng)": "eng",
            "German (deu)": "deu",
            "French (fra)": "fra",
            "Spanish (spa)": "spa",
            "Italian (ita)": "ita",
            "Portuguese (por)": "por",
            "Chinese Simplified (chi_sim)": "chi_sim",
            "Japanese (jpn)": "jpn",
            "Custom Code": "custom",
        }

        self.lang_combo = ctk.CTkComboBox(
            lang_box,
            values=list(self.lang_presets.keys()),
            command=self._on_language_selected,
            height=32,
        )
        self.lang_combo.set("English (eng)")
        self.lang_combo.pack(fill="x", pady=(4, 0))

        self.custom_lang_entry = ctk.CTkEntry(
            lang_box,
            textvariable=self.language_code,
            placeholder_text="Enter Tesseract language code (e.g. eng, deu+eng)",
            height=30,
        )
        # Hidden initially; shown if Custom Code is selected

        # 2. DPI Setting
        dpi_box = ctk.CTkFrame(right_col, fg_color="transparent")
        dpi_box.pack(fill="x", padx=16, pady=(10, 6))

        ctk.CTkLabel(
            dpi_box,
            text="Raster DPI Resolution:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(anchor="w")

        self.dpi_segmented = ctk.CTkSegmentedButton(
            dpi_box,
            values=["150 DPI", "300 DPI", "400 DPI", "600 DPI"],
            command=self._on_dpi_selected,
            height=32,
        )
        self.dpi_segmented.set("300 DPI")
        self.dpi_segmented.pack(fill="x", pady=(4, 0))

        # 3. Processing Options Switches
        opts_box = ctk.CTkFrame(right_col, corner_radius=8, fg_color=("gray85", "#1e242d"))
        opts_box.pack(fill="x", padx=16, pady=(14, 10))

        self.sw_force = ctk.CTkSwitch(
            opts_box,
            text="Force OCR (Re-OCR pages with existing text)",
            variable=self.force_ocr,
            font=ctk.CTkFont(size=12),
        )
        self.sw_force.pack(anchor="w", padx=12, pady=(10, 6))

        self.sw_deskew = ctk.CTkSwitch(
            opts_box,
            text="Auto-Deskew (Straighten rotated/skewed pages)",
            variable=self.deskew,
            font=ctk.CTkFont(size=12),
        )
        self.sw_deskew.pack(anchor="w", padx=12, pady=(6, 10))

        # 4. Action & Progress Area
        action_box = ctk.CTkFrame(right_col, fg_color="transparent")
        action_box.pack(fill="both", expand=True, padx=16, pady=(10, 16))

        self.btn_run = ctk.CTkButton(
            action_box,
            text="Run OCR (0 files)",
            height=46,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=("#10B981", "#059669"),
            hover_color=("#059669", "#047857"),
            command=self.start_ocr,
        )
        self.btn_run.pack(fill="x", pady=(0, 10))

        self.progress_bar = ctk.CTkProgressBar(action_box, height=12)
        self.progress_bar.set(0.0)
        self.progress_bar.pack(fill="x", pady=(0, 6))

        info_status_row = ctk.CTkFrame(action_box, fg_color="transparent")
        info_status_row.pack(fill="x")

        self.status_lbl = ctk.CTkLabel(
            info_status_row,
            text="Ready to process",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray65"),
        )
        self.status_lbl.pack(side="left")

        self.duration_label = ctk.CTkLabel(
            info_status_row,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.duration_label.pack(side="right")

        # 3. BOTTOM LIVE LOG CARD
        log_card = ctk.CTkFrame(self, corner_radius=10)
        log_card.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))
        log_card.grid_columnconfigure(0, weight=1)

        log_head = ctk.CTkFrame(log_card, fg_color="transparent")
        log_head.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 4))
        log_head.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            log_head,
            text="Activity Console",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="left")

        ctk.CTkButton(
            log_head,
            text="Copy Logs",
            width=70,
            height=24,
            font=ctk.CTkFont(size=11),
            fg_color=("gray75", "#374151"),
            hover_color=("gray65", "#4b5563"),
            command=self.copy_logs,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            log_head,
            text="Clear",
            width=50,
            height=24,
            font=ctk.CTkFont(size=11),
            fg_color=("gray75", "#374151"),
            hover_color=("gray65", "#4b5563"),
            command=self.clear_logs,
        ).pack(side="right")

        self.log_textbox = ctk.CTkTextbox(
            log_card,
            height=120,
            font=ctk.CTkFont(family="Consolas" if sys.platform == "win32" else "Monospace", size=11),
            wrap="word",
            corner_radius=6,
        )
        self.log_textbox.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))
        self.log_textbox.configure(state="disabled")

    def _change_appearance_mode(self, mode: str) -> None:
        ctk.set_appearance_mode(mode)

    def _on_language_selected(self, choice: str) -> None:
        val = self.lang_presets.get(choice, "eng")
        if val == "custom":
            self.custom_lang_entry.pack(fill="x", pady=(6, 0))
            self.language_code.set("")
        else:
            self.custom_lang_entry.pack_forget()
            self.language_code.set(val)

    def _on_dpi_selected(self, choice: str) -> None:
        cleaned = choice.replace(" DPI", "").strip()
        self.dpi_val.set(cleaned)

    def _prepare_runtime_paths(self) -> None:
        """Find and configure bundled Tesseract and Ghostscript runtime paths."""
        candidate_roots: list[Path] = []

        # 1. PyInstaller temp directory (_MEIPASS)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidate_roots.append(Path(meipass) / "runtime")
            candidate_roots.append(Path(meipass))

        # 2. Executable parent directory and _internal
        exe_dir = Path(sys.executable).resolve().parent
        candidate_roots.extend(
            [
                exe_dir / "runtime",
                exe_dir / "_internal" / "runtime",
                exe_dir,
            ]
        )

        # 3. Script parent directory
        script_dir = Path(__file__).resolve().parent
        candidate_roots.extend(
            [
                script_dir / "runtime",
                script_dir,
            ]
        )

        # Locate runtime folder
        found_runtime_root: Path | None = None
        for root_cand in candidate_roots:
            if (root_cand / "tesseract").exists() or (root_cand / "tesseract.exe").exists():
                found_runtime_root = root_cand
                break

        paths_to_prepend: list[Path] = []
        tess_bin_dir: Path | None = None
        tessdata_dir: Path | None = None
        gs_bin_dir: Path | None = None
        gs_lib_dir: Path | None = None

        if found_runtime_root:
            # Check Tesseract folder
            cand_tess = found_runtime_root / "tesseract" if (found_runtime_root / "tesseract").exists() else found_runtime_root
            if (cand_tess / "tesseract.exe").exists():
                tess_bin_dir = cand_tess
                paths_to_prepend.append(cand_tess)
                if (cand_tess / "tessdata").exists():
                    tessdata_dir = cand_tess / "tessdata"

            # Check Ghostscript folder
            cand_gs_bin = found_runtime_root / "ghostscript" / "bin"
            if cand_gs_bin.exists():
                gs_bin_dir = cand_gs_bin
                paths_to_prepend.append(cand_gs_bin)

            cand_gs_lib = found_runtime_root / "ghostscript" / "lib"
            if cand_gs_lib.exists():
                gs_lib_dir = cand_gs_lib

        # Fallback to system locations if not bundled or partially present
        if not tess_bin_dir:
            system_tess = shutil.which("tesseract")
            if system_tess:
                tess_bin_dir = Path(system_tess).parent
                for cand_data in [Path("/usr/share/tessdata"), Path("/usr/share/tesseract-ocr/tessdata")]:
                    if cand_data.exists() and not tessdata_dir:
                        tessdata_dir = cand_data
                        break
            else:
                system_tess_candidates = [
                    Path(r"C:\Program Files\Tesseract-OCR"),
                    Path(r"C:\Program Files (x86)\Tesseract-OCR"),
                    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR",
                ]
                for c in system_tess_candidates:
                    if (c / "tesseract.exe").exists():
                        tess_bin_dir = c
                        paths_to_prepend.append(c)
                        if (c / "tessdata").exists() and not tessdata_dir:
                            tessdata_dir = c / "tessdata"
                        break

        if not gs_bin_dir:
            system_gs = shutil.which("gs")
            if system_gs:
                gs_bin_dir = Path(system_gs).parent
            else:
                for gs_root in [Path(r"C:\Program Files\gs"), Path(r"C:\Program Files (x86)\gs")]:
                    if gs_root.exists():
                        for sub in sorted(gs_root.glob("gs*"), reverse=True):
                            bin_d = sub / "bin"
                            if (bin_d / "gswin64c.exe").exists() or (bin_d / "gswin32c.exe").exists():
                                gs_bin_dir = bin_d
                                paths_to_prepend.append(bin_d)
                                if (sub / "lib").exists() and not gs_lib_dir:
                                    gs_lib_dir = sub / "lib"
                                break
                        if gs_bin_dir:
                            break

        # Apply environment variables
        if tessdata_dir and tessdata_dir.exists():
            os.environ["TESSDATA_PREFIX"] = str(tessdata_dir)

        if gs_lib_dir and gs_lib_dir.exists():
            os.environ["GS_LIB"] = str(gs_lib_dir)

        if paths_to_prepend:
            existing_path = os.environ.get("PATH", "")
            prepend = os.pathsep.join(str(p) for p in paths_to_prepend if p.exists())
            if prepend:
                os.environ["PATH"] = prepend + os.pathsep + existing_path

        self.tess_ready = bool(tess_bin_dir or shutil.which("tesseract"))
        self.gs_ready = bool(gs_bin_dir or shutil.which("gs") or shutil.which("gswin64c.exe") or shutil.which("gswin32c.exe"))

        # Update Engine Status Chip
        if self.tess_ready and self.gs_ready:
            self.engine_chip.configure(
                text="● Engine Ready (Tesseract + Ghostscript)",
                fg_color=("#D1FAE5", "#064E3B"),
                text_color=("#065F46", "#34D399"),
            )
        elif self.tess_ready:
            self.engine_chip.configure(
                text="▲ Ghostscript missing (Tesseract ready)",
                fg_color=("#FEF3C7", "#78350F"),
                text_color=("#92400E", "#FCD34D"),
            )
        else:
            self.engine_chip.configure(
                text="● Missing OCR Engine (Tesseract/GS)",
                fg_color=("#FEE2E2", "#7F1D1D"),
                text_color=("#991B1B", "#F87171"),
            )

        # Log details
        if tess_bin_dir:
            exe_name = "tesseract.exe" if (tess_bin_dir / "tesseract.exe").exists() else "tesseract"
            self.log_queue.put(f"[INFO] Tesseract engine configured: {tess_bin_dir / exe_name}")
        else:
            self.log_queue.put("[WARN] Tesseract OCR binary not found on runtime paths.")

        if gs_bin_dir:
            self.log_queue.put(f"[INFO] Ghostscript engine configured: {gs_bin_dir}")

    def _render_file_list(self) -> None:
        """Re-render the scrollable list of queued PDF files with remove buttons."""
        for widget in self.file_scroll_frame.winfo_children():
            widget.destroy()

        if not self.selected_files:
            self.empty_label = ctk.CTkLabel(
                self.file_scroll_frame,
                text="📄 No PDF documents selected.\nClick '+ Add PDFs' to add files or launch with files pre-selected.",
                font=ctk.CTkFont(size=13),
                text_color=("gray50", "gray60"),
                justify="center",
            )
            self.empty_label.pack(pady=40, padx=20)
            self.queue_count_badge.configure(text="0 files")
            self.btn_run.configure(text="Run OCR (0 files)", state="disabled")
            return

        count = len(self.selected_files)
        self.queue_count_badge.configure(text=f"{count} file{'s' if count != 1 else ''}")
        self.btn_run.configure(
            text=f"Run OCR ({count} file{'s' if count != 1 else ''})",
            state="normal" if not self.is_processing else "disabled",
        )

        for idx, file_path in enumerate(self.selected_files):
            item_card = ctk.CTkFrame(self.file_scroll_frame, corner_radius=6, fg_color=("gray85", "#212832"))
            item_card.pack(fill="x", pady=2, padx=2)
            item_card.grid_columnconfigure(1, weight=1)

            # PDF Badge
            pdf_badge = ctk.CTkLabel(
                item_card,
                text="PDF",
                font=ctk.CTkFont(size=9, weight="bold"),
                fg_color=("#EF4444", "#DC2626"),
                text_color="white",
                corner_radius=4,
                padx=5,
                pady=1,
            )
            pdf_badge.grid(row=0, column=0, padx=(8, 6), pady=6)

            # File name and size
            try:
                size_str = format_file_size(file_path.stat().st_size)
            except Exception:
                size_str = "Unknown"

            name_lbl = ctk.CTkLabel(
                item_card,
                text=file_path.name,
                font=ctk.CTkFont(size=12, weight="bold"),
                anchor="w",
            )
            name_lbl.grid(row=0, column=1, sticky="w", padx=2, pady=6)

            size_lbl = ctk.CTkLabel(
                item_card,
                text=size_str,
                font=ctk.CTkFont(size=11),
                text_color=("gray40", "gray60"),
            )
            size_lbl.grid(row=0, column=2, padx=8, pady=6)

            # Remove item button
            remove_btn = ctk.CTkButton(
                item_card,
                text="✕",
                width=24,
                height=24,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color="transparent",
                hover_color=("gray75", "#374151"),
                text_color=("gray40", "gray60"),
                command=lambda p=file_path: self.remove_file(p),
            )
            remove_btn.grid(row=0, column=3, padx=(0, 6), pady=6)

    def add_pdfs(self) -> None:
        files = filedialog.askopenfilenames(
            title="Select PDF files",
            filetypes=[("PDF files", "*.pdf")],
        )
        added_any = False
        for file_str in files:
            p = Path(file_str)
            if p not in self.selected_files:
                self.selected_files.append(p)
                added_any = True

        if added_any:
            if len(self.selected_files) == len(files):
                # Default output to first selected file's folder
                self.output_dir.set(str(self.selected_files[0].parent))
            self._render_file_list()

    def add_pdf_paths(self, paths: list[str]) -> None:
        for file_str in paths:
            p = Path(file_str)
            if p.suffix.lower() == ".pdf" and p.exists() and p not in self.selected_files:
                self.selected_files.append(p)

        if self.selected_files:
            self.output_dir.set(str(self.selected_files[0].parent))

        self._render_file_list()

    def remove_file(self, file_path: Path) -> None:
        if file_path in self.selected_files:
            self.selected_files.remove(file_path)
            self._render_file_list()

    def clear_files(self) -> None:
        self.selected_files.clear()
        self.duration_label.configure(text="")
        self.status_lbl.configure(text="Ready to process")
        self.progress_bar.set(0.0)
        self._render_file_list()

    def pick_output_folder(self) -> None:
        folder = filedialog.askdirectory(
            title="Select Output Folder",
            initialdir=self.output_dir.get() or str(Path.cwd()),
        )
        if folder:
            self.output_dir.set(folder)

    def open_output_folder(self) -> None:
        target = Path(self.output_dir.get().strip())
        if not target.exists():
            messagebox.showwarning("Folder Not Found", f"The directory does not exist:\n{target}")
            return

        try:
            if sys.platform == "win32":
                os.startfile(str(target))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open directory: {e}")

    def clear_logs(self) -> None:
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")

    def copy_logs(self) -> None:
        content = self.log_textbox.get("1.0", "end").strip()
        if content:
            self.clipboard_clear()
            self.clipboard_append(content)
            messagebox.showinfo("Copied", "Console logs copied to clipboard!")

    def _poll_logs(self) -> None:
        while True:
            try:
                line = self.log_queue.get_nowait()
            except queue.Empty:
                break
            else:
                self.log_textbox.configure(state="normal")
                self.log_textbox.insert("end", line + "\n")
                self.log_textbox.see("end")
                self.log_textbox.configure(state="disabled")

        self.after(100, self._poll_logs)

    def _update_duration_timer(self) -> None:
        if self.is_processing:
            elapsed = max(0.0, time.time() - self.start_time)
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            self.duration_label.configure(text=f"⏱ {mins:02d}:{secs:02d}")
            self.after(200, self._update_duration_timer)

    def start_ocr(self) -> None:
        if self.is_processing or (self.worker_thread and self.worker_thread.is_alive()):
            messagebox.showinfo("OCR Running", "An OCR batch operation is already in progress.")
            return

        if not self.selected_files:
            messagebox.showwarning("No Files", "Please add at least one PDF document to process.")
            return

        out_dir = Path(self.output_dir.get().strip())
        if not out_dir or not out_dir.exists() or not out_dir.is_dir():
            messagebox.showwarning("Invalid Output Folder", "The selected output folder does not exist.")
            return

        dpi_str = self.dpi_val.get().strip()
        if not dpi_str.isdigit() or int(dpi_str) <= 0:
            messagebox.showwarning("Invalid DPI", "DPI resolution must be a positive integer.")
            return

        lang = self.language_code.get().strip()
        if not lang:
            messagebox.showwarning("Invalid Language", "Please select or enter an OCR language code.")
            return

        self.is_processing = True
        self.start_time = time.time()
        self.btn_run.configure(state="disabled", text="Processing...")
        self.btn_add.configure(state="disabled")
        self.btn_clear.configure(state="disabled")
        self.progress_bar.set(0.0)
        self.status_lbl.configure(text=f"Processing 1 of {len(self.selected_files)}...")

        self.worker_thread = threading.Thread(
            target=self._run_ocr_batch,
            args=(
                self.selected_files.copy(),
                out_dir,
                lang,
                int(dpi_str),
                self.force_ocr.get(),
                self.deskew.get(),
            ),
            daemon=True,
        )
        self.worker_thread.start()
        self._update_duration_timer()

    def _run_ocr_batch(
        self,
        files: list[Path],
        out_dir: Path,
        lang: str,
        dpi: int,
        force_ocr: bool,
        deskew: bool,
    ) -> None:
        total_files = len(files)
        batch_start = time.time()
        self.log_queue.put(f"[START] Batch processing started ({total_files} file{'s' if total_files != 1 else ''}).")
        successes = 0

        for idx, input_pdf in enumerate(files, start=1):
            def update_progress(current_idx=idx, total=total_files, name=input_pdf.name):
                fraction = (current_idx - 1) / total
                self.progress_bar.set(fraction)
                self.status_lbl.configure(text=f"[{current_idx}/{total}] Processing: {name}")

            self.after(0, update_progress)

            output_pdf = out_dir / f"{input_pdf.stem}_ocr.pdf"
            self.log_queue.put(f"[INFO] [{idx}/{total_files}] Processing: {input_pdf.name}")
            t_file_start = time.time()

            try:
                ocrmypdf.ocr(
                    str(input_pdf),
                    str(output_pdf),
                    language=[lang],
                    ocr_engine="tesseract",
                    image_dpi=dpi,
                    optimize=1,
                    jobs=max(1, min(4, os.cpu_count() or 1)),
                    use_threads=True,
                    output_type="pdf",
                    force_ocr=force_ocr,
                    deskew=deskew,
                    progress_bar=False,
                )
            except MissingDependencyError as exc:
                self.log_queue.put("[ERROR] Missing required OCR runtime dependency.")
                self.log_queue.put(f"[ERROR] {exc}")
                self.log_queue.put(
                    "[HINT] On Windows, run './collect_runtime_windows.ps1'. On Arch Linux, install 'tesseract' and 'ghostscript'."
                )
                self._finish_batch(successes, total_files)
                return
            except Exception as exc:
                file_dur = time.time() - t_file_start
                self.log_queue.put(f"[FAIL] {input_pdf.name} (failed after {file_dur:.1f}s)")
                self.log_queue.put(f"[ERROR] {exc}")
                continue

            file_dur = time.time() - t_file_start
            successes += 1
            self.log_queue.put(f"[OK] Completed {output_pdf.name} in {file_dur:.1f}s")

        total_dur = time.time() - batch_start
        self.log_queue.put(f"[DONE] Batch complete: {successes}/{total_files} succeeded in {total_dur:.1f}s.")
        self._finish_batch(successes, total_files)

    def _finish_batch(self, successes: int, total: int) -> None:
        def done():
            self.is_processing = False
            self.progress_bar.set(1.0 if successes == total else (successes / max(1, total)))
            self.btn_run.configure(
                state="normal",
                text=f"Run OCR ({len(self.selected_files)} file{'s' if len(self.selected_files) != 1 else ''})",
            )
            self.btn_add.configure(state="normal")
            self.btn_clear.configure(state="normal")
            self.status_lbl.configure(text=f"Finished: {successes}/{total} succeeded")

            if self.start_time > 0:
                total_sec = time.time() - self.start_time
                mins = int(total_sec // 60)
                secs = int(total_sec % 60)
                time_str = f"{mins}m {secs:02d}s" if mins > 0 else f"{total_sec:.1f}s"
                self.duration_label.configure(text=f"⏱ Total: {time_str}")

        self.after(0, done)


def main() -> None:
    multiprocessing.freeze_support()
    app = OCRGuiApp()
    if len(sys.argv) > 1:
        app.add_pdf_paths(sys.argv[1:])
    app.mainloop()


if __name__ == "__main__":
    main()
