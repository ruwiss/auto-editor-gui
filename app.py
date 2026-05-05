from __future__ import annotations

import json
import queue
import os
import shutil
import subprocess
import struct
import sys
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk
from tkinter import ttk


APP_TITLE = "AutoEditor GUI"
BG = "#111318"
PANEL = "#191d24"
PANEL_2 = "#202631"
TEXT = "#eef2f8"
MUTED = "#9aa4b2"
ACCENT = "#7c5cff"
ACCENT_HOVER = "#9178ff"
ERROR = "#ff6b6b"
CUT = "#ff4d5e"
WAVE = "#64d2ff"
LINE = "#2b3342"
SETTINGS_PATH = Path.home() / ".autoeditor_gui_settings.json"
DEFAULT_SETTINGS = {
    "audio_threshold": "0.04",
    "margin_before": "0.2s",
    "margin_after": "0.2s",
    "timeline_name": "AutoEditor Timeline",
}


class AutoEditorGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1040x680")
        self.minsize(860, 560)
        self.configure(bg=BG)
        self.option_add("*TCombobox*Listbox.background", PANEL_2)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", "white")

        self.log_queue: queue.Queue[str | tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.is_running = False
        self.preview_after_id: str | None = None
        self.settings_ready = False
        self.slider_dragging = False

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.audio_threshold = tk.StringVar(value="0.04")
        self.margin_before = tk.StringVar(value="0.2s")
        self.margin_after = tk.StringVar(value="0.2s")
        self.timeline_name = tk.StringVar(value="AutoEditor Timeline")
        self.status_text = tk.StringVar(value="Hazır")
        self.last_cut_ranges: list[tuple[float, float]] = []
        self.last_waveform: list[float] = []
        self.last_duration = 0.0

        self._load_settings()
        self._style()
        self._build()
        self._bind_setting_changes()
        self.settings_ready = True
        self.after(120, self._drain_log_queue)

    def _show_tooltip(self, widget: tk.Widget, text: str) -> None:
        self._hide_tooltip()
        x = widget.winfo_rootx() + 18
        y = widget.winfo_rooty() + 18
        tip = tk.Toplevel(self)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tip, text=text, bg="#05070a", fg=TEXT, relief="solid", bd=1, padx=8, pady=6, wraplength=260, justify="left", font=("Segoe UI", 9))
        label.pack()
        self.tooltip = tip

    def _hide_tooltip(self) -> None:
        tip = getattr(self, "tooltip", None)
        if tip is not None:
            tip.destroy()
            self.tooltip = None

    def _help_icon(self, parent: ttk.Frame, text: str) -> tk.Label:
        icon = tk.Label(parent, text="?", bg=PANEL_2, fg=MUTED, width=2, font=("Segoe UI Semibold", 8), cursor="question_arrow")
        icon.bind("<Enter>", lambda event: self._show_tooltip(icon, text))
        icon.bind("<Leave>", lambda event: self._hide_tooltip())
        return icon

    def _style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("Card.TFrame", background=PANEL, relief="flat")
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Tiny.Panel.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 8))
        style.configure("Section.Panel.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI Semibold", 10))
        style.configure("Header.TLabel", background=BG, foreground=TEXT, font=("Segoe UI Semibold", 18))
        style.configure("TButton", background=PANEL_2, foreground=TEXT, borderwidth=0, focusthickness=0, padding=(10, 7), font=("Segoe UI", 9))
        style.map("TButton", background=[("active", "#2a3241"), ("pressed", ACCENT)], foreground=[("disabled", "#6f7785")])
        style.configure("Accent.TButton", background=ACCENT, foreground="white", font=("Segoe UI Semibold", 9))
        style.map("Accent.TButton", background=[("active", ACCENT_HOVER), ("pressed", "#6848ff")], foreground=[("disabled", "#d8d2ff")])
        style.configure("TEntry", fieldbackground=PANEL_2, background=PANEL_2, foreground=TEXT, insertcolor=TEXT, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, borderwidth=1, padding=(6, 4))
        style.map("TEntry", fieldbackground=[("focus", "#121722"), ("!disabled", PANEL_2)], foreground=[("!disabled", TEXT)], bordercolor=[("focus", ACCENT), ("!focus", LINE)])
        style.configure("TCombobox", fieldbackground=PANEL_2, background=PANEL_2, foreground=TEXT, arrowcolor=TEXT, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, borderwidth=1, padding=(6, 4))
        style.map("TCombobox", fieldbackground=[("readonly", PANEL_2), ("focus", "#121722")], background=[("readonly", PANEL_2), ("active", "#2a3241")], foreground=[("readonly", TEXT), ("!disabled", TEXT)], arrowcolor=[("readonly", TEXT)], bordercolor=[("focus", ACCENT), ("!focus", LINE)])
        style.configure("Dark.TCombobox", fieldbackground=PANEL_2, background=PANEL_2, foreground=TEXT, arrowcolor=TEXT, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, borderwidth=1, padding=(6, 4))
        style.map("Dark.TCombobox", fieldbackground=[("readonly", PANEL_2), ("focus", "#121722")], background=[("readonly", PANEL_2), ("active", "#2a3241")], foreground=[("readonly", TEXT), ("!disabled", TEXT)], selectbackground=[("readonly", PANEL_2)], selectforeground=[("readonly", TEXT)], arrowcolor=[("readonly", TEXT)])
        style.configure("TCheckbutton", background=PANEL, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Horizontal.TProgressbar", troughcolor=PANEL_2, background=ACCENT, bordercolor=PANEL_2, lightcolor=ACCENT, darkcolor=ACCENT)

    def _build(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        root.rowconfigure(3, weight=0)

        header = ttk.Frame(root)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(header, text="AutoEditor GUI", style="Header.TLabel").pack(side="left")
        ttk.Label(header, text="Premiere XML · silence cut · waveform preview", style="Muted.TLabel").pack(side="left", padx=(12, 0), pady=(6, 0))

        self._waveform_panel(root, row=1)
        controls = ttk.Frame(root)
        controls.grid(row=2, column=0, sticky="ew", pady=(10, 10))
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(2, weight=1)
        self._file_panel(controls, 0)
        self._settings_panel(controls, 1)
        self._action_panel(controls, 2)
        self._log_panel(root, row=3)

    def _file_panel(self, parent: ttk.Frame, column: int) -> None:
        panel = self._panel_grid(parent, column)
        ttk.Label(panel, text="Dosyalar", style="Section.Panel.TLabel").pack(anchor="w", pady=(0, 8))
        self._path_row(panel, "Video", self.input_path, self._pick_input)
        self._path_row(panel, "Klasör", self.output_path, self._pick_output)

    def _settings_panel(self, parent: ttk.Frame, column: int) -> None:
        panel = self._panel_grid(parent, column)
        ttk.Label(panel, text="Ayarlar", style="Section.Panel.TLabel").pack(anchor="w", pady=(0, 8))
        grid = ttk.Frame(panel, style="Panel.TFrame")
        grid.pack(fill="x")

        self._slider_field(grid, "Sessizlik hassasiyeti", self.audio_threshold, 0.01, 0.12, 0.005, 0, 0, 2, help_text="Yükseltirsen daha fazla alan sessiz kabul edilir ve kesilir. Düşürürsen daha az yer kesilir.")
        self._slider_field(grid, "Kesim öncesi pay", self.margin_before, 0.0, 1.0, 0.05, 1, 0, 2, suffix="s", help_text="Kesimden hemen önce bırakılacak kısa tampon süre.")
        self._slider_field(grid, "Kesim sonrası pay", self.margin_after, 0.0, 1.5, 0.05, 2, 0, 2, suffix="s", help_text="Kesimden hemen sonra bırakılacak kısa tampon süre.")
        self._field(grid, "Timeline adı", lambda parent: self._dark_entry(parent, self.timeline_name), 3, 0, 2, help_text="Premiere içinde görünecek timeline adı.")

    def _action_panel(self, parent: ttk.Frame, column: int) -> None:
        card = self._panel_grid(parent, column)
        ttk.Label(card, text="İşlem", style="Section.Panel.TLabel").pack(anchor="w", pady=(0, 8))
        panel = ttk.Frame(card, style="Panel.TFrame")
        panel.pack(fill="x")
        panel.columnconfigure(0, weight=1)
        panel.columnconfigure(1, weight=1)
        self.preview_button = ttk.Button(panel, text="Komutu Önizle", command=self.preview_command)
        self.preview_button.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 6))
        ttk.Button(panel, text="Sıfırla", command=self.reset_settings).grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=(0, 6))
        ttk.Button(panel, text="Çıktı Klasörü", command=self.open_output_folder).grid(row=1, column=0, sticky="ew", padx=(0, 6))
        self.run_button = ttk.Button(panel, text="Premiere XML Oluştur", style="Accent.TButton", command=self.run_export)
        self.run_button.grid(row=1, column=1, sticky="ew", padx=(6, 0))

        status = ttk.Frame(card, style="Panel.TFrame")
        status.pack(fill="x", pady=(10, 0))
        status.columnconfigure(0, weight=1)
        status.columnconfigure(1, weight=0, minsize=96)
        self.status_label = tk.Label(status, textvariable=self.status_text, bg=PANEL, fg=MUTED, anchor="w", width=34, font=("Segoe UI", 8))
        self.status_label.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.progress = ttk.Progressbar(status, mode="indeterminate", length=90)
        self.progress.grid(row=0, column=1, sticky="e")

    def _waveform_panel(self, parent: ttk.Frame, row: int) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=12)
        panel.grid(row=row, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(2, weight=1)
        head = ttk.Frame(panel, style="Panel.TFrame")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(head, text="Kesim Önizleme", style="Section.Panel.TLabel").pack(side="left")
        ttk.Label(head, text="mavi: ses · kırmızı: kesilecek", style="Tiny.Panel.TLabel").pack(side="right")
        self.preview_summary = tk.StringVar(value="Video seçilince tahmini son süre burada görünecek.")
        ttk.Label(panel, textvariable=self.preview_summary, style="Tiny.Panel.TLabel").grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.wave_canvas = tk.Canvas(panel, height=320, bg="#0b0d12", highlightthickness=0, relief="flat")
        self.wave_canvas.grid(row=2, column=0, sticky="nsew")
        self.wave_canvas.bind("<Configure>", lambda event: self.draw_waveform())
        self.draw_waveform()

    def _log_panel(self, parent: ttk.Frame, row: int) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=12)
        panel.grid(row=row, column=0, sticky="ew")
        panel.columnconfigure(0, weight=1)
        ttk.Label(panel, text="Log", style="Section.Panel.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.log = tk.Text(panel, height=4, bg="#0b0d12", fg=TEXT, insertbackground=TEXT, relief="flat", borderwidth=0, highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT, padx=10, pady=8, font=("Cascadia Mono", 8), wrap="word")
        self.log.grid(row=1, column=0, sticky="ew")
        self._log("Hazır. Video seçip Premiere XML export alabilirsiniz.")

    def _panel(self, parent: ttk.Frame) -> ttk.Frame:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=12)
        panel.pack(fill="x", pady=(0, 10))
        return panel

    def _panel_grid(self, parent: ttk.Frame, column: int) -> ttk.Frame:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=12)
        panel.grid(row=0, column=column, sticky="nsew", padx=(0, 10) if column < 2 else 0)
        parent.rowconfigure(0, weight=1)
        return panel

    def _path_row(self, parent: ttk.Frame, label: str, variable: tk.StringVar, command) -> None:
        row = ttk.Frame(parent, style="Panel.TFrame")
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=label, style="Tiny.Panel.TLabel", width=6).pack(side="left")
        tk.Entry(row, textvariable=variable, bg=PANEL_2, fg=TEXT, insertbackground=TEXT, relief="flat", highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT, disabledbackground=PANEL_2, disabledforeground=MUTED, font=("Segoe UI", 8)).pack(side="left", fill="x", expand=True, padx=8, ipady=5)
        ttk.Button(row, text="Seç", command=command).pack(side="right")

    def _dark_entry(self, parent: ttk.Frame, variable: tk.StringVar) -> tk.Entry:
        return tk.Entry(
            parent,
            textvariable=variable,
            bg=PANEL_2,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=LINE,
            highlightcolor=ACCENT,
            disabledbackground=PANEL_2,
            disabledforeground=MUTED,
        )

    def _field(self, parent: ttk.Frame, label: str, widget_factory, row: int, column: int, columnspan: int = 1, help_text: str = "") -> None:
        frame = ttk.Frame(parent, style="Panel.TFrame")
        frame.grid(row=row, column=column, columnspan=columnspan, sticky="ew", padx=(0, 8), pady=4)
        top = ttk.Frame(frame, style="Panel.TFrame")
        top.pack(fill="x")
        ttk.Label(top, text=label, style="Tiny.Panel.TLabel").pack(side="left")
        if help_text:
            self._help_icon(top, help_text).pack(side="right")
        widget = widget_factory(frame)
        widget.pack(fill="x", pady=(2, 0))
        parent.columnconfigure(column, weight=1)

    def _slider_field(self, parent: ttk.Frame, label: str, variable: tk.StringVar, minimum: float, maximum: float, step: float, row: int, column: int, columnspan: int = 1, suffix: str = "", help_text: str = "") -> None:
        frame = ttk.Frame(parent, style="Panel.TFrame")
        frame.grid(row=row, column=column, columnspan=columnspan, sticky="ew", padx=(0, 8), pady=5)
        frame.columnconfigure(0, weight=1)
        top = ttk.Frame(frame, style="Panel.TFrame")
        top.grid(row=0, column=0, sticky="ew")
        ttk.Label(top, text=label, style="Tiny.Panel.TLabel").pack(side="left")
        if help_text:
            self._help_icon(top, help_text).pack(side="left", padx=(6, 0))
        value_label = tk.Label(top, text=variable.get(), bg=PANEL_2, fg=TEXT, width=7, anchor="e", padx=6, pady=2, font=("Consolas", 8))
        value_label.pack(side="right")
        scale_value = tk.DoubleVar(value=self._time_to_seconds(variable.get()) if suffix else self._threshold_to_float(variable.get()))
        is_dragging = tk.BooleanVar(value=False)

        def update(value: str) -> None:
            number = round(round(float(value) / step) * step, 4)
            if suffix:
                text = f"{number:.2f}{suffix}".replace(".00", "")
            else:
                text = f"{number:.3f}".rstrip("0").rstrip(".")
            variable.set(text)
            value_label.configure(text=text)
            if not is_dragging.get():
                self._settings_changed()

        scale = tk.Scale(
            frame,
            from_=minimum,
            to=maximum,
            resolution=step,
            orient="horizontal",
            variable=scale_value,
            command=update,
            showvalue=False,
            bg=PANEL,
            fg=TEXT,
            troughcolor=PANEL_2,
            activebackground=ACCENT,
            highlightthickness=0,
            bd=0,
        )
        scale.grid(row=1, column=0, sticky="ew")
        scale.bind("<ButtonPress-1>", lambda event: self._start_slider_drag(is_dragging))
        scale.bind("<ButtonRelease-1>", lambda event: self._finish_slider_drag(is_dragging))

        def sync_from_variable(*_: object) -> None:
            if is_dragging.get():
                return
            number = self._time_to_seconds(variable.get()) if suffix else self._threshold_to_float(variable.get())
            scale_value.set(number)
            value_label.configure(text=variable.get())

        variable.trace_add("write", sync_from_variable)
        parent.columnconfigure(column, weight=1)

    def _start_slider_drag(self, is_dragging: tk.BooleanVar) -> None:
        self.slider_dragging = True
        is_dragging.set(True)

    def _finish_slider_drag(self, is_dragging: tk.BooleanVar) -> None:
        self.slider_dragging = False
        is_dragging.set(False)
        self._settings_changed()

    def _pick_input(self) -> None:
        path = filedialog.askopenfilename(title="Video seç", filetypes=(("Video", "*.mp4 *.mov *.mkv *.avi *.m4v *.webm"), ("Tüm dosyalar", "*.*")))
        if not path:
            return
        self.input_path.set(path)
        source = Path(path)
        if not self.output_path.get().strip():
            self.output_path.set(str(source.parent))
        self.timeline_name.set(source.stem)
        self._settings_changed()

    def _pick_output(self) -> None:
        path = filedialog.askdirectory(title="Premiere XML çıktı klasörü")
        if path:
            self.output_path.set(path)
            self._settings_changed()

    def _bind_setting_changes(self) -> None:
        variables = (
            self.output_path,
            self.audio_threshold,
            self.margin_before,
            self.margin_after,
            self.timeline_name,
        )
        for variable in variables:
            variable.trace_add("write", lambda *_: self._settings_changed())

    def _settings_changed(self) -> None:
        if not getattr(self, "settings_ready", False):
            return
        if self.slider_dragging:
            return
        self._save_settings()
        if self.input_path.get().strip():
            self._schedule_preview()

    def _schedule_preview(self) -> None:
        if self.preview_after_id:
            self.after_cancel(self.preview_after_id)
        self.preview_after_id = self.after(900, self._auto_preview)

    def _auto_preview(self) -> None:
        self.preview_after_id = None
        if self.worker and self.worker.is_alive():
            self._schedule_preview()
            return
        self.preview_cuts(silent=True)

    def _load_settings(self) -> None:
        if not SETTINGS_PATH.exists():
            return
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return
        mapping = {
            "output_path": self.output_path,
            "audio_threshold": self.audio_threshold,
            "margin_before": self.margin_before,
            "margin_after": self.margin_after,
            "timeline_name": self.timeline_name,
        }
        for key, variable in mapping.items():
            if key in data:
                variable.set(str(data[key]))

    def _save_settings(self) -> None:
        data = {
            "output_path": self.output_path.get(),
            "audio_threshold": self.audio_threshold.get(),
            "margin_before": self.margin_before.get(),
            "margin_after": self.margin_after.get(),
            "timeline_name": self.timeline_name.get(),
        }
        try:
            SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def reset_settings(self) -> None:
        for key, value in DEFAULT_SETTINGS.items():
            variable = getattr(self, key, None)
            if isinstance(variable, tk.StringVar):
                variable.set(value)
        if self.input_path.get().strip():
            self.timeline_name.set(Path(self.input_path.get().strip()).stem)
        self._set_status("Ayarlar sıfırlandı")
        self._settings_changed()

    def _set_status(self, text: str) -> None:
        self.status_text.set(text if len(text) <= 42 else text[:39] + "...")

    def build_command(self) -> list[str]:
        input_file = self.input_path.get().strip()
        output_folder = self.output_path.get().strip()
        if not input_file:
            raise ValueError("Video dosyası seçilmedi.")
        if not output_folder:
            raise ValueError("Çıktı klasörü seçilmedi.")
        output_parent = Path(output_folder)
        output_parent.mkdir(parents=True, exist_ok=True)
        source = Path(input_file)
        output_file = output_parent / f"{source.stem}_premiere.xml"

        edit = self._edit_expression()
        export = self._premiere_export_value()
        margin = f"{self.margin_before.get().strip()},{self.margin_after.get().strip()}"

        command = [
            sys.executable,
            "-m",
            "auto_editor",
            input_file,
            "--edit",
            edit,
            "--margin",
            margin,
            "--when-normal",
            "speed:1",
            "--when-silent",
            "speed:99999",
            "--export",
            export,
            "-o",
            str(output_file),
        ]
        return command

    def _edit_expression(self) -> str:
        return f"audio:threshold={self.audio_threshold.get().strip()},stream=all"

    def _premiere_export_value(self) -> str:
        name = self.timeline_name.get().strip()
        if not name:
            return "premiere"
        safe_name = name.replace('"', "'")
        return f'premiere:name="{safe_name}"'

    def preview_command(self) -> None:
        try:
            command = self.build_command()
        except ValueError as exc:
            messagebox.showwarning(APP_TITLE, str(exc))
            return
        command_text = subprocess.list2cmdline(command)
        self._log("Komut önizleme:")
        self._log(command_text)
        self._set_status("Komut hazır")
        messagebox.showinfo(APP_TITLE, command_text)

    def copy_command(self) -> None:
        try:
            command_text = subprocess.list2cmdline(self.build_command())
        except ValueError as exc:
            messagebox.showwarning(APP_TITLE, str(exc))
            return
        self.clipboard_clear()
        self.clipboard_append(command_text)
        self._set_status("Komut kopyalandı")
        self._log("Komut panoya kopyalandı.")

    def open_output_folder(self) -> None:
        output_folder = self.output_path.get().strip()
        if not output_folder:
            messagebox.showwarning(APP_TITLE, "Önce çıktı klasörü seçin.")
            return
        folder = Path(output_folder)
        if not folder.exists():
            messagebox.showwarning(APP_TITLE, "Çıktı klasörü bulunamadı.")
            return
        os.startfile(folder)

    def preview_cuts(self, silent: bool = False) -> None:
        if self.worker and self.worker.is_alive():
            if not silent:
                messagebox.showinfo(APP_TITLE, "Zaten çalışan bir işlem var.")
            return
        try:
            input_file = self.input_path.get().strip()
            if not input_file:
                raise ValueError("Video dosyası seçilmedi.")
        except ValueError as exc:
            if not silent:
                messagebox.showwarning(APP_TITLE, str(exc))
            return
        if not silent:
            self._log("Kesim önizleme analizi başladı...")
            self._log("Önizleme için ffmpeg ile ses dalgası ve silence bölgeleri hesaplanıyor.")
        self._set_running(True, "Analiz ediliyor... kesilecek sessizlikler çıkarılıyor")
        self.worker = threading.Thread(target=self._run_preview_analysis, args=(input_file,), daemon=True)
        self.worker.start()

    def _run_preview_analysis(self, input_file: str) -> None:
        try:
            media_duration = self._probe_duration(input_file)
            waveform = self._extract_waveform(input_file, 900)
            if not waveform:
                self.log_queue.put("__DONE_ERROR__Waveform çıkarılamadı. ffmpeg/ffprobe PATH içinde olmalı ve videoda ses kanalı bulunmalı.")
                return
            cut_ranges = self._detect_audio_cuts_from_waveform(waveform, media_duration)
            duration = media_duration
        except Exception as exc:
            self.log_queue.put(f"__DONE_ERROR__Önizleme okunamadı: {exc}")
            return
        self.log_queue.put(("__PREVIEW_READY__", {"cuts": cut_ranges, "duration": duration, "waveform": waveform}))

    def _detect_audio_cuts_from_waveform(self, waveform: list[float], duration: float) -> list[tuple[float, float]]:
        if not waveform or duration <= 0:
            return []
        threshold = self._threshold_to_float(self.audio_threshold.get().strip())
        before = self._time_to_seconds(self.margin_before.get().strip())
        after = self._time_to_seconds(self.margin_after.get().strip())
        min_silence = 0.18
        ranges: list[tuple[float, float]] = []
        start_index: int | None = None
        for index, amp in enumerate(waveform):
            silent = amp < threshold
            if silent and start_index is None:
                start_index = index
            if (not silent or index == len(waveform) - 1) and start_index is not None:
                end_index = index if not silent else index + 1
                start = (start_index / len(waveform)) * duration
                end = (end_index / len(waveform)) * duration
                if end - start >= min_silence:
                    cut_start = max(0.0, start + before)
                    cut_end = max(cut_start, end - after)
                    if cut_end > cut_start:
                        ranges.append((cut_start, cut_end))
                start_index = None
        return ranges

    def _threshold_to_float(self, value: str) -> float:
        try:
            cleaned = value.strip().replace("%", "")
            number = float(cleaned)
            if "%" in value:
                return max(0.0, min(1.0, number / 100))
            return max(0.0, min(1.0, number))
        except ValueError:
            return 0.04

    def _time_to_seconds(self, value: str) -> float:
        cleaned = value.strip().lower().replace("sec", "").replace("s", "")
        try:
            return max(0.0, float(cleaned))
        except ValueError:
            return 0.0

    def _probe_duration(self, input_file: str) -> float:
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return 0.0
        command = [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            input_file,
        ]
        process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", timeout=30)
        if process.returncode != 0:
            return 0.0
        try:
            return float(process.stdout.strip())
        except ValueError:
            return 0.0

    def _extract_waveform(self, input_file: str, samples: int) -> list[float]:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return []
        command = [
            ffmpeg,
            "-v",
            "error",
            "-i",
            input_file,
            "-ac",
            "1",
            "-filter:a",
            f"aresample={samples}",
            "-map",
            "0:a:0",
            "-f",
            "s16le",
            "-",
        ]
        process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
        raw = process.stdout
        if process.returncode != 0 or not raw:
            return []
        values = struct.unpack(f"<{len(raw) // 2}h", raw[: len(raw) - (len(raw) % 2)])
        if not values:
            return []
        bucket_size = max(1, len(values) // samples)
        waveform: list[float] = []
        for index in range(0, len(values), bucket_size):
            bucket = values[index : index + bucket_size]
            peak = max(abs(value) for value in bucket) / 32768
            waveform.append(min(1.0, peak))
        return waveform[:samples]

    def run_export(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(APP_TITLE, "Zaten çalışan bir işlem var.")
            return
        try:
            command = self.build_command()
        except ValueError as exc:
            messagebox.showwarning(APP_TITLE, str(exc))
            return
        self._log("Export başladı...")
        self._log(subprocess.list2cmdline(command))
        self._set_running(True)
        self.worker = threading.Thread(target=self._run_command, args=(command,), daemon=True)
        self.worker.start()

    def _run_command(self, command: list[str]) -> None:
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        except FileNotFoundError:
            self.log_queue.put("__DONE_ERROR__HATA: Python/auto-editor başlatılamadı. `py -m pip install -r requirements.txt` çalıştırın.")
            return
        assert process.stdout is not None
        for line in process.stdout:
            self.log_queue.put(line.rstrip())
        code = process.wait()
        if code == 0:
            self.log_queue.put("__DONE_OK__Tamamlandı. XML dosyasını Premiere Pro içine import edebilirsiniz.")
        else:
            self.log_queue.put(f"__DONE_ERROR__İşlem hata kodu ile bitti: {code}")

    def _drain_log_queue(self) -> None:
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(message, tuple) and message[0] == "__PREVIEW_READY__":
                payload = message[1]
                self.last_cut_ranges = payload["cuts"]
                self.last_duration = payload["duration"]
                self.last_waveform = payload["waveform"]
                self._set_running(False)
                cut_total = sum(end - start for start, end in self.last_cut_ranges)
                final_duration = max(0.0, self.last_duration - cut_total)
                summary = f"Orijinal {self._format_time(self.last_duration)} · Kesilecek {self._format_time(cut_total)} · Son süre ≈ {self._format_time(final_duration)} · {len(self.last_cut_ranges)} bölüm"
                self.preview_summary.set(summary)
                self._set_status(f"Son süre ≈ {self._format_time(final_duration)}")
                self.draw_waveform()
                self._log(f"Önizleme hazır. Kesilecek bölüm sayısı: {len(self.last_cut_ranges)}")
                continue
            if message.startswith("__DONE_OK__"):
                self._set_running(False)
                self._set_status("Tamamlandı")
                self._log(message.replace("__DONE_OK__", "", 1))
                messagebox.showinfo(APP_TITLE, "Premiere XML oluşturuldu.")
                continue
            if message.startswith("__DONE_ERROR__"):
                self._set_running(False)
                self._set_status("Hata oluştu")
                self._log(message.replace("__DONE_ERROR__", "", 1))
                continue
            self._log(message)
        self.after(120, self._drain_log_queue)

    def _set_running(self, running: bool, status: str | None = None) -> None:
        self.is_running = running
        state = "disabled" if running else "normal"
        self.run_button.configure(state=state)
        self.preview_button.configure(state=state)
        if running:
            self._set_status(status or "Çalışıyor...")
            self.progress.start(12)
        else:
            self.progress.stop()

    def clear_log(self) -> None:
        self.log.delete("1.0", "end")
        self._set_status("Log temizlendi")

    def _log(self, message: str) -> None:
        self.log.insert("end", message + "\n")
        self.log.see("end")

    def draw_waveform(self) -> None:
        if not hasattr(self, "wave_canvas"):
            return
        canvas = self.wave_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        mid = height / 2
        canvas.create_rectangle(0, 0, width, height, fill="#0b0d12", outline="")
        canvas.create_line(0, mid, width, mid, fill="#263241")

        if self.last_duration > 0:
            for start, end in self.last_cut_ranges:
                x1 = max(0, min(width, (start / self.last_duration) * width))
                x2 = max(0, min(width, (end / self.last_duration) * width))
                canvas.create_rectangle(x1, 0, x2, height, fill=CUT, stipple="gray50", outline="")

        if self.last_waveform:
            count = len(self.last_waveform)
            for index, amp in enumerate(self.last_waveform):
                x = (index / max(1, count - 1)) * width
                y = amp * (height * 0.42)
                canvas.create_line(x, mid - y, x, mid + y, fill=WAVE)
        else:
            canvas.create_text(width / 2, mid, text="Kesimleri görmek için video seçip 'Kesimleri Önizle'ye basın", fill=MUTED, font=("Segoe UI", 10))

        if self.last_duration > 0:
            canvas.create_text(8, height - 14, text="0:00", fill=MUTED, anchor="w", font=("Segoe UI", 8))
            canvas.create_text(width - 8, height - 14, text=self._format_time(self.last_duration), fill=MUTED, anchor="e", font=("Segoe UI", 8))

    def _format_time(self, seconds: float) -> str:
        total = max(0, int(seconds))
        minutes, secs = divmod(total, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"


if __name__ == "__main__":
    AutoEditorGui().mainloop()
