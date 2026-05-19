import customtkinter as ctk
import threading
import subprocess
import json
import os
import re
import io
import sys
import shutil
import signal
from datetime import datetime
from tkinter import filedialog, messagebox

import requests
from PIL import Image

# ─── Config ──────────────────────────────────────────────────────────────────

APP_TITLE = "YouTube Downloader"
APP_SIZE = "1100x720"
DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def _find_ytdlp():
    """Find yt-dlp binary: bundled in project dir first, then system PATH."""
    app_dir = os.path.dirname(os.path.abspath(__file__))
    if sys.platform == "win32":
        local = os.path.join(app_dir, "yt-dlp.exe")
    else:
        local = os.path.join(app_dir, "yt-dlp")
    if os.path.isfile(local):
        return local
    found = shutil.which("yt-dlp")
    if found:
        return found
    return "yt-dlp"


YTDLP = _find_ytdlp()


def _hide_console():
    """Return startupinfo to hide console window on Windows."""
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return si
    return None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def fmt_duration(seconds):
    if not seconds:
        return "?"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


# ─── App ─────────────────────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(APP_SIZE)
        self.minsize(900, 600)

        self.video_info = None
        self.download_dir = DEFAULT_DOWNLOAD_DIR
        self.is_downloading = False
        self.process = None
        self.history: list[dict] = []
        self.fetch_timer = None

        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(0, weight=1)

        # Left panel
        left = ctk.CTkFrame(self, corner_radius=0)
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_columnconfigure(0, weight=1)

        self._build_url_bar(left)
        self._build_preview(left)
        self._build_download_section(left)
        self._build_history(left)

        # Right sidebar
        sidebar = ctk.CTkScrollableFrame(self, width=260, corner_radius=0)
        sidebar.grid(row=0, column=1, sticky="nsew")
        sidebar.grid_columnconfigure(0, weight=1)
        self._build_sidebar(sidebar)

    # -- URL bar --
    def _build_url_bar(self, parent):
        frame = ctk.CTkFrame(parent)
        frame.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        frame.grid_columnconfigure(0, weight=1)

        self.url_var = ctk.StringVar()
        self.url_var.trace_add("write", self._on_url_change)

        self.url_entry = ctk.CTkEntry(frame, placeholder_text="Paste a YouTube URL...", height=40)
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.url_entry.bind("<KeyRelease>", lambda e: self._fetch_info())
        self.url_entry.bind("<Return>", lambda e: self._fetch_info())

        paste_btn = ctk.CTkButton(frame, text="Paste", width=90, height=40, command=self._paste_url)
        paste_btn.grid(row=0, column=1)

        #fetch_btn = ctk.CTkButton(frame, text="Fetch", width=90, height=40,
        #                          fg_color="#2ecc71", hover_color="#27ae60", command=self._fetch_info)
        #fetch_btn.grid(row=0, column=2, padx=(8, 0))

    # -- Preview --
    def _build_preview(self, parent):
        self.preview_frame = ctk.CTkFrame(parent)
        self.preview_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=8)
        self.preview_frame.grid_columnconfigure(1, weight=1)

        self.thumb_label = ctk.CTkLabel(self.preview_frame, text="", width=240, height=135)
        self.thumb_label.grid(row=0, column=0, rowspan=3, padx=(8, 12), pady=8)

        self.title_label = ctk.CTkLabel(self.preview_frame, text="Waiting for video info...",
                                        font=ctk.CTkFont(size=15, weight="bold"),
                                        wraplength=450, anchor="w", justify="left")
        self.title_label.grid(row=0, column=1, sticky="w", pady=(8, 2))

        self.channel_label = ctk.CTkLabel(self.preview_frame, text="", anchor="w",
                                          text_color="gray")
        self.channel_label.grid(row=1, column=1, sticky="w")

        self.duration_label = ctk.CTkLabel(self.preview_frame, text="", anchor="w",
                                           text_color="gray")
        self.duration_label.grid(row=2, column=1, sticky="w", pady=(0, 8))

    # -- Download controls --
    def _build_download_section(self, parent):
        frame = ctk.CTkFrame(parent)
        frame.grid(row=2, column=0, sticky="ew", padx=16, pady=8)
        frame.grid_columnconfigure(0, weight=1)

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        btn_frame.grid_columnconfigure(0, weight=1)

        self.download_btn = ctk.CTkButton(btn_frame, text="Download", height=48,
                                          font=ctk.CTkFont(size=16, weight="bold"),
                                          fg_color="#e74c3c", hover_color="#c0392b",
                                          command=self._start_download)
        self.download_btn.grid(row=0, column=0, sticky="ew")

        self.cancel_btn = ctk.CTkButton(btn_frame, text="Cancel", height=48, width=100,
                                        font=ctk.CTkFont(size=14, weight="bold"),
                                        fg_color="#7f8c8d", hover_color="#636e72",
                                        state="disabled", command=self._cancel_download)
        self.cancel_btn.grid(row=0, column=1, sticky="e", padx=(8, 0))

        self.progress_bar = ctk.CTkProgressBar(frame)
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=12)
        self.progress_bar.set(0)

        self.status_label = ctk.CTkLabel(frame, text="Ready", anchor="w", text_color="gray")
        self.status_label.grid(row=2, column=0, sticky="w", padx=12, pady=(4, 12))

    # -- History --
    def _build_history(self, parent):
        lbl = ctk.CTkLabel(parent, text="Download History", font=ctk.CTkFont(size=13, weight="bold"), anchor="w")
        lbl.grid(row=3, column=0, sticky="w", padx=16, pady=(8, 2))

        self.history_frame = ctk.CTkScrollableFrame(parent, height=140)
        self.history_frame.grid(row=4, column=0, sticky="nsew", padx=16, pady=(0, 16))
        parent.grid_rowconfigure(4, weight=1)
        self.history_frame.grid_columnconfigure(0, weight=1)

        self.history_placeholder = ctk.CTkLabel(self.history_frame, text="No downloads yet.",
                                                text_color="gray")
        self.history_placeholder.grid(row=0, column=0, pady=8)

    # -- Sidebar --
    def _build_sidebar(self, parent):
        heading = ctk.CTkLabel(parent, text="Settings", font=ctk.CTkFont(size=16, weight="bold"))
        heading.grid(row=0, column=0, sticky="w", padx=12, pady=(12, 8))

        # Format toggle
        self._sb_label(parent, 1, "Format")
        self.format_var = ctk.StringVar(value="video")
        seg = ctk.CTkSegmentedButton(parent, values=["Video", "Audio"],
                                     command=self._on_format_toggle)
        seg.set("Video")
        seg.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))
        self.format_seg = seg

        # Video quality
        self._sb_label(parent, 3, "Video Quality")
        self.quality_var = ctk.StringVar(value="Best")
        self.quality_menu = ctk.CTkOptionMenu(parent, variable=self.quality_var,
                                              values=["Best", "2160p", "1440p", "1080p", "720p", "480p", "360p"])
        self.quality_menu.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 8))

        # Video format
        self._sb_label(parent, 5, "Video Format")
        self.vfmt_var = ctk.StringVar(value="mp4")
        self.vfmt_menu = ctk.CTkOptionMenu(parent, variable=self.vfmt_var,
                                           values=["mp4", "mkv", "webm"])
        self.vfmt_menu.grid(row=6, column=0, sticky="ew", padx=12, pady=(0, 8))

        # Audio format
        self._sb_label(parent, 7, "Audio Format")
        self.afmt_var = ctk.StringVar(value="mp3")
        self.afmt_menu = ctk.CTkOptionMenu(parent, variable=self.afmt_var,
                                           values=["mp3", "m4a", "wav", "flac", "ogg"])
        self.afmt_menu.grid(row=8, column=0, sticky="ew", padx=12, pady=(0, 8))

        # Audio quality
        self._sb_label(parent, 9, "Audio Quality")
        self.aquality_var = ctk.StringVar(value="320kbps")
        self.aquality_menu = ctk.CTkOptionMenu(parent, variable=self.aquality_var,
                                               values=["320kbps", "256kbps", "192kbps", "128kbps"])
        self.aquality_menu.grid(row=10, column=0, sticky="ew", padx=12, pady=(0, 8))

        # Subtitle toggle
        self._sb_label(parent, 11, "Subtitles")
        self.sub_var = ctk.BooleanVar(value=False)
        self.sub_switch = ctk.CTkSwitch(parent, text="Download subtitles", variable=self.sub_var,
                                        command=self._on_sub_toggle)
        self.sub_switch.grid(row=12, column=0, sticky="w", padx=12, pady=(0, 4))

        self.sub_lang_var = ctk.StringVar(value="en")
        self.sub_lang_menu = ctk.CTkOptionMenu(parent, variable=self.sub_lang_var,
                                               values=["en", "tr", "de", "fr", "es", "ar", "ja", "ko", "auto"])
        self.sub_lang_menu.grid(row=13, column=0, sticky="ew", padx=12, pady=(0, 8))
        self.sub_lang_menu.configure(state="disabled")

        self._sb_label(parent, 14, "Playlist")
        self.playlist_var = ctk.BooleanVar(value=False)
        self.playlist_switch = ctk.CTkSwitch(parent, text="Download whole playlist", variable=self.playlist_var, command=self._on_playlist_toggle)
        self.playlist_switch.grid(row=15, column=0, sticky="w", padx=12, pady=(0, 8))

        # Download location
        self._sb_label(parent, 16, "Download Location")
        self.dir_label = ctk.CTkLabel(parent, text=self._short_path(self.download_dir),
                                      anchor="w", wraplength=230, text_color="gray")
        self.dir_label.grid(row=17, column=0, sticky="w", padx=12)

        dir_btn = ctk.CTkButton(parent, text="Browse", width=120, command=self._pick_dir)
        dir_btn.grid(row=18, column=0, sticky="w", padx=12, pady=(4, 12))

        # Initial state
        self._toggle_audio_widgets(False)

    def _sb_label(self, parent, row, text):
        lbl = ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=13, weight="bold"), anchor="w")
        lbl.grid(row=row, column=0, sticky="w", padx=12, pady=(8, 2))

    # ── Sidebar callbacks ────────────────────────────────────────────────

    def _on_format_toggle(self, value):
        self._toggle_audio_widgets(value == "Audio")

    def _toggle_audio_widgets(self, audio_only):
        vid_state = "disabled" if audio_only else "normal"
        aud_state = "normal" if audio_only else "disabled"
        self.quality_menu.configure(state=vid_state)
        self.vfmt_menu.configure(state=vid_state)
        self.afmt_menu.configure(state=aud_state)
        self.aquality_menu.configure(state=aud_state)

    def _on_playlist_toggle(self):
        url = self.url_entry.get().strip()
        if url:
            self._fetch_info()

    def _on_sub_toggle(self):
        self.sub_lang_menu.configure(state="normal" if self.sub_var.get() else "disabled")

    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.download_dir)
        if d:
            self.download_dir = d
            self.dir_label.configure(text=self._short_path(d))

    @staticmethod
    def _short_path(p):
        return "..." + p[-37:] if len(p) > 40 else p
    
    # On URL Change 
    def _on_url_change(self, *args):
        if hasattr(self, "_fetch_timer") and self._fetch_timer:
            self.after_cancel(self._fetch_timer)
            self._fetch_timer = None

        url = self.url_var.get().strip()

        if url and (url.startswith("http")  or "youtube.com" in url or "youtu.be" in url):
            if self.video_info and (self.video_info.get("webpage_url") == url or self.video_info.get("original_url") == url):
                return
            self._fetch_timer = self.after(800, self._fetch_info)

    def _check_and_fetch(self):
        url = self.url_entry.get().strip()
        if url and (url.startswith("http") or "youtube.com" in url or "youtu.be" in url):
            if hasattr(self, "_last_fetched_url") and self._last_fetched_url == url:
                return
            
            self._last_fetched_url = url
            self._fetch_info()

    # ── Paste ────────────────────────────────────────────────────────────

    def _paste_url(self):
        try:
            clip = self.clipboard_get()
        except Exception:
            clip = ""
        if clip:
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, clip.strip())
            self._last_fetched_url = clip.strip()
            self._fetch_info()


    # ── Fetch info ───────────────────────────────────────────────────────

    def _fetch_info(self):
        if hasattr(self, "_fetch_timer") and self._fetch_timer:
            self.after_cancel(self._fetch_timer)
            self._fetch_timer = None
        url = self.url_entry.get().strip()
        if not url:
            return
        self._last_fetched_url = url
        self.title_label.configure(text="Fetching info...")
        self.channel_label.configure(text="")
        self.duration_label.configure(text="")
        self.thumb_label.configure(image=None, text="")
        threading.Thread(target=self._fetch_worker, args=(url,), daemon=True).start()

    def _fetch_worker(self, url):
        try:
            cmd = [YTDLP, "-J", "--no-download", url]
            if self.playlist_var.get():
                cmd.extend(["--yes-playlist", "--flat-playlist"])
            else:
                cmd.append("--no-playlist")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                    startupinfo=_hide_console())
            if result.returncode != 0:
                self.after(0, lambda: self._show_fetch_error(result.stderr.strip()))
                return
            info = json.loads(result.stdout)
            self.video_info = info
            self.after(0, lambda: self._display_info(info))
        except FileNotFoundError:
            self.after(0, lambda: self._show_fetch_error("yt-dlp not found! Place it in the project directory or install it."))
        except subprocess.TimeoutExpired:
            self.after(0, lambda: self._show_fetch_error("Timeout — check your connection."))
        except Exception as e:
            self.after(0, lambda: self._show_fetch_error(str(e)))

    def _show_fetch_error(self, msg):
        self.title_label.configure(text="Error!")
        self.channel_label.configure(text=msg[:120])
        self.duration_label.configure(text="")
        self.video_info = None

    def _display_info(self, info):
        if "entries" in info or info.get("_type") == "playlist":
            title = info.get("title", "Unknown Playlist")
            entries = list(info.get("entries", []))

            self.title_label.configure(text=title)
            self.channel_label.configure(text=f"{info.get('uploader', info.get('channel', ''))} ({len(entries)} video)")
            self.duration_label.configure(text="Playlist")
            
            # Since we cannot iterate over all the videos one by one, we use the defaults
            self.quality_menu.configure(values=["Best", "2160p", "1440p", "1080p", "720p", "480p", "360p"])
            self.quality_var.set("Best")
        else:
            self.title_label.configure(text=info.get("title", "?"))
            self.channel_label.configure(text=info.get("channel", info.get("uploader", "")))
            dur = fmt_duration(info.get("duration"))
            self.duration_label.configure(text=f"Duration: {dur}")
            self._update_quality_options(info)

        thumb_url = info.get("thumbnail")
        if thumb_url:
            threading.Thread(target=self._load_thumb, args=(thumb_url,), daemon=True).start()

    def _update_quality_options(self, info):
        heights = set()
        for f in info.get("formats", []):
            h = f.get("height")
            if h and f.get("vcodec", "none") != "none":
                heights.add(h)
        quality_map = {2160: "2160p", 1440: "1440p", 1080: "1080p", 720: "720p", 480: "480p", 360: "360p"}
        available = ["Best"]
        for h in sorted(heights, reverse=True):
            label = quality_map.get(h, f"{h}p")
            if label not in available:
                available.append(label)
        self.quality_menu.configure(values=available)
        self.quality_var.set("Best")

    def _load_thumb(self, url):
        try:
            resp = requests.get(url, timeout=10)
            img = Image.open(io.BytesIO(resp.content))
            img = img.resize((240, 135), Image.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(240, 135))
            self.after(0, lambda: self.thumb_label.configure(image=ctk_img, text=""))
            self._thumb_ref = ctk_img
        except Exception:
            pass

    # ── Download ─────────────────────────────────────────────────────────

    def _start_download(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("No URL", "Please enter a YouTube URL.")
            return
        if self.is_downloading:
            return

        cmd = self._build_cmd(url)
        self.is_downloading = True
        self.download_btn.configure(state="disabled", text="Downloading...")
        self.cancel_btn.configure(state="normal")
        self.progress_bar.set(0)
        self.status_label.configure(text="Starting...")
        threading.Thread(target=self._download_worker, args=(cmd, url), daemon=True).start()

    def _cancel_download(self):
        if self.process:
            try:
                if sys.platform == "win32":
                    self.process.terminate()
                else:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
        self.is_downloading = False
        self.cancel_btn.configure(state="disabled")
        self.download_btn.configure(state="normal", text="Download")
        self.progress_bar.set(0)
        self.status_label.configure(text="Cancelled.")

    def _build_cmd(self, url):
        cmd = [YTDLP, "--newline"]
        
        is_playlist = self.playlist_var.get()
        if is_playlist:
            cmd.append("--yes-playlist")
        else:
            cmd.append("--no-playlist")

        audio_only = self.format_seg.get() == "Audio"

        if audio_only:
            afmt = self.afmt_var.get()
            abitrate = self.aquality_var.get().replace("kbps", "")
            cmd += ["-x", "--audio-format", afmt, "--audio-quality", f"{abitrate}K"]
        else:
            quality = self.quality_var.get()
            vfmt = self.vfmt_var.get()

            if quality == "Best":
                fmt_str = "bestvideo+bestaudio/best"
            else:
                height = quality.replace("p", "")
                fmt_str = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"

            cmd += ["-f", fmt_str, "--merge-output-format", vfmt]

        if self.sub_var.get():
            lang = self.sub_lang_var.get()
            if lang == "auto":
                cmd += ["--write-auto-sub", "--sub-lang", "en"]
            else:
                cmd += ["--write-sub", "--sub-lang", lang]

        if is_playlist:
            out_tmpl = os.path.join(self.download_dir, "%(playlist_title)s", "%(playlist_index)s - %(title)s.%(ext)s")
        else:
            out_tmpl = os.path.join(self.download_dir, "%(title)s.%(ext)s")

        cmd += ["-o", out_tmpl]
        cmd.append(url)
        return cmd

    def _download_worker(self, cmd, url):
        title = self.video_info.get("title", url) if self.video_info else url
        try:
            kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, startupinfo=_hide_console())
            if sys.platform != "win32":
                kwargs["preexec_fn"] = os.setsid
            self.process = subprocess.Popen(cmd, **kwargs)

            for line in self.process.stdout:
                if not self.is_downloading:
                    break
                line = line.strip()
                if line:
                    self._parse_progress(line)

            self.process.wait()

            if not self.is_downloading:
                return

            ok = self.process.returncode == 0
            self.after(0, lambda: self._download_finished(ok, title))
        except FileNotFoundError:
            self.after(0, lambda: self._download_finished(False, title, "yt-dlp not found!"))
        except Exception as e:
            self.after(0, lambda: self._download_finished(False, title, str(e)))

    _progress_re = re.compile(
        r"\[download\]\s+([\d.]+)%\s+of\s+~?([\d.]+\S+)\s+at\s+([\d.]+\S+)\s+ETA\s+(\S+)"
    )

    def _parse_progress(self, line):
        m = self._progress_re.search(line)
        if m:
            pct = float(m.group(1))
            total = m.group(2)
            speed = m.group(3)
            eta = m.group(4)
            self.after(0, lambda: self._update_progress(pct, total, speed, eta))
        elif "[download] 100%" in line:
            self.after(0, lambda: self._update_progress(100, "", "", ""))
        elif line.startswith("["):
            short = line[:80]
            self.after(0, lambda: self.status_label.configure(text=short))

    def _update_progress(self, pct, total, speed, eta):
        self.progress_bar.set(pct / 100)
        if pct >= 100:
            self.status_label.configure(text="Merging / finalizing...")
        else:
            self.status_label.configure(text=f"{pct:.1f}%  —  {speed}  —  ETA {eta}  ({total})")

    def _download_finished(self, success, title, err_msg=None):
        self.is_downloading = False
        self.process = None
        self.download_btn.configure(state="normal", text="Download")
        self.cancel_btn.configure(state="disabled")

        if success:
            self.progress_bar.set(1)
            self.status_label.configure(text="Completed!")
            self._add_history(title, True)
            messagebox.showinfo("Done", f"Download completed!\n\n{title}\n\nLocation: {self.download_dir}")
        else:
            self.progress_bar.set(0)
            msg = err_msg or "Download failed."
            self.status_label.configure(text=f"Error: {msg[:60]}")
            self._add_history(title, False)

    # ── History ──────────────────────────────────────────────────────────

    def _add_history(self, title, success):
        if self.history_placeholder.winfo_exists():
            self.history_placeholder.destroy()

        now = datetime.now().strftime("%H:%M")
        icon = "+" if success else "x"
        color = "#2ecc71" if success else "#e74c3c"
        short_title = title[:55] + "..." if len(title) > 55 else title
        self.history.insert(0, {"title": title, "success": success, "time": now})

        row = ctk.CTkLabel(self.history_frame,
                           text=f"{icon}  [{now}]  {short_title}",
                           anchor="w", text_color=color)
        for i, child in enumerate(self.history_frame.winfo_children()):
            child.grid(row=i + 1)
        row.grid(row=0, column=0, sticky="w", padx=4, pady=1)


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
