# YouTube Downloader

A simple desktop YouTube downloader built with Python and CustomTkinter.

![Dark theme UI](https://img.shields.io/badge/theme-dark-1a1a2e) ![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue) ![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

## Features

- Download video or audio-only from YouTube
- Choose video quality (360p to 4K) and format (MP4, MKV, WEBM)
- Choose audio format (MP3, M4A, WAV, FLAC, OGG) and bitrate
- Video preview with thumbnail, title, duration, and channel name
- Real-time progress bar with speed and ETA
- Cancel downloads at any time
- Optional subtitle download
- Dark theme UI
- Download history

## Requirements

- Python 3.8+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (bundled or installed separately)
- [ffmpeg](https://ffmpeg.org/download.html) (required for merging video+audio and format conversion)

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/yt-dlp-exe.git
cd yt-dlp-exe
pip install -r requirements.txt
```

### Getting yt-dlp

**Option A — Bundled binary (recommended for Windows):**

Download `yt-dlp.exe` from [yt-dlp releases](https://github.com/yt-dlp/yt-dlp/releases/latest) and place it in the project folder.

**Option B — System install (all platforms):**

```bash
# pip
pip install yt-dlp

# macOS
brew install yt-dlp

# Linux
sudo apt install yt-dlp   # or your package manager
```

The app checks for a bundled binary first, then falls back to `yt-dlp` on your PATH.

### Getting ffmpeg

```bash
# Windows — download from https://ffmpeg.org/download.html and add to PATH

# macOS
brew install ffmpeg

# Linux
sudo apt install ffmpeg
```

## Usage

```bash
python main.py
```

1. Paste a YouTube URL and click **Fetch** (or press Enter)
2. Choose format and quality from the sidebar
3. Click **Download**
4. Click **Cancel** to stop a download in progress

## Project Structure

```
yt-dlp-exe/
├── main.py              # Application (single file)
├── yt-dlp.exe           # Bundled yt-dlp binary (optional, Windows)
├── requirements.txt     # Python dependencies
└── README.md
```

## Credits

Powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp) — a powerful command-line video downloader.

## License

MIT
