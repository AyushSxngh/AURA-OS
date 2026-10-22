use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::thread;

pub struct HttpBridge;

impl HttpBridge {
    pub fn get_transfer_dir() -> PathBuf {
        let home = std::env::var("HOME").or_else(|_| std::env::var("USERPROFILE")).unwrap_or_else(|_| ".".to_string());
        let desktop = PathBuf::from(home).join("Desktop").join("AURA_Transfer");
        let _ = fs::create_dir_all(&desktop);
        desktop
    }

    pub fn start_server(port: u16) -> Option<thread::JoinHandle<()>> {
        let transfer_dir = Arc::new(Self::get_transfer_dir());
        let addr = format!("0.0.0.0:{}", port);

        let listener = match TcpListener::bind(&addr) {
            Ok(l) => l,
            Err(e) => {
                eprintln!("[HttpBridge] Failed to bind to {}: {}", addr, e);
                return None;
            }
        };

        println!("[HttpBridge] Offline Transfer Bridge listening on http://{}", addr);

        let handle = thread::spawn(move || {
            for stream_res in listener.incoming() {
                if let Ok(stream) = stream_res {
                    let dir = Arc::clone(&transfer_dir);
                    thread::spawn(move || {
                        let _ = Self::handle_client(stream, &dir);
                    });
                }
            }
        });

        Some(handle)
    }

    fn handle_client(mut stream: TcpStream, dir: &Path) -> std::io::Result<()> {
        let mut reader = BufReader::new(stream.try_clone()?);
        let mut request_line = String::new();
        if reader.read_line(&mut request_line)? == 0 {
            return Ok(());
        }

        let parts: Vec<&str> = request_line.split_whitespace().collect();
        if parts.len() < 2 {
            return Ok(());
        }

        let method = parts[0];
        let raw_uri = parts[1];

        // Parse headers
        let mut content_length: usize = 0;
        let mut line = String::new();
        while reader.read_line(&mut line)? > 0 {
            let trimmed = line.trim();
            if trimmed.is_empty() {
                break;
            }
            if let Some((k, v)) = trimmed.split_once(':') {
                if k.trim().eq_ignore_ascii_case("content-length") {
                    content_length = v.trim().parse::<usize>().unwrap_or(0);
                }
            }
            line.clear();
        }

        let (path_part, query_part) = match raw_uri.split_once('?') {
            Some((p, q)) => (p, q),
            None => (raw_uri, ""),
        };

        if method == "GET" || method == "HEAD" {
            if path_part == "/" || path_part == "/index.html" {
                Self::serve_html_index(&mut stream, dir)?;
            } else if path_part.starts_with("/download/") {
                let filename = urlencoding_decode(&path_part[10..]);
                Self::serve_file_download(&mut stream, dir, &filename)?;
            } else if path_part == "/api/open_folder" {
                #[cfg(target_os = "macos")]
                {
                    let _ = std::process::Command::new("open").arg(dir).spawn();
                }
                Self::send_response(&mut stream, "200 OK", "application/json", b"{\"status\":\"ok\"}")?;
            } else {
                Self::send_response(&mut stream, "404 Not Found", "text/plain", b"Not Found")?;
            }
        } else if method == "POST" && path_part == "/upload" {
            let filename = Self::parse_query_param(query_part, "name")
                .unwrap_or_else(|| format!("upload_{}.bin", std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_secs()));
            Self::handle_file_upload(&mut reader, &mut stream, dir, &filename, content_length)?;
        } else {
            Self::send_response(&mut stream, "405 Method Not Allowed", "text/plain", b"Method Not Allowed")?;
        }

        Ok(())
    }

    fn serve_html_index(stream: &mut TcpStream, dir: &Path) -> std::io::Result<()> {
        let mut files_html = String::new();
        if let Ok(entries) = fs::read_dir(dir) {
            let mut items: Vec<(String, u64, String)> = Vec::new();
            for entry in entries.flatten() {
                if let Ok(meta) = entry.metadata() {
                    if meta.is_file() {
                        let name = entry.file_name().to_string_lossy().to_string();
                        let size = meta.len();
                        let ext = Path::new(&name).extension().and_then(|e| e.to_str()).unwrap_or("").to_lowercase();
                        let icon = match ext.as_str() {
                            "apk" => "📦",
                            "jpg" | "jpeg" | "png" | "webp" => "🖼️",
                            "mp4" | "mkv" => "🎬",
                            "pdf" => "📄",
                            "mp3" | "wav" => "🎵",
                            _ => "📁",
                        };
                        items.push((name, size, icon.to_string()));
                    }
                }
            }

            items.sort_by(|a, b| a.0.to_lowercase().cmp(&b.0.to_lowercase()));

            if items.is_empty() {
                files_html = r#"<div class="empty-state">No files currently in <code>~/Desktop/AURA_Transfer</code>.<br>Drop any APK or file into that folder on your Mac to download it here!</div>"#.to_string();
            } else {
                for (name, size, icon) in items {
                    let formatted_size = format_file_size(size);
                    let encoded_name = urlencoding_encode(&name);
                    let is_apk = name.ends_with(".apk");
                    let badge = if is_apk { r#"<span class="badge apk">Android APK</span>"# } else { "" };
                    files_html.push_str(&format!(
                        r#"<div class="file-item">
                            <div class="file-left">
                                <span class="file-icon">{}</span>
                                <div class="file-details">
                                    <div class="file-name">{} {}</div>
                                    <div class="file-size">{}</div>
                                </div>
                            </div>
                            <a class="btn-dl" href="/download/{}" download="{}">⬇️ Download{}</a>
                        </div>"#,
                        icon, name, badge, formatted_size, encoded_name, name, if is_apk { " / Install" } else { "" }
                    ));
                }
            }
        }

        let dir_str = dir.display().to_string();
        let html = format!(
            r#"<!DOCTYPE html>
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
            padding: 4px 10px;
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
            <div class="dropzone-sub">Saves instantly to Mac Desktop: <code>{dir_str}</code></div>
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
            <span style="font-size: 11px; color: #94a3b8;">Refreshes on reload</span>
        </div>
        <div class="file-list">
            {files_html}
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
</html>"#,
            dir_str = dir_str,
            files_html = files_html
        );

        Self::send_response(stream, "200 OK", "text/html; charset=utf-8", html.as_bytes())
    }

    fn serve_file_download(stream: &mut TcpStream, dir: &Path, filename: &str) -> std::io::Result<()> {
        let safe_name = Path::new(filename).file_name().unwrap_or_default().to_string_lossy().to_string();
        let target_path = dir.join(&safe_name);

        if !target_path.exists() || !target_path.is_file() {
            return Self::send_response(stream, "404 Not Found", "text/plain", b"File not found");
        }

        let metadata = fs::metadata(&target_path)?;
        let file_size = metadata.len();
        let mut file = fs::File::open(&target_path)?;

        let ext = Path::new(&safe_name).extension().and_then(|e| e.to_str()).unwrap_or("").to_lowercase();
        let content_type = match ext.as_str() {
            "apk" => "application/vnd.android.package-archive",
            "jpg" | "jpeg" => "image/jpeg",
            "png" => "image/png",
            "webp" => "image/webp",
            "mp4" => "video/mp4",
            "pdf" => "application/pdf",
            "txt" => "text/plain",
            _ => "application/octet-stream",
        };

        let headers = format!(
            "HTTP/1.1 200 OK\r\nContent-Type: {}\r\nContent-Length: {}\r\nContent-Disposition: attachment; filename=\"{}\"\r\nConnection: close\r\n\r\n",
            content_type, file_size, safe_name
        );
        stream.write_all(headers.as_bytes())?;

        let mut buf = [0u8; 65536];
        loop {
            let n = file.read(&mut buf)?;
            if n == 0 {
                break;
            }
            stream.write_all(&buf[..n])?;
        }

        Ok(())
    }

    fn handle_file_upload(
        reader: &mut BufReader<TcpStream>,
        stream: &mut TcpStream,
        dir: &Path,
        filename: &str,
        content_length: usize,
    ) -> std::io::Result<()> {
        let safe_name = Path::new(filename).file_name().unwrap_or_default().to_string_lossy().to_string();
        let target_path = dir.join(&safe_name);

        let mut out_file = fs::File::create(&target_path)?;
        let mut remaining = content_length;
        let mut buf = [0u8; 65536];

        while remaining > 0 {
            let to_read = std::cmp::min(remaining, buf.len());
            let n = reader.read(&mut buf[..to_read])?;
            if n == 0 {
                break;
            }
            out_file.write_all(&buf[..n])?;
            remaining -= n;
        }

        println!("[HttpBridge] Uploaded '{}' ({} bytes) to {}", safe_name, content_length, target_path.display());

        Self::send_response(stream, "200 OK", "application/json", b"{\"status\":\"success\"}")
    }

    fn parse_query_param(query: &str, param: &str) -> Option<String> {
        for pair in query.split('&') {
            if let Some((k, v)) = pair.split_once('=') {
                if k == param {
                    return Some(urlencoding_decode(v));
                }
            }
        }
        None
    }

    fn send_response(stream: &mut TcpStream, status: &str, content_type: &str, body: &[u8]) -> std::io::Result<()> {
        let headers = format!(
            "HTTP/1.1 {}\r\nContent-Type: {}\r\nContent-Length: {}\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n",
            status, content_type, body.len()
        );
        stream.write_all(headers.as_bytes())?;
        stream.write_all(body)?;
        Ok(())
    }
}

fn format_file_size(bytes: u64) -> String {
    if bytes < 1024 {
        format!("{} B", bytes)
    } else if bytes < 1024 * 1024 {
        format!("{:.1} KB", bytes as f64 / 1024.0)
    } else if bytes < 1024 * 1024 * 1024 {
        format!("{:.1} MB", bytes as f64 / (1024.0 * 1024.0))
    } else {
        format!("{:.2} GB", bytes as f64 / (1024.0 * 1024.0 * 1024.0))
    }
}

fn urlencoding_decode(s: &str) -> String {
    let mut result = Vec::new();
    let bytes = s.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            if let Ok(byte) = u8::from_str_radix(std::str::from_utf8(&bytes[i + 1..i + 3]).unwrap_or(""), 16) {
                result.push(byte);
                i += 3;
                continue;
            }
        } else if bytes[i] == b'+' {
            result.push(b' ');
            i += 1;
            continue;
        }
        result.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&result).to_string()
}

fn urlencoding_encode(s: &str) -> String {
    let mut result = String::new();
    for c in s.chars() {
        if c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | '.' | '~') {
            result.push(c);
        } else {
            for b in c.to_string().as_bytes() {
                result.push_str(&format!("%{:02X}", b));
            }
        }
    }
    result
}
