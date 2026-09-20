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
from tkinter import filedialog, messagebox, ttk

import ocrmypdf
import ocrmypdf._plugin_manager
import ocrmypdf.pluginspec
from ocrmypdf.exceptions import MissingDependencyError

APP_VERSION = "1.1.4"


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

            # Fallback list of known builtin plugins if pkgutil.iter_modules yields nothing (e.g. in PyInstaller frozen archive)
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


class OCRGuiApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"Searchable PDF OCR Tool v{APP_VERSION}")
        self.root.geometry("920x620")
        self.root.minsize(860, 560)

        self.selected_files: list[Path] = []
        self.output_dir = tk.StringVar(value=str(Path.cwd()))
        self.language = tk.StringVar(value="eng")
        self.dpi = tk.StringVar(value="300")
        self.force_ocr = tk.BooleanVar(value=False)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.start_time: float = 0.0
        self.is_processing: bool = False

        self._build_ui()
        self._poll_logs()
        self._prepare_runtime_paths()

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        file_row = ttk.Frame(main)
        file_row.pack(fill=tk.X, pady=(0, 8))

        ttk.Button(file_row, text="Add PDFs", command=self.add_pdfs).pack(side=tk.LEFT)
        ttk.Button(file_row, text="Clear", command=self.clear_files).pack(side=tk.LEFT, padx=(8, 0))

        self.file_count_label = ttk.Label(file_row, text="0 file(s) selected")
        self.file_count_label.pack(side=tk.RIGHT)

        self.file_list = tk.Listbox(main, height=10)
        self.file_list.pack(fill=tk.X, pady=(0, 10))

        output_frame = ttk.LabelFrame(main, text="Output")
        output_frame.pack(fill=tk.X, pady=(0, 10))

        output_row = ttk.Frame(output_frame, padding=8)
        output_row.pack(fill=tk.X)

        ttk.Label(output_row, text="Folder:").pack(side=tk.LEFT)
        ttk.Entry(output_row, textvariable=self.output_dir).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        ttk.Button(output_row, text="Browse", command=self.pick_output_folder).pack(side=tk.LEFT)

        options = ttk.LabelFrame(main, text="OCR Options")
        options.pack(fill=tk.X, pady=(0, 10))

        opts = ttk.Frame(options, padding=8)
        opts.pack(fill=tk.X)

        ttk.Label(opts, text="Language (Tesseract code):").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(opts, textvariable=self.language, width=12).grid(row=0, column=1, sticky=tk.W, padx=(6, 18))

        ttk.Label(opts, text="Image DPI:").grid(row=0, column=2, sticky=tk.W)
        ttk.Entry(opts, textvariable=self.dpi, width=10).grid(row=0, column=3, sticky=tk.W, padx=(6, 18))

        ttk.Checkbutton(opts, text="Force OCR", variable=self.force_ocr).grid(row=0, column=4, sticky=tk.W)

        action_row = ttk.Frame(main)
        action_row.pack(fill=tk.X, pady=(0, 10))

        self.start_btn = ttk.Button(action_row, text="Run OCR", command=self.start_ocr)
        self.start_btn.pack(side=tk.LEFT)

        self.progress = ttk.Progressbar(action_row, mode="indeterminate")
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 8))

        self.duration_label = ttk.Label(action_row, text="", width=20, anchor=tk.E)
        self.duration_label.pack(side=tk.RIGHT)

        log_frame = ttk.LabelFrame(main, text="Log")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(log_frame, height=14, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.log_text.configure(state=tk.DISABLED)

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

        # Log runtime discovery information
        if tess_bin_dir:
            exe_name = "tesseract.exe" if (tess_bin_dir / "tesseract.exe").exists() else "tesseract"
            self.log_queue.put(f"OCR Engine configured: Tesseract ({tess_bin_dir / exe_name})")
        else:
            self.log_queue.put("Warning: Tesseract OCR binary not found on runtime paths.")

        if tessdata_dir:
            self.log_queue.put(f"Tessdata models: {tessdata_dir}")

        if gs_bin_dir:
            self.log_queue.put(f"Ghostscript runtime: {gs_bin_dir}")

    def add_pdfs(self) -> None:
        files = filedialog.askopenfilenames(
            title="Select PDF files",
            filetypes=[("PDF files", "*.pdf")],
        )
        for file_str in files:
            path = Path(file_str)
            if path not in self.selected_files:
                self.selected_files.append(path)

        self._refresh_file_list()

    def add_pdf_paths(self, paths: list[str]) -> None:
        for file_str in paths:
            path = Path(file_str)
            if path.suffix.lower() == ".pdf" and path.exists() and path not in self.selected_files:
                self.selected_files.append(path)

        if self.selected_files:
            # Default output to the folder of the first selected PDF when launched from Explorer context menu.
            self.output_dir.set(str(self.selected_files[0].parent))

        self._refresh_file_list()

    def clear_files(self) -> None:
        self.selected_files.clear()
        self.duration_label.config(text="")
        self._refresh_file_list()

    def pick_output_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select output folder")
        if folder:
            self.output_dir.set(folder)

    def _refresh_file_list(self) -> None:
        self.file_list.delete(0, tk.END)
        for file_path in self.selected_files:
            self.file_list.insert(tk.END, str(file_path))

        self.file_count_label.config(text=f"{len(self.selected_files)} file(s) selected")

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _poll_logs(self) -> None:
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self._append_log(msg)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_logs)

    def _update_duration_timer(self) -> None:
        if self.is_processing:
            elapsed = max(0.0, time.time() - self.start_time)
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            self.duration_label.config(text=f"Waiting: {mins:02d}:{secs:02d}")
            self.root.after(200, self._update_duration_timer)

    def start_ocr(self) -> None:
        if self.is_processing or (self.worker_thread and self.worker_thread.is_alive()):
            messagebox.showinfo("OCR running", "OCR is already running.")
            return

        if not self.selected_files:
            messagebox.showwarning("No input", "Select at least one PDF file.")
            return

        out_dir = Path(self.output_dir.get().strip())
        if not out_dir:
            messagebox.showwarning("No output", "Select an output folder.")
            return

        if not out_dir.exists() or not out_dir.is_dir():
            messagebox.showwarning("Invalid output", "Selected output folder does not exist.")
            return

        dpi_value = self.dpi.get().strip()
        if not dpi_value.isdigit() or int(dpi_value) <= 0:
            messagebox.showwarning("Invalid DPI", "DPI must be a positive integer.")
            return

        lang = self.language.get().strip()
        if not lang:
            messagebox.showwarning("Invalid language", "Language cannot be empty.")
            return

        self.is_processing = True
        self.start_time = time.time()
        self.start_btn.config(state=tk.DISABLED)
        self.progress.start(10)
        self.duration_label.config(text="Waiting: 00:00")

        self.worker_thread = threading.Thread(
            target=self._run_ocr_batch,
            args=(self.selected_files.copy(), out_dir, lang, int(dpi_value), self.force_ocr.get()),
            daemon=True,
        )
        self.worker_thread.start()
        self._update_duration_timer()

    def _run_ocr_batch(self, files: list[Path], out_dir: Path, lang: str, dpi: int, force_ocr: bool) -> None:
        batch_start = time.time()
        self.log_queue.put("Starting OCR batch...")
        successes = 0

        for idx, input_pdf in enumerate(files, start=1):
            output_pdf = out_dir / f"{input_pdf.stem}_ocr.pdf"
            self.log_queue.put(f"[{idx}/{len(files)}] Processing: {input_pdf.name}")
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
                    progress_bar=False,
                )
            except MissingDependencyError as exc:
                self.log_queue.put("ERROR: Missing OCR runtime dependency.")
                self.log_queue.put(str(exc))
                self.log_queue.put(
                    "Please verify that the bundled Tesseract OCR and Ghostscript runtimes are present."
                )
                self._finish_batch()
                return
            except Exception as exc:
                file_dur = time.time() - t_file_start
                self.log_queue.put(f"FAIL: {input_pdf.name} (after {file_dur:.1f}s)")
                self.log_queue.put(f"ERROR running OCR: {exc}")
                continue

            file_dur = time.time() - t_file_start
            successes += 1
            self.log_queue.put(f"OK: created {output_pdf.name} (Duration: {file_dur:.1f}s)")

        total_dur = time.time() - batch_start
        self.log_queue.put(f"Batch complete: {successes}/{len(files)} file(s) succeeded in {total_dur:.1f}s total.")
        self._finish_batch()

    def _finish_batch(self) -> None:
        def done() -> None:
            self.is_processing = False
            self.progress.stop()
            self.start_btn.config(state=tk.NORMAL)
            if self.start_time > 0:
                total = time.time() - self.start_time
                mins = int(total // 60)
                secs = int(total % 60)
                if mins > 0:
                    self.duration_label.config(text=f"Duration: {mins}m {secs:02d}s")
                else:
                    self.duration_label.config(text=f"Duration: {total:.1f}s")

        self.root.after(0, done)


def main() -> None:
    multiprocessing.freeze_support()
    root = tk.Tk()
    style = ttk.Style(root)

    # Use a native-friendly theme when available for better widget rendering.
    if "vista" in style.theme_names():
        style.theme_use("vista")
    elif "clam" in style.theme_names():
        style.theme_use("clam")

    app = OCRGuiApp(root)
    if len(sys.argv) > 1:
        app.add_pdf_paths(sys.argv[1:])
    root.mainloop()


if __name__ == "__main__":
    main()
