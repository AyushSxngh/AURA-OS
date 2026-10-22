#!/usr/bin/env python3
"""
AURA OS — Hypervisor Offline Transfer Bridge Service
Autonomous Host <-> Android Guest File Transfer Server

Features:
1. Listens on 0.0.0.0:8088 (accessible from host and guest VM via localhost:8088 or 127.0.0.1:8088).
2. Serves and syncs with ~/Desktop/AURA_Transfer folder.
3. Automatically sets up ADB reverse port forwarding (tcp:8088 -> tcp:8088).
4. Modern high-performance web portal for uploading/downloading APKs, media, and files with zero ADB tracking.
5. Auto-cooperates with aura-gui: If aura-gui already holds port 8088, monitors and maintains adb reverse.
"""

import os
import sys
import time
import socket
import glob
import urllib.parse
import subprocess
import signal
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

PID_FILE = "/tmp/sec_bridge_service.pid"
LOG_FILE = "/tmp/sec_bridge_service.log"
PORT = 8088

def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{ts}] [sec_bridge_service] {msg}"
    print(formatted, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(formatted + "\n")
    except Exception:
        pass

def get_transfer_dir() -> str:
    home = os.environ.get("HOME", os.path.expanduser("~"))
    path = os.path.join(home, "Desktop", "AURA_Transfer")
    os.makedirs(path, exist_ok=True)
    return path

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0

def ensure_adb_reverse():
    try:
        res = subprocess.run(
            ["adb", "-s", "emulator-5554", "reverse", "tcp:8088", "tcp:8088"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3
        )
        return res.returncode == 0
    except Exception:
        return False

def format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024.0:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024.0 * 1024.0):.1f} MB"
    else:
        return f"{size_bytes / (1024.0 * 1024.0 * 1024.0):.2f} GB"

def get_file_icon(ext: str) -> str:
    ext = ext.lower().lstrip(".")
    if ext == "apk":
        return "📦"
    elif ext in ["jpg", "jpeg", "png", "webp", "gif"]:
        return "🖼️"
    elif ext in ["mp4", "mkv", "mov", "avi"]:
        return "🎬"
    elif ext in ["pdf", "doc", "docx", "txt"]:
        return "📄"
    elif ext in ["mp3", "wav", "flac", "ogg"]:
        return "🎵"
    elif ext in ["zip", "rar", "7z", "tar", "gz"]:
        return "🗜️"
    return "📁"

class BridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Redirect to log
        log(f"{self.address_string()} - {format % args}")

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        transfer_dir = get_transfer_dir()

        if path in ["/", "/index.html"]:
            self.serve_portal(transfer_dir)
        elif path.startswith("/download/"):
            filename = urllib.parse.unquote(path[10:])
            self.serve_download(transfer_dir, filename)
        elif path == "/api/open_folder":
            if sys.platform == "darwin":
                subprocess.Popen(["open", transfer_dir])
            self.send_json_response({"status": "ok"})
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        transfer_dir = get_transfer_dir()

        if path == "/upload":
            query = urllib.parse.parse_qs(parsed.query)
            filename = query.get("name", [f"upload_{int(time.time())}.bin"])[0]
            filename = os.path.basename(urllib.parse.unquote(filename))
            target_path = os.path.join(transfer_dir, filename)

            content_length = int(self.headers.get("Content-Length", 0))
            bytes_read = 0
            with open(target_path, "wb") as f:
                while bytes_read < content_length:
                    chunk_size = min(65536, content_length - bytes_read)
                    chunk = self.rfile.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    bytes_read += len(chunk)

            log(f"Successfully uploaded: {filename} ({bytes_read} bytes)")
            self.send_json_response({"status": "success", "file": filename, "bytes": bytes_read})
        else:
            self.send_response(405)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"405 Method Not Allowed")

    def send_json_response(self, data: dict):
        body = urllib.parse.json.dumps(data).encode("utf-8") if hasattr(urllib.parse, "json") else __import__("json").dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def serve_download(self, transfer_dir: str, filename: str):
        filename = os.path.basename(filename)
        target_path = os.path.join(transfer_dir, filename)

        if not os.path.isfile(target_path):
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"File not found")
            return

        file_size = os.path.getsize(target_path)
        ext = os.path.splitext(filename)[1].lower()
        content_type = "application/octet-stream"
        if ext == ".apk":
            content_type = "application/vnd.android.package-archive"
        elif ext in [".jpg", ".jpeg"]:
            content_type = "image/jpeg"
        elif ext == ".png":
            content_type = "image/png"
        elif ext == ".pdf":
            content_type = "application/pdf"
        elif ext == ".mp4":
            content_type = "video/mp4"

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(file_size))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        with open(target_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def serve_portal(self, transfer_dir: str):
        files_html = []
        try:
            entries = os.listdir(transfer_dir)
            entries.sort(key=lambda s: s.lower())
        except Exception:
            entries = []

        valid_files = []
        for name in entries:
            full = os.path.join(transfer_dir, name)
            if os.path.isfile(full):
                size = os.path.getsize(full)
                ext = os.path.splitext(name)[1]
                icon = get_file_icon(ext)
                valid_files.append((name, size, icon))

        if not valid_files:
            file_section = f'<div class="empty-state">No files currently in <code>{transfer_dir}</code>.<br>Drop any APK or file into this Mac folder to download or install it on Android!</div>'
        else:
            for name, size, icon in valid_files:
                is_apk = name.lower().endswith(".apk")
                badge = '<span class="badge apk">Android APK</span>' if is_apk else ""
                action_text = "⬇️ Download / Install" if is_apk else "⬇️ Download"
                encoded_name = urllib.parse.quote(name)
                formatted_size = format_file_size(size)

                files_html.append(f"""
                <div class="file-item">
                    <div class="file-left">
                        <span class="file-icon">{icon}</span>
                        <div class="file-details">
                            <div class="file-name">{name} {badge}</div>
                            <div class="file-size">{formatted_size}</div>
                        </div>
                    </div>
                    <a class="btn-dl" href="/download/{encoded_name}" download="{name}">{action_text}</a>
                </div>
                """)
            file_section = "\n".join(files_html)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>AURA OS — Offline Hypervisor Transfer Bridge</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: #0f172a;
            color: #f8fafc;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            padding: 16px;
            max-width: 680px;
            margin: 0 auto;
        }}
        .header {{
            text-align: center;
            padding: 24px 0 16px;
            border-bottom: 1px solid #1e293b;
            margin-bottom: 20px;
        }}
        .title {{
            font-size: 22px;
            font-weight: 800;
            color: #38bdf8;
            letter-spacing: -0.5px;
            margin-bottom: 6px;
        }}
        .subtitle {{
            font-size: 13px;
            color: #94a3b8;
        }}
        .bridge-pill {{
            display: inline-block;
            background: #064e3b;
            color: #34d399;
            padding: 4px 12px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 600;
            margin-top: 8px;
        }}
        .card {{
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 14px;
            padding: 18px;
            margin-bottom: 18px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
        }}
        .card-header {{
            font-size: 15px;
            font-weight: 700;
            margin-bottom: 12px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .file-list {{
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}
        .file-item {{
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 10px;
            padding: 12px 14px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .file-left {{
            display: flex;
            align-items: center;
            gap: 12px;
            overflow: hidden;
        }}
        .file-icon {{
            font-size: 24px;
        }}
        .file-details {{
            overflow: hidden;
        }}
        .file-name {{
            font-size: 14px;
            font-weight: 600;
            color: #f1f5f9;
            word-break: break-all;
        }}
        .file-size {{
            font-size: 11px;
            color: #64748b;
            margin-top: 2px;
        }}
        .btn-dl {{
            background: #2563eb;
            color: white;
            text-decoration: none;
            padding: 8px 14px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            white-space: nowrap;
            transition: background 0.2s;
        }}
        .btn-dl:hover {{ background: #1d4ed8; }}
        .badge.apk {{
            background: #7e22ce;
            color: #f3e8ff;
            font-size: 10px;
            padding: 2px 6px;
            border-radius: 4px;
            margin-left: 6px;
        }}
        .dropzone {{
            border: 2px dashed #475569;
            border-radius: 10px;
            padding: 26px 16px;
            text-align: center;
            background: #0f172a;
            cursor: pointer;
            transition: border-color 0.2s;
        }}
        .dropzone:hover {{ border-color: #38bdf8; }}
        .dropzone-icon {{ font-size: 32px; margin-bottom: 8px; }}
        .dropzone-text {{ font-size: 14px; color: #cbd5e1; font-weight: 500; }}
        .dropzone-sub {{ font-size: 12px; color: #64748b; margin-top: 4px; }}
        .progress-bar {{
            height: 6px;
            background: #334155;
            border-radius: 3px;
            margin-top: 12px;
            overflow: hidden;
            display: none;
        }}
        .progress-fill {{
            height: 100%;
            background: #38bdf8;
            width: 0%;
            transition: width 0.1s;
        }}
        .empty-state {{
            padding: 24px 12px;
            text-align: center;
            color: #64748b;
            font-size: 13px;
            line-height: 1.5;
        }}
        code {{
            background: #1e293b;
            padding: 2px 6px;
            border-radius: 4px;
            color: #38bdf8;
            font-family: monospace;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="title">⚡ AURA OS Offline Bridge</div>
        <div class="subtitle">Direct Host &lt;-&gt; Android Hypervisor File Portal</div>
        <div class="bridge-pill">● Offline Bridge Connected (localhost:8088)</div>
    </div>

    <!-- Upload from Android to Mac -->
    <div class="card">
        <div class="card-header">
            <span>📤 Send File from Android to Mac</span>
        </div>
        <div class="dropzone" onclick="document.getElementById('fileInput').click()">
            <div class="dropzone-icon">📁</div>
            <div class="dropzone-text">Tap here to choose files or photos to export</div>
            <div class="dropzone-sub">Saves instantly to Mac Desktop: <code>{transfer_dir}</code></div>
            <input type="file" id="fileInput" style="display:none" multiple onchange="uploadFiles(this.files)">
        </div>
        <div class="progress-bar" id="progressBar">
            <div class="progress-fill" id="progressFill"></div>
        </div>
        <div id="statusText" style="font-size: 12px; color: #38bdf8; margin-top: 8px; text-align: center; display: none;"></div>
    </div>

    <!-- Download from Mac to Android -->
    <div class="card">
        <div class="card-header">
            <span>📥 Download / Install on Android (from Mac)</span>
            <span style="font-size: 11px; color: #94a3b8;">Auto-Refreshes</span>
        </div>
        <div class="file-list">
            {file_section}
        </div>
    </div>

    <script>
        async function uploadFiles(files) {{
            if (!files || files.length === 0) return;
            const pBar = document.getElementById('progressBar');
            const pFill = document.getElementById('progressFill');
            const status = document.getElementById('statusText');
            pBar.style.display = 'block';
            status.style.display = 'block';

            for (let i = 0; i < files.length; i++) {{
                const f = files[i];
                status.innerText = `Uploading ${{f.name}} (${{i + 1}}/${{files.length}})...`;
                pFill.style.width = '30%';

                try {{
                    const url = '/upload?name=' + encodeURIComponent(f.name);
                    const resp = await fetch(url, {{
                        method: 'POST',
                        body: f
                    }});
                    pFill.style.width = '100%';
                    if (resp.ok) {{
                        status.innerText = `✅ Successfully uploaded ${{f.name}} to Mac!`;
                    }} else {{
                        status.innerText = `⚠️ Upload failed for ${{f.name}}`;
                    }}
                }} catch (e) {{
                    status.innerText = `❌ Error: ` + e;
                }}
            }}

            setTimeout(() => {{
                location.reload();
            }}, 1200);
        }}
    </script>
</body>
</html>"""

        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

def daemon_loop():
    # Save PID
    pid = os.getpid()
    with open(PID_FILE, "w") as f:
        f.write(str(pid))

    def on_term(signum, frame):
        log("Received SIGTERM, shutting down bridge daemon.")
        try:
            os.remove(PID_FILE)
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, on_term)

    transfer_dir = get_transfer_dir()
    log(f"Starting AURA Bridge Daemon (PID {pid}) on port {PORT}")
    log(f"Serving transfer folder: {transfer_dir}")

    # Background thread to ensure ADB reverse stays active whenever device connects
    def adb_reverse_maintainer():
        while True:
            ensure_adb_reverse()
            time.sleep(10)

    t = threading.Thread(target=adb_reverse_maintainer, daemon=True)
    t.start()

    # Background thread to sync emulator toolbar screenshots to Android Gallery
    def screenshot_sync_maintainer():
        desktop = os.path.expanduser("~/Desktop")
        synced_files = set()
        for f in glob.glob(os.path.join(desktop, "Screenshot_*.png")):
            synced_files.add(os.path.basename(f))

        while True:
            try:
                for f in glob.glob(os.path.join(desktop, "Screenshot_*.png")):
                    fname = os.path.basename(f)
                    if fname not in synced_files:
                        synced_files.add(fname)
                        dest = f"/sdcard/Pictures/Screenshots/{fname}"
                        subprocess.run(
                            ["adb", "-s", "emulator-5554", "push", f, dest],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=5
                        )
                        subprocess.run(
                            ["adb", "-s", "emulator-5554", "shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", f"file://{dest}"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=5
                        )
                        log(f"📸 Auto-synced {fname} to Android Gallery (/sdcard/Pictures/Screenshots/)")
            except Exception:
                pass
            time.sleep(2)

    t_ss = threading.Thread(target=screenshot_sync_maintainer, daemon=True)
    t_ss.start()

    # Check if port is already held (e.g. by aura-gui)
    if is_port_in_use(PORT):
        log(f"Port {PORT} is already bound (likely aura-gui is running). Daemon will monitor and maintain ADB reverse.")
        while True:
            time.sleep(5)
            if not is_port_in_use(PORT):
                log(f"Port {PORT} became available. Taking over port listener.")
                break

    try:
        server = ThreadingHTTPServer(("0.0.0.0", PORT), BridgeHandler)
        server.daemon_threads = True
        log(f"🚀 Bridge HTTP Server active on http://0.0.0.0:{PORT}")
        server.serve_forever()
    except Exception as e:
        log(f"Bridge server encountered error: {e}")
    finally:
        try:
            os.remove(PID_FILE)
        except Exception:
            pass

def stop_daemon():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
            print(f"🛑 Stopped bridge daemon (PID {pid})")
        except Exception:
            pass
        try:
            os.remove(PID_FILE)
        except Exception:
            pass

def main():
    if len(sys.argv) < 2:
        print("Usage: sec_bridge_service.py [start|stop|status|daemon|open]")
        return

    cmd = sys.argv[1].lower()

    if cmd == "daemon":
        daemon_loop()
    elif cmd == "start":
        stop_daemon()
        script = os.path.abspath(__file__)
        log_f = open(LOG_FILE, "a")
        proc = subprocess.Popen(
            [sys.executable, "-u", script, "daemon"],
            stdin=subprocess.DEVNULL,
            stdout=log_f,
            stderr=log_f,
            start_new_session=True
        )
        print(f"🚀 Started AURA Transfer Bridge Service in background (PID {proc.pid})")
    elif cmd == "stop":
        stop_daemon()
    elif cmd == "status":
        is_running = False
        pid_val = None
        if os.path.exists(PID_FILE):
            try:
                pid_val = int(open(PID_FILE).read().strip())
                os.kill(pid_val, 0)
                is_running = True
            except Exception:
                is_running = False

        port_active = is_port_in_use(PORT)
        print(f"🌉 AURA OS Offline Transfer Bridge Status:")
        print(f"   Daemon Process : {'RUNNING (PID ' + str(pid_val) + ')' if is_running else 'STOPPED'}")
        print(f"   Port {PORT}      : {'ACTIVE (Listening)' if port_active else 'INACTIVE'}")
        print(f"   Transfer Folder: {get_transfer_dir()}")
    elif cmd == "open":
        ensure_adb_reverse()
        subprocess.run(["adb", "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", "http://localhost:8088", "com.android.chrome"])
        print("📱 Opened bridge in guest Chrome!")
    else:
        print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()
