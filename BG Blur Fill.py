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

ERROR_LOG = os.path.join(os.path.dirname(__file__), 'video_processor_error.txt')
PREVIEW_MAX_W = 960
PREVIEW_MAX_HEIGHT = 400
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp')
VIDEO_EXTS = ('.mp4', '.mov', '.mkv', '.avi', '.webm')

BG = '#1f2326'
PANEL = '#262b2e'
FG = '#e6eef6'
ACCENT = '#4f8ef7'
MUTED = '#9aa5b1'

class VideoProcessorApp:
    def __init__(self, root):
        self.root = root
        root.title("OpenCV Video/Image Resizer / Letterbox Tool")
        root.geometry("1100x700")
        root.minsize(900, 600)
        root.configure(bg=BG)

        style = ttk.Style()
        try:
            style.theme_use('clam')
        except Exception:
            pass
        style.configure('TFrame', background=BG)
        style.configure('TLabel', background=BG, foreground=FG)
        style.configure('TButton', background=PANEL, foreground=FG)
        style.configure('TCheckbutton', background=BG, foreground=FG)
        style.configure('TRadiobutton', background=BG, foreground=FG)
        style.configure('TScale', background=BG)
        style.map('TButton', background=[('active', ACCENT)])

        self.media_path = tk.StringVar(value="(no file selected)")
        self.aspect_choice = tk.StringVar(value="16:9 (landscape)")
        self.mode = tk.StringVar(value="letterbox")
        self.blur_bg = tk.BooleanVar(value=True)
        self.keep_audio = tk.BooleanVar(value=True)
        self.blur_strength = tk.IntVar(value=25)
        self.bg_brightness = tk.IntVar(value=0)
        self.fast_preview = tk.BooleanVar(value=True)

        self.preview_image = None
        self._build_ui()
        self.aspect_choice.trace_add('write', lambda *_: self.update_preview())
        self.mode.trace_add('write', lambda *_: self.update_preview())
        self.blur_bg.trace_add('write', lambda *_: self.update_preview())
        self.media_path.trace_add('write', lambda *_: self.update_preview())
        self.blur_strength.trace_add('write', lambda *_: self.update_preview())
        self.bg_brightness.trace_add('write', lambda *_: self.update_preview())
        self.fast_preview.trace_add('write', lambda *_: self.update_preview())

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(main)
        controls.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        controls.config(width=420)

        preview_panel = ttk.Frame(main)
        preview_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        def ctrl_row(parent, pady=(6,6)):
            r = ttk.Frame(parent)
            r.pack(fill=tk.X, pady=pady)
            return r

        row0 = ctrl_row(controls, pady=(0,8))
        ttk.Label(row0, text="Selected file:").pack(side=tk.LEFT)
        ttk.Label(row0, textvariable=self.media_path, wraplength=280).pack(side=tk.LEFT, padx=8)
        ttk.Button(row0, text="Select File", command=self.select_media).pack(side=tk.RIGHT)

        row1 = ctrl_row(controls)
        ttk.Label(row1, text="Aspect / Size:").pack(side=tk.LEFT)
        aspect_menu = ttk.OptionMenu(row1, self.aspect_choice, self.aspect_choice.get(), *ASPECT_PRESETS.keys())
        aspect_menu.pack(side=tk.LEFT, padx=8)

        row2 = ctrl_row(controls)
        ttk.Label(row2, text="Mode:").pack(side=tk.LEFT)
        ttk.Radiobutton(row2, text="Stretch to fit", variable=self.mode, value="resize").pack(side=tk.LEFT, padx=6)
        ttk.Radiobutton(row2, text="Keep aspect (letterbox)", variable=self.mode, value="letterbox").pack(side=tk.LEFT, padx=6)

        row3 = ctrl_row(controls)
        ttk.Checkbutton(row3, text="Use blurred background for letterbox", variable=self.blur_bg).pack(side=tk.LEFT)

        row4 = ctrl_row(controls)
        ttk.Checkbutton(row4, text="Keep original audio (requires ffmpeg)", variable=self.keep_audio).pack(side=tk.LEFT)

        row5 = ctrl_row(controls)
        ttk.Label(row5, text="Blur strength:").pack(side=tk.LEFT)
        blur_scale = ttk.Scale(row5, from_=0, to=100, orient='horizontal', variable=self.blur_strength)
        blur_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        self.blur_strength_spin = tk.Spinbox(row5, from_=0, to=100, textvariable=self.blur_strength, width=5,
                                            bg=PANEL, fg=FG, insertbackground=FG)
        self.blur_strength_spin.pack(side=tk.LEFT)

        row6 = ctrl_row(controls)
        ttk.Label(row6, text="Background brightness:").pack(side=tk.LEFT)
        bg_brightness_scale = ttk.Scale(row6, from_=-100, to=100, orient='horizontal', variable=self.bg_brightness)
        bg_brightness_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        self.bg_brightness_spin = tk.Spinbox(row6, from_=-100, to=100, textvariable=self.bg_brightness, width=6,
                                            bg=PANEL, fg=FG, insertbackground=FG)
        self.bg_brightness_spin.pack(side=tk.LEFT)

        row7 = ctrl_row(controls)
        chk = ttk.Checkbutton(row7, text="Fast preview", variable=self.fast_preview)
        chk.pack(side=tk.LEFT)
        qbtn = ttk.Button(row7, text='?', width=3, command=self._show_fast_preview_help)
        qbtn.pack(side=tk.LEFT, padx=(6,0))

        acts = ttk.Frame(controls)
        acts.pack(fill=tk.X, pady=(12,0))
        ttk.Button(acts, text="Save output", command=self.on_save).pack(side=tk.LEFT)
        ttk.Button(acts, text="Open folder", command=self.open_folder).pack(side=tk.LEFT, padx=8)
        ttk.Button(acts, text="Refresh Preview", command=self.update_preview).pack(side=tk.LEFT, padx=8)

        prog_row = ttk.Frame(controls)
        prog_row.pack(fill=tk.X, pady=(12,0))
        ttk.Label(prog_row, text="Progress:").pack(side=tk.LEFT)
        self.progress = ttk.Progressbar(prog_row, orient='horizontal', mode='determinate')
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        self.progress['value'] = 0
        self.progress['maximum'] = 100
        self.status_var = tk.StringVar(value="Ready")
        status_label = ttk.Label(controls, textvariable=self.status_var, foreground=ACCENT)
        status_label.pack(fill=tk.X, pady=(8,0))

        phead = ttk.Frame(preview_panel)
        phead.pack(fill=tk.X)
        ttk.Label(phead, text="Preview (single frame)").pack(side=tk.LEFT)

        self.preview_canvas = tk.Canvas(preview_panel, width=PREVIEW_MAX_W, height=PREVIEW_MAX_HEIGHT, bg='black', highlightthickness=0)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True, pady=8)

        self.config_summary = tk.Text(preview_panel, width=48, height=6, wrap='word', bg=PANEL, fg=FG, relief='flat')
        self.config_summary.pack(fill=tk.X)
        self.config_summary.configure(state='disabled')

    def _show_fast_preview_help(self):
        text = ("Fast preview — enable this to reduce lag while adjusting settings. "
                "The preview image is approximate (may be a different size), but the saved output will match the selected settings.")
        try:
            win = tk.Toplevel(self.root)
            win.title('Fast preview help')
            win.transient(self.root)
            win.configure(bg=BG)
            win.resizable(False, False)
            x = self.root.winfo_pointerx()
            y = self.root.winfo_pointery()
            win.geometry(f'+{x+10}+{y+10}')
            lbl = tk.Label(win, text=text, justify='left', wraplength=360, bg=PANEL, fg=FG, padx=12, pady=8)
            lbl.pack()
            btn = ttk.Button(win, text='Close', command=win.destroy)
            btn.pack(pady=(0,8))
        except Exception:
            messagebox.showinfo('Fast preview', text)

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
            self.status_var.set("File selected: %s" % os.path.basename(path))

    def open_folder(self):
        p = self.media_path.get()
        if os.path.isfile(p):
            folder = os.path.dirname(p)
            try:
                if os.name == 'nt':
                    os.startfile(folder)
                elif os.name == 'posix':
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
            out_path = filedialog.asksaveasfilename(defaultextension='.png', filetypes=[('PNG image','*.png'),('JPEG image','*.jpg;*.jpeg'),('All files','*.*')], title='Save processed image as...')
            if not out_path:
                return
            self.status_var.set('Processing image...')
            self.progress['value'] = 0
            self.root.update_idletasks()
            thread = threading.Thread(target=self._process_and_save_image, args=(src, out_path), daemon=True)
            thread.start()
        else:
            out_path = filedialog.asksaveasfilename(defaultextension='.mp4', filetypes=[('MP4 video','*.mp4')], title='Save processed video as...')
            if not out_path:
                return
            self.status_var.set('Processing video...')
            self.progress['value'] = 0
            self.root.update_idletasks()
            thread = threading.Thread(target=self._process_and_save, args=(src, out_path), daemon=True)
            thread.start()

    def _update_progress_safe(self, percent, text=None):
        def _():
            try:
                self.progress['value'] = percent
                if text is not None:
                    self.status_var.set(text)
            except Exception:
                pass
        self.root.after(1, _)

    def update_preview(self):
        src = self.media_path.get()
        if not os.path.isfile(src):
            self.preview_canvas.delete('all')
            self._update_config_summary()
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
                pil = Image.open(src).convert('RGB')
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
                    raise RuntimeError('Failed to read a frame for preview')

            if fast:
                comp_w = min(PREVIEW_MAX_W, tW)
                comp_h = min(PREVIEW_MAX_HEIGHT, tH)
                scale_factor = comp_w / max(1, tW)
                eff_blur = max(1, int(blur_strength * scale_factor)) if blur_strength > 0 else 0
            else:
                comp_w = tW
                comp_h = tH
                eff_blur = blur_strength

            preview = self._make_preview_frame(frame, comp_w, comp_h, mode, use_blur, eff_blur, bg_brightness)
            im = Image.fromarray(cv2.cvtColor(preview, cv2.COLOR_BGR2RGB))
            display_w = min(PREVIEW_MAX_W, tW)
            display_h = max(1, int(display_w * (tH / tW)))
            if display_h > PREVIEW_MAX_HEIGHT:
                display_h = PREVIEW_MAX_HEIGHT
                display_w = max(1, int(display_h * (tW / tH)))
            im = im.resize((display_w, display_h), Image.LANCZOS)
            self.preview_image = ImageTk.PhotoImage(im)
            self.preview_canvas.config(width=display_w, height=display_h, bg=PANEL)
            self.preview_canvas.delete('all')
            self.preview_canvas.create_image(0, 0, anchor='nw', image=self.preview_image)
            self._update_config_summary()
        except Exception:
            self.preview_canvas.delete('all')
            with open(ERROR_LOG, 'w', encoding='utf-8') as f:
                f.write(traceback.format_exc())
            self.status_var.set('Preview error — see ' + ERROR_LOG)

    def _update_config_summary(self):
        summary = (
            f"Aspect: {self.aspect_choice.get()}\n"
            f"Mode: {self.mode.get()}\n"
            f"Blur bg: {self.blur_bg.get()}\n"
            f"Blur strength: {self.blur_strength.get()}\n"
            f"Background brightness: {self.bg_brightness.get()}\n"
            f"Fast preview: {self.fast_preview.get()}\n"
            f"Keep audio: {self.keep_audio.get()}"
        )
        try:
            self.config_summary.configure(state='normal')
            self.config_summary.delete('1.0', tk.END)
            self.config_summary.insert(tk.END, summary)
            self.config_summary.configure(state='disabled')
        except Exception:
            pass

    def _make_preview_frame(self, frame, tW, tH, mode, use_blur, blur_strength, bg_brightness):
        h, w = frame.shape[:2]
        if mode == 'resize':
            resized = cv2.resize(frame, (tW, tH), interpolation=cv2.INTER_LINEAR)
            out = resized
            out = cv2.resize(out, (min(tW, PREVIEW_MAX_W), min(tH, PREVIEW_MAX_HEIGHT)), interpolation=cv2.INTER_LINEAR)
            return out
        else:
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
            pil = Image.open(image_path).convert('RGB')
            frame = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
            tW, tH = ASPECT_PRESETS[self.aspect_choice.get()]
            mode = self.mode.get()
            use_blur = self.blur_bg.get()
            blur_strength = self.blur_strength.get()
            bg_brightness = int(self.bg_brightness.get())
            if mode == 'resize':
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
                raise RuntimeError('Failed to write output image')
            self._update_progress_safe(100, 'Done')
            messagebox.showinfo('Finished', 'Saved processed image to: ' + out_path)
        except Exception:
            tb = traceback.format_exc()
            with open(ERROR_LOG, 'w', encoding='utf-8') as f:
                f.write(tb)
            messagebox.showerror('Processing error', f'An error occurred. Details written to: {ERROR_LOG}')
        finally:
            self._update_progress_safe(0, 'Ready')

    def _process_and_save(self, video_path, out_path):
        cap = None
        writer = None
        tmp_video = None
        tmp_audio = None
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise RuntimeError('Failed to open input video')
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
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            tmp_fd, tmp_video = tempfile.mkstemp(suffix='.mp4')
            os.close(tmp_fd)
            writer = cv2.VideoWriter(tmp_video, fourcc, fps, (tW, tH))
            if not writer.isOpened():
                raise RuntimeError('Failed to open output writer')
            frame_idx = 0
            if mode == 'resize':
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    resized = cv2.resize(frame, (tW, tH), interpolation=cv2.INTER_LINEAR)
                    writer.write(resized)
                    frame_idx += 1
                    if total_frames:
                        pct = int(frame_idx / total_frames * 100)
                        self._update_progress_safe(pct, f'Processing frame {frame_idx}/{total_frames} ({pct}%)')
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
                        self._update_progress_safe(pct, f'Processing frame {frame_idx}/{total_frames} ({pct}%)')
            writer.release(); writer = None
            cap.release(); cap = None
            self._update_progress_safe(100, 'Finalizing output...')
            if keep_audio:
                tmp_audio = tempfile.mktemp(suffix='.aac')
                ffmpeg = self._ffmpeg_exe()
                if not ffmpeg:
                    raise RuntimeError('ffmpeg not found on PATH; required to copy audio')
                cmd_extract = [ffmpeg, '-y', '-i', video_path, '-vn', '-acodec', 'copy', tmp_audio]
                subprocess.check_call(cmd_extract)
                cmd_mux = [ffmpeg, '-y', '-i', tmp_video, '-i', tmp_audio, '-c', 'copy', out_path]
                subprocess.check_call(cmd_mux)
            else:
                os.replace(tmp_video, out_path)
                tmp_video = None
            self._update_progress_safe(100, 'Done')
            messagebox.showinfo('Finished', 'Saved processed video to:' + out_path)
        except Exception:
            tb = traceback.format_exc()
            with open(ERROR_LOG, 'w', encoding='utf-8') as f:
                f.write(tb)
            messagebox.showerror('Processing error', f'An error occurred. Details written to: {ERROR_LOG}')
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
            self._update_progress_safe(0, 'Ready')

    def _ffmpeg_exe(self):
        names = ['ffmpeg']
        for n in names:
            try:
                subprocess.check_call([n, '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return n
            except Exception:
                continue
        return None

if __name__ == '__main__':
    root = tk.Tk()
    root.iconbitmap("favicon.ico")
    app = VideoProcessorApp(root)
    try:
        root.state('zoomed')
    except Exception:
        pass
    root.mainloop()
