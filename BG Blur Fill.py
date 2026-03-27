#!/usr/bin/env python3

import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import math
import cv2
import numpy as np
import subprocess
import tempfile
import traceback
from PIL import Image, ImageTk

ASPECT_PRESETS = {
    "9:16 (vertical)": (1080, 1920),
    "16:9 (landscape)": (1920, 1080),
    "1:1 (square)": (1080, 1080),
    "4:5 (portrait)": (1080, 1350),
    "3:4 (portrait)": (1080, 1440),
}

ERROR_LOG = os.path.join(os.path.dirname(__file__), "video_processor_error.txt")
PREVIEW_MAX_W = 960
PREVIEW_MAX_HEIGHT = 400
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp")
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".webm")

BG = "#1f2326"
PANEL = "#262b2e"
PANEL_2 = "#2d3337"
FG = "#e6eef6"
ACCENT = "#4f8ef7"
MUTED = "#9aa5b1"
BORDER = "#394046"
PLACEHOLDER = "#f2f6fb"
PLACEHOLDER_SUB = "#c8d1db"

DEFAULT_BLUR = 25
DEFAULT_BRIGHTNESS = 0


class VideoProcessorApp:
    def __init__(self, root):
        self.root = root
        root.title("BG Blur Fill")
        root.geometry("1200x780")
        root.minsize(1000, 680)
        root.configure(bg=BG)
        root.iconbitmap("favicon.ico")

        self.fast_help_window = None

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("TButton", background=PANEL_2, foreground=FG, padding=(10, 6))
        style.configure("Accent.TButton", background=ACCENT, foreground="white", padding=(10, 6))
        style.configure("TCheckbutton", background=BG, foreground=FG)
        style.configure("TRadiobutton", background=BG, foreground=FG)
        style.configure("TScale", background=BG)
        style.configure("TLabelframe", background=BG, foreground=FG)
        style.configure("TLabelframe.Label", background=BG, foreground=FG, font=("Segoe UI", 10, "bold"))
        style.map("TButton", background=[("active", ACCENT)], foreground=[("active", "white")])
        style.map("Accent.TButton", background=[("active", "#3c7ae0")])

        self.media_path = tk.StringVar(value="")
        self.aspect_choice = tk.StringVar(value="16:9 (landscape)")
        self.mode = tk.StringVar(value="letterbox")
        self.blur_bg = tk.BooleanVar(value=True)
        self.keep_audio = tk.BooleanVar(value=True)
        self.blur_strength = tk.IntVar(value=DEFAULT_BLUR)
        self.bg_brightness = tk.IntVar(value=DEFAULT_BRIGHTNESS)
        self.fast_preview = tk.BooleanVar(value=True)

        self.preview_image = None
        self._preview_source_bgr = None
        self._preview_canvas_ready = False
        self._preview_placeholder_mode = True

        self._build_ui()

        self.aspect_choice.trace_add("write", lambda *_: self.update_preview())
        self.mode.trace_add("write", lambda *_: self.update_preview())
        self.blur_bg.trace_add("write", lambda *_: self.update_preview())
        self.media_path.trace_add("write", lambda *_: self.update_preview())
        self.blur_strength.trace_add("write", lambda *_: self.update_preview())
        self.bg_brightness.trace_add("write", lambda *_: self.update_preview())
        self.fast_preview.trace_add("write", lambda *_: self.update_preview())

        self.preview_canvas.bind("<Configure>", self._on_preview_canvas_resize)
        self.root.after(50, self.update_preview)

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=14)
        main.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(main)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 14))
        left.configure(width=450)

        right = ttk.Frame(main)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        file_box = ttk.Labelframe(left, text="File")
        file_box.pack(fill=tk.X, pady=(0, 12))

        self.file_label = ttk.Label(file_box, text="No file selected", wraplength=380, foreground=MUTED)
        self.file_label.pack(fill=tk.X, padx=12, pady=(10, 8))

        file_actions = ttk.Frame(file_box)
        file_actions.pack(fill=tk.X, padx=12, pady=(0, 12))
        ttk.Button(file_actions, text="📂 Select File", command=self.select_media, style="Accent.TButton").pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

        output_box = ttk.Labelframe(left, text="Output settings")
        output_box.pack(fill=tk.X, pady=(0, 12))

        aspect_row = self._row(output_box)
        ttk.Label(aspect_row, text="Aspect / Size:").pack(side=tk.LEFT)
        aspect_menu = ttk.OptionMenu(aspect_row, self.aspect_choice, self.aspect_choice.get(), *ASPECT_PRESETS.keys())
        aspect_menu.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))

        mode_row = self._row(output_box)
        ttk.Label(mode_row, text="Mode:").pack(side=tk.LEFT)
        mode_inner = ttk.Frame(mode_row)
        mode_inner.pack(side=tk.RIGHT, fill=tk.X, expand=True)
        ttk.Radiobutton(mode_inner, text="Stretch to fit", variable=self.mode, value="resize").pack(side=tk.LEFT, padx=(0, 12))
        ttk.Radiobutton(mode_inner, text="Keep aspect (letterbox)", variable=self.mode, value="letterbox").pack(side=tk.LEFT)

        effect_box = ttk.Labelframe(left, text="Effects")
        effect_box.pack(fill=tk.X, pady=(0, 12))

        blur_row = self._row(effect_box)
        ttk.Label(blur_row, text="Blur strength: ").pack(side=tk.LEFT)
        blur_control = ttk.Frame(blur_row)
        blur_control.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))
        blur_scale = ttk.Scale(blur_control, from_=0, to=100, orient="horizontal", variable=self.blur_strength)
        blur_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.blur_strength_spin = tk.Spinbox(
            blur_control,
            from_=0,
            to=100,
            textvariable=self.blur_strength,
            width=6,
            bg=PANEL,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )
        self.blur_strength_spin.pack(side=tk.LEFT, padx=(8, 8))
        ttk.Button(blur_control, text="↺", width=3, command=self.reset_blur_strength).pack(side=tk.LEFT)

        brightness_row = self._row(effect_box)
        ttk.Label(brightness_row, text="Blur brightness:").pack(side=tk.LEFT)
        brightness_control = ttk.Frame(brightness_row)
        brightness_control.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))
        brightness_scale = ttk.Scale(brightness_control, from_=-100, to=100, orient="horizontal", variable=self.bg_brightness)
        brightness_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.bg_brightness_spin = tk.Spinbox(
            brightness_control,
            from_=-100,
            to=100,
            textvariable=self.bg_brightness,
            width=6,
            bg=PANEL,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )
        self.bg_brightness_spin.pack(side=tk.LEFT, padx=(8, 8))
        ttk.Button(brightness_control, text="↺", width=3, command=self.reset_bg_brightness).pack(side=tk.LEFT)

        ttk.Checkbutton(effect_box, text="Use blurred background for letterbox", variable=self.blur_bg).pack(anchor="w", padx=12, pady=(4, 2))
        ttk.Checkbutton(effect_box, text="Keep original audio", variable=self.keep_audio).pack(anchor="w", padx=12, pady=(0, 10))

        preview_box = ttk.Labelframe(right, text="Preview")
        preview_box.pack(fill=tk.BOTH, expand=True)

        preview_top = ttk.Frame(preview_box)
        preview_top.pack(fill=tk.X, padx=12, pady=(10, 6))

        ttk.Label(preview_top, text="Single frame preview").pack(side=tk.LEFT)
        preview_tools = ttk.Frame(preview_top)
        preview_tools.pack(side=tk.RIGHT)

        ttk.Checkbutton(preview_tools, text="Fast preview", variable=self.fast_preview).pack(side=tk.LEFT, padx=(0, 8))
        self.info_btn = self._create_circle_info_button(preview_tools, command=self._show_fast_preview_help)
        self.info_btn.pack(side=tk.LEFT)

        self.preview_canvas = tk.Canvas(
            preview_box,
            width=PREVIEW_MAX_W,
            height=PREVIEW_MAX_HEIGHT,
            bg="black",
            highlightthickness=0,
        )
        self.preview_canvas.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))

        self.config_summary = tk.Text(
            preview_box,
            width=48,
            height=7,
            wrap="word",
            bg=PANEL,
            fg=FG,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            padx=10,
            pady=8,
        )
        self.config_summary.pack(fill=tk.X, padx=12, pady=(0, 12))
        self.config_summary.configure(state="disabled")

        actions_box = ttk.Labelframe(left, text="Actions")
        actions_box.pack(fill=tk.X, pady=(0, 12))

        actions = ttk.Frame(actions_box)
        actions.pack(fill=tk.X, padx=12, pady=12)

        ttk.Button(actions, text="💾 Save output", command=self.on_save, style="Accent.TButton").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(actions, text="📁 Open folder", command=self.open_folder).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        ttk.Button(actions, text="🔄 Refresh Preview", command=self.update_preview).pack(side=tk.LEFT, fill=tk.X, expand=True)

        status_box = ttk.Labelframe(left, text="Status")
        status_box.pack(fill=tk.X)

        status_inner = ttk.Frame(status_box)
        status_inner.pack(fill=tk.X, padx=12, pady=12)

        self.progress = ttk.Progressbar(status_inner, orient="horizontal", mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status_inner, textvariable=self.status_var, foreground=ACCENT).pack(anchor="w", pady=(8, 0))

    def _row(self, parent):
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, padx=12, pady=8)
        return row

    def _create_circle_info_button(self, parent, command):
        canvas = tk.Canvas(parent, width=30, height=30, bg=BG, highlightthickness=0, bd=0, cursor="hand2")
        oval = canvas.create_oval(3, 3, 27, 27, fill=ACCENT, outline=ACCENT)
        canvas.create_text(15, 15, text="?", fill="white", font=("Segoe UI", 11, "bold"))

        def on_enter(_):
            canvas.itemconfig(oval, fill="#3c7ae0", outline="#3c7ae0")

        def on_leave(_):
            canvas.itemconfig(oval, fill=ACCENT, outline=ACCENT)

        def on_click(_):
            command()
            return "break"

        canvas.bind("<Enter>", on_enter)
        canvas.bind("<Leave>", on_leave)
        canvas.bind("<Button-1>", on_click)
        return canvas

    def _close_fast_help(self):
        win = self.fast_help_window
        self.fast_help_window = None
        if win is not None:
            try:
                win.grab_release()
            except Exception:
                pass
            try:
                win.destroy()
            except Exception:
                pass

    def _show_fast_preview_help(self):
        text = (
            "Fast preview reduces lag while adjusting settings.\n\n"
            "The preview is approximate and may use a smaller working size, "
            "but the saved output will still match the selected settings."
        )
        try:
            if self.fast_help_window is not None and self.fast_help_window.winfo_exists():
                self.fast_help_window.lift()
                self.fast_help_window.focus_force()
                return

            win = tk.Toplevel(self.root)
            self.fast_help_window = win
            win.title("Fast preview help")
            win.transient(self.root)
            win.configure(bg=BG)
            win.resizable(False, False)
            win.protocol("WM_DELETE_WINDOW", self._close_fast_help)
            win.bind("<Escape>", lambda _e: self._close_fast_help())

            frame = ttk.Frame(win, padding=12)
            frame.pack(fill=tk.BOTH, expand=True)

            ttk.Label(frame, text=text, justify="left", wraplength=380).pack(anchor="w")
            ttk.Button(frame, text="✖ Close", command=self._close_fast_help).pack(anchor="e", pady=(12, 0))

            win.update_idletasks()
            self._position_popup_inside_root(win, width=430, height=170, anchor_widget=self.info_btn)
            win.deiconify()
            win.lift()
            win.wait_visibility()
            win.grab_set()
            win.focus_force()
        except Exception:
            messagebox.showinfo("Fast preview", text)

    def _position_popup_inside_root(self, win, width=430, height=170, anchor_widget=None):
        self.root.update_idletasks()
        win.update_idletasks()

        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()

        x = root_x + max(12, (root_w - width) // 2)
        y = root_y + max(12, (root_h - height) // 2)

        if anchor_widget is not None:
            try:
                ax = anchor_widget.winfo_rootx() - root_x
                ay = anchor_widget.winfo_rooty() - root_y
                aw = anchor_widget.winfo_width()
                ah = anchor_widget.winfo_height()
                x = root_x + ax - width + aw // 2
                y = root_y + ay + ah + 8
            except Exception:
                pass

        min_x = root_x + 12
        min_y = root_y + 12
        max_x = root_x + max(12, root_w - width - 12)
        max_y = root_y + max(12, root_h - height - 12)

        x = min(max(x, min_x), max_x)
        y = min(max(y, min_y), max_y)

        win.geometry(f"{width}x{height}+{x}+{y}")

    def reset_blur_strength(self):
        self.blur_strength.set(DEFAULT_BLUR)

    def reset_bg_brightness(self):
        self.bg_brightness.set(DEFAULT_BRIGHTNESS)

    def select_media(self):
        filetypes = [
            ("Image and Video files", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp *.mp4 *.mov *.mkv *.avi *.webm"),
            ("Image files", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp"),
            ("Video files", "*.mp4 *.mov *.mkv *.avi *.webm"),
            ("All files", "*.*"),
        ]
        path = filedialog.askopenfilename(title="Select image or video file", filetypes=filetypes)
        if path:
            self.media_path.set(path)
            self.file_label.configure(text=path, foreground=FG)
            self.status_var.set(f"File selected: {os.path.basename(path)}")

    def open_folder(self):
        p = self.media_path.get()
        if os.path.isfile(p):
            folder = os.path.dirname(p)
            try:
                if os.name == "nt":
                    os.startfile(folder)
                elif os.name == "posix":
                    os.system(f'xdg-open "{folder}"')
                else:
                    messagebox.showinfo("Open folder", folder)
            except Exception as e:
                messagebox.showerror("Error", str(e))
        else:
            messagebox.showinfo("No file", "No valid file selected yet.")

    def on_save(self):
        src = self.media_path.get()
        if not os.path.isfile(src):
            messagebox.showwarning("No file", "Please select a valid image or video file first.")
            return

        ext = os.path.splitext(src)[1].lower()
        is_image = ext in IMAGE_EXTS

        if is_image:
            out_path = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[("PNG image", "*.png"), ("JPEG image", "*.jpg;*.jpeg"), ("All files", "*.*")],
                title="Save processed image as...",
            )
            if not out_path:
                return
            self.status_var.set("Processing image...")
            self.progress["value"] = 0
            self.root.update_idletasks()
            thread = threading.Thread(target=self._process_and_save_image, args=(src, out_path), daemon=True)
            thread.start()
        else:
            out_path = filedialog.asksaveasfilename(
                defaultextension=".mp4",
                filetypes=[("MP4 video", "*.mp4")],
                title="Save processed video as...",
            )
            if not out_path:
                return
            self.status_var.set("Processing video...")
            self.progress["value"] = 0
            self.root.update_idletasks()
            thread = threading.Thread(target=self._process_and_save, args=(src, out_path), daemon=True)
            thread.start()

    def _update_progress_safe(self, percent, text=None):
        def _():
            try:
                self.progress["value"] = percent
                if text is not None:
                    self.status_var.set(text)
            except Exception:
                pass

        self.root.after(1, _)

    def _show_placeholder(self, text="Please select your file"):
        self.preview_canvas.delete("all")
        w = max(1, self.preview_canvas.winfo_width())
        h = max(1, self.preview_canvas.winfo_height())
        self.preview_canvas.create_rectangle(0, 0, w, h, fill="black", outline="")
        self.preview_canvas.create_text(
            w // 2,
            h // 2 - 20,
            text=text,
            fill=PLACEHOLDER,
            font=("Segoe UI", 24, "bold"),
            justify="center",
            anchor="center",
        )
        self.preview_canvas.create_text(
            w // 2,
            h // 2 + 18,
            text="Supported: images and videos",
            fill=PLACEHOLDER_SUB,
            font=("Segoe UI", 12, "bold"),
            justify="center",
            anchor="center",
        )
        self._update_config_summary()

    def _on_preview_canvas_resize(self, _event):
        self._render_preview()

    def _render_preview(self):
        if self._preview_placeholder_mode or self._preview_source_bgr is None:
            self._show_placeholder("Please select your file")
            return

        try:
            canvas_w = max(1, self.preview_canvas.winfo_width())
            canvas_h = max(1, self.preview_canvas.winfo_height())
            frame = self._preview_source_bgr
            fh, fw = frame.shape[:2]
            scale = min(canvas_w / fw, canvas_h / fh)
            disp_w = max(1, int(fw * scale))
            disp_h = max(1, int(fh * scale))
            resized = cv2.resize(frame, (disp_w, disp_h), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
            im = Image.fromarray(cv2.cvtColor(resized, cv2.COLOR_BGR2RGB))
            self.preview_image = ImageTk.PhotoImage(im)
            self.preview_canvas.delete("all")
            self.preview_canvas.create_rectangle(0, 0, canvas_w, canvas_h, fill=PANEL, outline="")
            x = (canvas_w - disp_w) // 2
            y = (canvas_h - disp_h) // 2
            self.preview_canvas.create_image(x, y, anchor="nw", image=self.preview_image)
        except Exception:
            self.preview_canvas.delete("all")
            self._show_placeholder("Please select your file")

    def update_preview(self):
        src = self.media_path.get()
        if not os.path.isfile(src):
            self._preview_source_bgr = None
            self._preview_placeholder_mode = True
            self._render_preview()
            return

        try:
            ext = os.path.splitext(src)[1].lower()
            tW, tH = ASPECT_PRESETS[self.aspect_choice.get()]
            mode = self.mode.get()
            use_blur = self.blur_bg.get()
            blur_strength = self.blur_strength.get()
            bg_brightness = int(self.bg_brightness.get())
            fast = self.fast_preview.get()

            if ext in IMAGE_EXTS:
                pil = Image.open(src).convert("RGB")
                frame = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
            else:
                cap = cv2.VideoCapture(src)
                total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                if total > 0:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, total // 2)
                else:
                    cap.set(cv2.CAP_PROP_POS_MSEC, 1000)
                ret, frame = cap.read()
                cap.release()
                if not ret or frame is None:
                    raise RuntimeError("Failed to read a frame for preview")

            if fast:
                comp_w = min(PREVIEW_MAX_W, tW)
                comp_h = min(PREVIEW_MAX_HEIGHT, tH)
                scale_factor = comp_w / max(1, tW)
                eff_blur = max(1, int(blur_strength * scale_factor)) if blur_strength > 0 else 0
            else:
                comp_w = tW
                comp_h = tH
                eff_blur = blur_strength

            self._preview_source_bgr = self._make_preview_frame(
                frame, comp_w, comp_h, mode, use_blur, eff_blur, bg_brightness
            )
            self._preview_placeholder_mode = False
            self._render_preview()
            self._update_config_summary()
        except Exception:
            self._preview_source_bgr = None
            self._preview_placeholder_mode = True
            self.preview_canvas.delete("all")
            with open(ERROR_LOG, "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
            self.status_var.set("Preview error — see " + ERROR_LOG)
            self._show_placeholder("Please select your file")

    def _update_config_summary(self):
        summary = (
            f"Aspect: {self.aspect_choice.get()}\n"
            f"Mode: {self.mode.get()}\n"
            f"Blur background: {self.blur_bg.get()}\n"
            f"Blur strength: {self.blur_strength.get()}\n"
            f"Blur brightness: {self.bg_brightness.get()}\n"
            f"Fast preview: {self.fast_preview.get()}\n"
            f"Keep audio: {self.keep_audio.get()}"
        )
        try:
            self.config_summary.configure(state="normal")
            self.config_summary.delete("1.0", tk.END)
            self.config_summary.insert(tk.END, summary)
            self.config_summary.configure(state="disabled")
        except Exception:
            pass

    def _make_preview_frame(self, frame, tW, tH, mode, use_blur, blur_strength, bg_brightness):
        h, w = frame.shape[:2]
        if mode == "resize":
            resized = cv2.resize(frame, (tW, tH), interpolation=cv2.INTER_LINEAR)
            out = cv2.resize(resized, (min(tW, PREVIEW_MAX_W), min(tH, PREVIEW_MAX_HEIGHT)), interpolation=cv2.INTER_LINEAR)
            return out

        scale = min(tW / w, tH / h)
        new_w = int(math.floor(w * scale))
        new_h = int(math.floor(h * scale))
        bg = cv2.resize(frame, (tW, tH), interpolation=cv2.INTER_LINEAR)

        if use_blur and blur_strength > 0:
            sigma = max(1, int(blur_strength))
            bg = cv2.GaussianBlur(bg, (0, 0), sigmaX=sigma, sigmaY=sigma)
            hsv = cv2.cvtColor(bg, cv2.COLOR_BGR2HSV)
            hsv[:, :, 1] = (hsv[:, :, 1].astype(np.float32) * 0.6).astype(np.uint8)
            bg = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
            if bg_brightness != 0:
                bg = cv2.convertScaleAbs(bg, alpha=1.0, beta=bg_brightness)

        fg = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        x_off = (tW - new_w) // 2
        y_off = (tH - new_h) // 2
        bg[y_off:y_off + new_h, x_off:x_off + new_w] = fg
        out = cv2.resize(bg, (min(tW, PREVIEW_MAX_W), min(tH, PREVIEW_MAX_HEIGHT)), interpolation=cv2.INTER_LINEAR)
        return out

    def _process_and_save_image(self, image_path, out_path):
        try:
            pil = Image.open(image_path).convert("RGB")
            frame = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
            tW, tH = ASPECT_PRESETS[self.aspect_choice.get()]
            mode = self.mode.get()
            use_blur = self.blur_bg.get()
            blur_strength = self.blur_strength.get()
            bg_brightness = int(self.bg_brightness.get())

            if mode == "resize":
                out = cv2.resize(frame, (tW, tH), interpolation=cv2.INTER_LINEAR)
            else:
                h, w = frame.shape[:2]
                scale = min(tW / w, tH / h)
                new_w = int(math.floor(w * scale))
                new_h = int(math.floor(h * scale))
                bg = cv2.resize(frame, (tW, tH), interpolation=cv2.INTER_LINEAR)
                if use_blur and blur_strength > 0:
                    bg = cv2.GaussianBlur(bg, (0, 0), sigmaX=blur_strength, sigmaY=blur_strength)
                    hsv = cv2.cvtColor(bg, cv2.COLOR_BGR2HSV)
                    hsv[:, :, 1] = (hsv[:, :, 1].astype(np.float32) * 0.6).astype(np.uint8)
                    bg = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
                    if bg_brightness != 0:
                        bg = cv2.convertScaleAbs(bg, alpha=1.0, beta=bg_brightness)
                fg = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
                x_off = (tW - new_w) // 2
                y_off = (tH - new_h) // 2
                bg[y_off:y_off + new_h, x_off:x_off + new_w] = fg
                out = bg

            ok = cv2.imwrite(out_path, out)
            if not ok:
                raise RuntimeError("Failed to write output image")

            self._update_progress_safe(100, "Done")
            messagebox.showinfo("Finished", "Saved processed image to: " + out_path)
        except Exception:
            tb = traceback.format_exc()
            with open(ERROR_LOG, "w", encoding="utf-8") as f:
                f.write(tb)
            messagebox.showerror("Processing error", f"An error occurred. Details written to: {ERROR_LOG}")
        finally:
            self._update_progress_safe(0, "Ready")

    def _process_and_save(self, video_path, out_path):
        cap = None
        writer = None
        tmp_video = None
        tmp_audio = None
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise RuntimeError("Failed to open input video")

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            tW, tH = ASPECT_PRESETS[self.aspect_choice.get()]
            mode = self.mode.get()
            use_blur = self.blur_bg.get()
            blur_strength = self.blur_strength.get()
            bg_brightness = int(self.bg_brightness.get())
            keep_audio = self.keep_audio.get()
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")

            tmp_fd, tmp_video = tempfile.mkstemp(suffix=".mp4")
            os.close(tmp_fd)
            writer = cv2.VideoWriter(tmp_video, fourcc, fps, (tW, tH))
            if not writer.isOpened():
                raise RuntimeError("Failed to open output writer")

            frame_idx = 0

            if mode == "resize":
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    resized = cv2.resize(frame, (tW, tH), interpolation=cv2.INTER_LINEAR)
                    writer.write(resized)
                    frame_idx += 1
                    if total_frames:
                        pct = int(frame_idx / total_frames * 100)
                        self._update_progress_safe(pct, f"Processing frame {frame_idx}/{total_frames} ({pct}%)")
            else:
                scale = min(tW / w, tH / h)
                new_w = int(math.floor(w * scale))
                new_h = int(math.floor(h * scale))
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    bg = cv2.resize(frame, (tW, tH), interpolation=cv2.INTER_LINEAR)
                    if use_blur and blur_strength > 0:
                        bg = cv2.GaussianBlur(bg, (0, 0), sigmaX=blur_strength, sigmaY=blur_strength)
                        hsv = cv2.cvtColor(bg, cv2.COLOR_BGR2HSV)
                        hsv[:, :, 1] = (hsv[:, :, 1].astype(np.float32) * 0.6).astype(np.uint8)
                        bg = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
                        if bg_brightness != 0:
                            bg = cv2.convertScaleAbs(bg, alpha=1.0, beta=bg_brightness)
                    fg = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
                    x_off = (tW - new_w) // 2
                    y_off = (tH - new_h) // 2
                    bg[y_off:y_off + new_h, x_off:x_off + new_w] = fg
                    writer.write(bg)
                    frame_idx += 1
                    if total_frames:
                        pct = int(frame_idx / total_frames * 100)
                        self._update_progress_safe(pct, f"Processing frame {frame_idx}/{total_frames} ({pct}%)")

            writer.release()
            writer = None
            cap.release()
            cap = None
            self._update_progress_safe(100, "Finalizing output...")

            if keep_audio:
                tmp_audio = tempfile.mktemp(suffix=".aac")
                ffmpeg = self._ffmpeg_exe()
                if not ffmpeg:
                    raise RuntimeError("ffmpeg not found on PATH; required to copy audio")
                cmd_extract = [ffmpeg, "-y", "-i", video_path, "-vn", "-acodec", "copy", tmp_audio]
                subprocess.check_call(cmd_extract)
                cmd_mux = [ffmpeg, "-y", "-i", tmp_video, "-i", tmp_audio, "-c", "copy", out_path]
                subprocess.check_call(cmd_mux)
            else:
                os.replace(tmp_video, out_path)
                tmp_video = None

            self._update_progress_safe(100, "Done")
            messagebox.showinfo("Finished", "Saved processed video to: " + out_path)
        except Exception:
            tb = traceback.format_exc()
            with open(ERROR_LOG, "w", encoding="utf-8") as f:
                f.write(tb)
            messagebox.showerror("Processing error", f"An error occurred. Details written to: {ERROR_LOG}")
        finally:
            try:
                if cap is not None:
                    cap.release()
            except Exception:
                pass
            try:
                if writer is not None:
                    writer.release()
            except Exception:
                pass
            try:
                if tmp_video and os.path.exists(tmp_video):
                    os.remove(tmp_video)
            except Exception:
                pass
            try:
                if tmp_audio and os.path.exists(tmp_audio):
                    os.remove(tmp_audio)
            except Exception:
                pass
            self._update_progress_safe(0, "Ready")

    def _ffmpeg_exe(self):
        for n in ["ffmpeg"]:
            try:
                subprocess.check_call([n, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return n
            except Exception:
                continue
        return None


if __name__ == "__main__":
    root = tk.Tk()
    app = VideoProcessorApp(root)
    try:
        root.state("zoomed")
    except Exception:
        pass
    root.mainloop()