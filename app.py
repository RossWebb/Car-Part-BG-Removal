import os
import sys
import traceback
from pathlib import Path
from rembg import remove, new_session
from PIL import Image
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, colorchooser
from tkinterdnd2 import TkinterDnD, DND_FILES
import threading
import time

# Write a log file next to the exe so errors are always recoverable
LOG_PATH = Path(sys.executable).parent / "error.log" if getattr(sys, "frozen", False) \
           else Path(__file__).parent / "error.log"

def write_error_log(exc: Exception):
    try:
        with open(LOG_PATH, "w") as f:
            f.write("PartOutCutter error log\n")
            f.write("=" * 50 + "\n")
            f.write(traceback.format_exc())
    except Exception:
        pass


# ── Preset definitions ────────────────────────────────────────────────────────

PRESETS = {
    "Standard": dict(
        model="isnet-general-use",
        alpha_matting=False,
        fg_threshold=240,
        bg_threshold=10,
        erode_size=10,
        post_process=False,
        bgcolor=None,
    ),
    "Conservative (reflective parts)": dict(
        model="u2net",
        alpha_matting=True,
        fg_threshold=200,
        bg_threshold=30,
        erode_size=4,
        post_process=True,
        bgcolor=None,
    ),
    "Clean edges (hair/fur)": dict(
        model="isnet-general-use",
        alpha_matting=True,
        fg_threshold=240,
        bg_threshold=10,
        erode_size=10,
        post_process=True,
        bgcolor=None,
    ),
    "White background": dict(
        model="isnet-general-use",
        alpha_matting=False,
        fg_threshold=240,
        bg_threshold=10,
        erode_size=10,
        post_process=False,
        bgcolor=(255, 255, 255, 255),
    ),
}

MODELS = [
    "isnet-general-use",
    "u2net",
    "u2net_human_seg",
    "silueta",
    "isnet-anime",
]


def _silent_tqdm_init(original_init):
    """Wrap tqdm __init__ to force disable=True so it never tries to write to stdout."""
    def patched_init(self, *args, **kwargs):
        kwargs["disable"] = True
        original_init(self, *args, **kwargs)
    return patched_init


class PartOutApp:
    def __init__(self):
        self.root = TkinterDnD.Tk()
        self.root.title("Part-Out Cutter - Catalogue Edition")
        self.root.geometry("860x780")
        self.root.configure(bg="#0f172a")
        self.root.resizable(False, False)

        self.session = None
        self.current_model_name = None
        self.processing = False
        self.output_dir = None

        # Settings vars — populated in setup_settings_panel()
        self.var_preset = None
        self.var_model = None
        self.var_alpha_matting = None
        self.var_fg_threshold = None
        self.var_bg_threshold = None
        self.var_erode_size = None
        self.var_post_process = None
        self.var_bgcolor_enabled = None
        self._bgcolor_rgba = None          # (R,G,B,255) or None
        self._bgcolor_swatch = None        # tk.Label used as colour swatch

        self.setup_ui()
        threading.Thread(target=self.load_model_then_enable, daemon=True).start()
        self.root.mainloop()

    # ═══════════════════════════════════════════════════════════════════ UI ══

    def setup_ui(self):
        # ── Title ──────────────────────────────────────────────────────────
        tk.Label(self.root, text="Part-Out Cutter",
                 font=("Arial", 26, "bold"), fg="#60a5fa", bg="#0f172a"
                 ).pack(pady=(16, 2))
        tk.Label(self.root, text="Catalogue Edition  •  AI Background Removal  •  R.Webb 2026",
                 font=("Arial", 10), fg="#475569", bg="#0f172a"
                 ).pack(pady=(0, 8))

        # ── Status ─────────────────────────────────────────────────────────
        self.status_var = tk.StringVar(value="⏳  Loading AI model — please wait…")
        self.status_label = tk.Label(self.root, textvariable=self.status_var,
                                     font=("Arial", 11), fg="#fbbf24", bg="#0f172a")
        self.status_label.pack(pady=(0, 6))

        self.progress = ttk.Progressbar(self.root, mode="indeterminate", length=420)
        self.progress.pack(pady=(0, 8))
        self.progress.start(12)

        # ── Action buttons ─────────────────────────────────────────────────
        btn_frame = tk.Frame(self.root, bg="#0f172a")
        btn_frame.pack(pady=4)

        def mkbtn(parent, text, cmd, primary=True):
            return tk.Button(
                parent, text=text, command=cmd,
                font=("Arial", 11, "bold" if primary else "normal"),
                bg="#1d4ed8" if primary else "#334155",
                fg="white",
                activebackground="#2563eb" if primary else "#475569",
                activeforeground="white",
                relief="flat", padx=16, pady=7, state="disabled",
            )

        self.btn_files  = mkbtn(btn_frame, "📂  Select Files",   self.select_files)
        self.btn_folder = mkbtn(btn_frame, "📁  Select Folder",  self.select_folder)
        self.btn_outdir = mkbtn(btn_frame, "💾  Output Folder",  self.choose_output_dir, primary=False)
        for b in (self.btn_files, self.btn_folder, self.btn_outdir):
            b.pack(side="left", padx=6)

        self.outdir_var = tk.StringVar(value="Output: same folder as input")
        tk.Label(self.root, textvariable=self.outdir_var,
                 font=("Consolas", 9), fg="#64748b", bg="#0f172a").pack(pady=(2, 0))

        # ── Settings panel ─────────────────────────────────────────────────
        # ── Drop zone ──────────────────────────────────────────────────────
        self.drop_zone = tk.Label(
            self.root,
            text="⬇   Drop images or a folder here   ⬇",
            font=("Arial", 11, "bold"),
            fg="#60a5fa",
            bg="#162032",
            relief="groove",
            pady=12,
            cursor="hand2",
        )
        self.drop_zone.pack(fill="x", padx=25, pady=(8, 0))
        self.drop_zone.drop_target_register(DND_FILES)
        self.drop_zone.dnd_bind("<<Drop>>", self._on_drop)
        self.drop_zone.dnd_bind("<<DragEnter>>", self._on_drop_enter)
        self.drop_zone.dnd_bind("<<DragLeave>>", self._on_drop_leave)

        self.setup_settings_panel()

        # ── Log ────────────────────────────────────────────────────────────
        log_frame = tk.Frame(self.root, bg="#0f172a")
        log_frame.pack(fill="both", expand=True, padx=25, pady=(8, 14))

        self.log_text = tk.Text(log_frame, height=10, bg="#1e293b", fg="#e2e8f0",
                                font=("Consolas", 10), relief="flat",
                                insertbackground="white")
        sb = tk.Scrollbar(log_frame, command=self.log_text.yview, bg="#334155")
        self.log_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)

        self.log("Application started.")
        self.log("Loading AI model in the background…")

    # ── Settings panel ────────────────────────────────────────────────────────

    def setup_settings_panel(self):
        outer = tk.LabelFrame(self.root, text="  Settings  ", font=("Arial", 10, "bold"),
                              fg="#94a3b8", bg="#1e293b", bd=1, relief="groove",
                              padx=14, pady=10)
        outer.pack(fill="x", padx=25, pady=(8, 4))

        # Tk variables
        self.var_preset         = tk.StringVar(value="Standard")
        self.var_model          = tk.StringVar(value="isnet-general-use")
        self.var_alpha_matting  = tk.BooleanVar(value=False)
        self.var_fg_threshold   = tk.IntVar(value=240)
        self.var_bg_threshold   = tk.IntVar(value=10)
        self.var_erode_size     = tk.IntVar(value=10)
        self.var_post_process   = tk.BooleanVar(value=False)
        self.var_bgcolor_enabled = tk.BooleanVar(value=False)

        col_lbl = dict(fg="#94a3b8", bg="#1e293b", font=("Arial", 9))
        col_val = dict(fg="#e2e8f0", bg="#1e293b", font=("Arial", 9))
        col_frm = dict(bg="#1e293b")

        # ── Row 0: Preset + Model ──────────────────────────────────────────
        r0 = tk.Frame(outer, **col_frm); r0.pack(fill="x", pady=(0, 6))

        tk.Label(r0, text="Preset:", **col_lbl).pack(side="left")
        preset_menu = ttk.Combobox(r0, textvariable=self.var_preset,
                                   values=list(PRESETS.keys()), state="readonly", width=28)
        preset_menu.pack(side="left", padx=(4, 20))
        preset_menu.bind("<<ComboboxSelected>>", self._apply_preset)

        tk.Label(r0, text="Model:", **col_lbl).pack(side="left")
        model_menu = ttk.Combobox(r0, textvariable=self.var_model,
                                  values=MODELS, state="readonly", width=22)
        model_menu.pack(side="left", padx=4)
        model_menu.bind("<<ComboboxSelected>>", self._on_model_changed)

        # ── Row 1: Alpha matting toggle ────────────────────────────────────
        r1 = tk.Frame(outer, **col_frm); r1.pack(fill="x", pady=2)
        self.chk_alpha = tk.Checkbutton(r1, text="Alpha matting  (better edges — slower)",
                                        variable=self.var_alpha_matting,
                                        command=self._toggle_matting_controls,
                                        fg="#cbd5e1", bg="#1e293b",
                                        selectcolor="#0f172a", activebackground="#1e293b",
                                        font=("Arial", 9))
        self.chk_alpha.pack(side="left")

        # ── Row 2: Matting sliders ─────────────────────────────────────────
        self.matting_frame = tk.Frame(outer, **col_frm)
        self.matting_frame.pack(fill="x", pady=(0, 4))

        def slider_row(parent, label, var, from_, to, tooltip=""):
            f = tk.Frame(parent, **col_frm)
            f.pack(fill="x", pady=1)
            tk.Label(f, text=label, width=26, anchor="w", **col_lbl).pack(side="left")
            s = tk.Scale(f, variable=var, from_=from_, to=to, orient="horizontal",
                         length=200, bg="#1e293b", fg="#e2e8f0",
                         troughcolor="#334155", highlightthickness=0,
                         activebackground="#60a5fa", font=("Arial", 8))
            s.pack(side="left")
            val_lbl = tk.Label(f, textvariable=var, width=4, **col_val)
            val_lbl.pack(side="left", padx=4)
            if tooltip:
                tk.Label(f, text=tooltip, fg="#475569", bg="#1e293b",
                         font=("Arial", 8)).pack(side="left")
            return s

        self.sl_fg = slider_row(self.matting_frame,
                                "  Foreground threshold:", self.var_fg_threshold,
                                0, 255, "↑ = less foreground kept")
        self.sl_bg = slider_row(self.matting_frame,
                                "  Background threshold:", self.var_bg_threshold,
                                0, 255, "↑ = more background kept")
        self.sl_er = slider_row(self.matting_frame,
                                "  Erode size:", self.var_erode_size,
                                0, 40,  "shrinks uncertain edge region")

        self._toggle_matting_controls()   # grey out if unchecked

        # ── Row 3: Post-process + bgcolor ─────────────────────────────────
        r3 = tk.Frame(outer, **col_frm); r3.pack(fill="x", pady=(4, 0))

        tk.Checkbutton(r3, text="Post-process mask  (softer edges)",
                       variable=self.var_post_process,
                       fg="#cbd5e1", bg="#1e293b", selectcolor="#0f172a",
                       activebackground="#1e293b", font=("Arial", 9)
                       ).pack(side="left", padx=(0, 20))

        tk.Checkbutton(r3, text="Fill background:",
                       variable=self.var_bgcolor_enabled,
                       command=self._toggle_bgcolor,
                       fg="#cbd5e1", bg="#1e293b", selectcolor="#0f172a",
                       activebackground="#1e293b", font=("Arial", 9)
                       ).pack(side="left")

        self._bgcolor_swatch = tk.Label(r3, text="  255, 255, 255  ",
                                        bg="#ffffff", fg="#000000",
                                        font=("Consolas", 8), relief="groove",
                                        cursor="hand2")
        self._bgcolor_swatch.pack(side="left", padx=4)
        self._bgcolor_swatch.bind("<Button-1>", self._pick_bgcolor)
        self._bgcolor_rgba = (255, 255, 255, 255)
        self._toggle_bgcolor()

    # ── Settings helpers ──────────────────────────────────────────────────────

    def _apply_preset(self, _event=None):
        p = PRESETS.get(self.var_preset.get(), PRESETS["Standard"])
        self.var_model.set(p["model"])
        self.var_alpha_matting.set(p["alpha_matting"])
        self.var_fg_threshold.set(p["fg_threshold"])
        self.var_bg_threshold.set(p["bg_threshold"])
        self.var_erode_size.set(p["erode_size"])
        self.var_post_process.set(p["post_process"])
        if p["bgcolor"]:
            self._bgcolor_rgba = p["bgcolor"]
            self.var_bgcolor_enabled.set(True)
            self._update_swatch()
        else:
            self.var_bgcolor_enabled.set(False)
        self._toggle_matting_controls()
        self._toggle_bgcolor()
        self._on_model_changed()
        self.log(f"Preset applied: {self.var_preset.get()}")

    def _on_model_changed(self, _event=None):
        chosen = self.var_model.get()
        if chosen != self.current_model_name:
            self.log(f"Model changed to '{chosen}' — will reload on next run.")

    def _toggle_matting_controls(self):
        state = "normal" if self.var_alpha_matting.get() else "disabled"
        for w in (self.sl_fg, self.sl_bg, self.sl_er):
            w.configure(state=state)

    def _toggle_bgcolor(self):
        state = "normal" if self.var_bgcolor_enabled.get() else "disabled"
        self._bgcolor_swatch.configure(
            cursor="hand2" if self.var_bgcolor_enabled.get() else "arrow"
        )

    def _pick_bgcolor(self, _event=None):
        if not self.var_bgcolor_enabled.get():
            return
        colour = colorchooser.askcolor(
            color=f"#{self._bgcolor_rgba[0]:02x}{self._bgcolor_rgba[1]:02x}{self._bgcolor_rgba[2]:02x}",
            title="Choose background fill colour",
        )
        if colour and colour[0]:
            r, g, b = (int(x) for x in colour[0])
            self._bgcolor_rgba = (r, g, b, 255)
            self._update_swatch()

    def _update_swatch(self):
        r, g, b, _ = self._bgcolor_rgba
        hex_col = f"#{r:02x}{g:02x}{b:02x}"
        luma = 0.299 * r + 0.587 * g + 0.114 * b
        fg = "#000000" if luma > 128 else "#ffffff"
        self._bgcolor_swatch.configure(bg=hex_col, fg=fg,
                                       text=f"  {r}, {g}, {b}  ")

    def _get_remove_kwargs(self) -> dict:
        """Build the kwargs dict for rembg.remove() from current UI settings."""
        kwargs = dict(session=self.session,
                      post_process_mask=self.var_post_process.get())
        if self.var_alpha_matting.get():
            kwargs.update(
                alpha_matting=True,
                alpha_matting_foreground_threshold=self.var_fg_threshold.get(),
                alpha_matting_background_threshold=self.var_bg_threshold.get(),
                alpha_matting_erode_size=self.var_erode_size.get(),
            )
        if self.var_bgcolor_enabled.get() and self._bgcolor_rgba:
            kwargs["bgcolor"] = self._bgcolor_rgba
        return kwargs

    # ═══════════════════════════════════════════════════════════════ Model ═══

    def _load_session(self, model_name: str):
        self.log(f"Loading model '{model_name}'…")
        self.log("If this is the first run, model weights will download (~170 MB)…")
        start = time.time()
        # Disable tqdm progress bar — it crashes when there is no console
        # (which is always the case in a --windowed PyInstaller build)
        import tqdm
        import os
        os.environ["TQDM_DISABLE"] = "1"
        tqdm.tqdm.__init__ = _silent_tqdm_init(tqdm.tqdm.__init__)
        self.session = new_session(model_name)
        self.current_model_name = model_name
        self.log(f"Model loaded in {time.time()-start:.1f}s  ✓")

    def load_model_then_enable(self):
        try:
            self._load_session(self.var_model.get())
            self.root.after(0, self._on_model_ready)
        except Exception as exc:
            write_error_log(exc)
            self.root.after(0, lambda: self._on_model_error(
                f"{exc}\n\nFull traceback written to:\n{LOG_PATH}"))

    def _ensure_model(self):
        """Reload session if the user has picked a different model."""
        chosen = self.var_model.get()
        if chosen != self.current_model_name:
            self._load_session(chosen)

    def _on_model_ready(self):
        self.progress.stop()
        self.progress.pack_forget()
        self.status_var.set("✅  Model ready — select images to process")
        self.status_label.configure(fg="#4ade80")
        for b in (self.btn_files, self.btn_folder, self.btn_outdir):
            b.configure(state="normal")
        self.log("Ready.")

    def _on_model_error(self, msg):
        self.progress.stop()
        self.progress.pack_forget()
        self.status_var.set("❌  Model failed to load")
        self.status_label.configure(fg="#f87171")
        self.log(f"ERROR: {msg}")
        messagebox.showerror("Model Error", f"Failed to load AI model:\n\n{msg}")

    # ═══════════════════════════════════════════════════════ File selection ═══

    def choose_output_dir(self):
        folder = filedialog.askdirectory(title="Choose output folder")
        if folder:
            self.output_dir = folder
            self.outdir_var.set(f"Output: {folder}")
            self.log(f"Output folder → {folder}")

    def _parse_drop_paths(self, data: str) -> list:
        """Parse tkinterdnd2 drop data into a list of path strings.
        Paths with spaces are wrapped in curly braces by Windows DnD."""
        paths = []
        data = data.strip()
        while data:
            if data.startswith("{"):
                end = data.index("}")
                paths.append(data[1:end])
                data = data[end + 1:].strip()
            else:
                parts = data.split(" ", 1)
                paths.append(parts[0])
                data = parts[1].strip() if len(parts) > 1 else ""
        return paths

    def _on_drop(self, event):
        if self.processing:
            messagebox.showwarning("Busy", "Already processing — please wait.")
            return
        if self.session is None:
            messagebox.showwarning("Not ready", "Model is still loading — please wait.")
            return

        raw_paths = self._parse_drop_paths(event.data)
        files = []

        for raw in raw_paths:
            p = Path(raw)
            if p.is_dir():
                files += [f for f in p.glob("*.*")
                          if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
            elif p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                files.append(p)

        if not files:
            messagebox.showinfo("No images",
                                "No supported images found in the dropped items.\n"
                                "Supported formats: jpg, jpeg, png, webp")
            return

        threading.Thread(target=self.start_processing,
                         args=[files], daemon=True).start()

    def _on_drop_enter(self, event):
        self.drop_zone.configure(fg="#ffffff", bg="#1d4ed8")

    def _on_drop_leave(self, event):
        self.drop_zone.configure(fg="#60a5fa", bg="#162032")

    def select_files(self):
        if self.processing:
            messagebox.showwarning("Busy", "Already processing — please wait.")
            return
        files = filedialog.askopenfilenames(
            title="Select images",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.webp")],
        )
        if files:
            threading.Thread(target=self.start_processing,
                             args=[list(files)], daemon=True).start()

    def select_folder(self):
        if self.processing:
            messagebox.showwarning("Busy", "Already processing — please wait.")
            return
        folder = filedialog.askdirectory(title="Select folder of images")
        if folder:
            files = [p for p in Path(folder).glob("*.*")
                     if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
            if not files:
                messagebox.showinfo("No images",
                                    "No supported images found in that folder.")
                return
            threading.Thread(target=self.start_processing,
                             args=[files], daemon=True).start()

    # ═══════════════════════════════════════════════════════════ Processing ═══

    def start_processing(self, files):
        self.processing = True
        self.root.after(0, self._disable_buttons)

        # Reload model if user changed it
        try:
            self._ensure_model()
        except Exception as exc:
            self.log(f"ERROR loading model: {exc}")
            self.processing = False
            self.root.after(0, self._enable_buttons)
            return

        kwargs = self._get_remove_kwargs()

        # Log active settings
        self.log(f"\n{'─'*52}")
        self.log(f"Batch: {len(files)} image(s)  |  model: {self.current_model_name}")
        self.log(f"  alpha matting : {self.var_alpha_matting.get()}"
                 + (f"  fg={self.var_fg_threshold.get()} "
                    f"bg={self.var_bg_threshold.get()} "
                    f"erode={self.var_erode_size.get()}"
                    if self.var_alpha_matting.get() else ""))
        self.log(f"  post-process  : {self.var_post_process.get()}")
        self.log(f"  bgcolor fill  : {self._bgcolor_rgba if self.var_bgcolor_enabled.get() else 'off'}")

        ok = fail = 0
        for i, filepath in enumerate(files, 1):
            path = Path(filepath)
            self.log(f"[{i}/{len(files)}]  {path.name} …")
            try:
                out_path = self._get_output_path(path)
                self._remove_background(path, out_path, kwargs)
                self.log(f"         ✓  → {out_path.name}")
                ok += 1
            except Exception as exc:
                self.log(f"         ✗  FAILED: {exc}")
                fail += 1

        self.log(f"{'─'*52}")
        self.log(f"Done.  {ok} succeeded, {fail} failed.\n")
        self.processing = False
        self.root.after(0, self._enable_buttons)
        self.root.after(0, lambda: messagebox.showinfo(
            "Batch complete",
            f"Processed {len(files)} image(s).\n✓ {ok} succeeded   ✗ {fail} failed",
        ))

    def _get_output_path(self, input_path: Path) -> Path:
        out_dir = Path(self.output_dir) if self.output_dir else input_path.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / (input_path.stem + "_nobg.png")

    def _remove_background(self, input_path: Path, output_path: Path, kwargs: dict):
        with Image.open(input_path) as img:
            result: Image.Image = remove(img, **kwargs)
        result.save(output_path, "PNG")

    # ══════════════════════════════════════════════════════ Button helpers ════

    def _disable_buttons(self):
        for b in (self.btn_files, self.btn_folder, self.btn_outdir):
            b.configure(state="disabled")
        self.drop_zone.configure(fg="#334155", bg="#0f172a")
        self.status_var.set("⚙️  Processing…")
        self.status_label.configure(fg="#fbbf24")

    def _enable_buttons(self):
        for b in (self.btn_files, self.btn_folder, self.btn_outdir):
            b.configure(state="normal")
        self.drop_zone.configure(fg="#60a5fa", bg="#162032")
        self.status_var.set("✅  Ready")
        self.status_label.configure(fg="#4ade80")

    # ══════════════════════════════════════════════════════════════ Logging ═══

    def log(self, message: str):
        def _append():
            self.log_text.insert("end", message + "\n")
            self.log_text.see("end")
        if threading.current_thread() is threading.main_thread():
            _append()
        else:
            self.root.after(0, _append)


if __name__ == "__main__":
    PartOutApp()
