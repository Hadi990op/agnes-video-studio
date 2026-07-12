# Deployment Guide

This guide covers running Agnes Video Studio as a service with automatic startup.

---

## 1. Prerequisites

- Python 3.10+
- An Agnes AI API key (free) — get one at [agnes-ai.com](https://agnes-ai.com)
  - Sign up → Dashboard → Generate API Key

## 2. Clone & Install

```bash
git clone https://github.com/Hadi990op/agnes-video-studio.git
cd agnes-video-studio

# Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Configure API Key

```bash
mkdir -p .agnes_config
cat > .agnes_config/config.json << 'EOF'
{
  "api_key": "YOUR_AGNES_API_KEY_HERE"
}
EOF
chmod 600 .agnes_config/config.json
```

Alternatively, use the environment variable:
```bash
export AGNES_API_KEY="YOUR_AGNES_API_KEY_HERE"
```

Or set it through the web UI after starting the server (Settings → API Key).

## 4. Run Directly

```bash
source .venv/bin/activate
python server.py
```

The server runs on `http://localhost:8765`.

## 5. Run as a Systemd Service (Linux)

```bash
# Copy the service file (adjust paths if needed)
cp deploy/agnes-studio.service ~/.config/systemd/user/agnes-studio.service

# Edit the file to match your install path
# Replace %h with your actual home directory if running as user service,
# or copy to /etc/systemd/system/ for system-wide service

# For system-wide service:
sudo cp deploy/agnes-studio.service /etc/systemd/system/
# Edit WorkingDirectory and ExecStart paths to match your setup
sudo nano /etc/systemd/system/agnes-studio.service

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable agnes-studio
sudo systemctl start agnes-studio

# Check status
sudo systemctl status agnes-studio
```

## 6. Reverse Proxy with Caddy (Optional)

If you want to expose the studio behind a reverse proxy with a path prefix (e.g. `/studio/`):

### Caddyfile snippet

```caddy
handle_path /studio/* {
    reverse_proxy localhost:8765
}

# Redirect /studio → /studio/ (no trailing slash)
redir /studio /studio/ permanent
```

Reload Caddy:
```bash
sudo systemctl reload caddy
```

### Nginx equivalent

```nginx
location /studio/ {
    proxy_pass http://localhost:8765/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

## 7. Verify

```bash
# Check the API
curl http://localhost:8765/api/config

# If behind proxy
curl https://your-domain.com/studio/api/config
```

You should see:
```json
{"api_key": "sk-...", "source": "config", "can_clear": true}
```

Open the web UI at `http://localhost:8765` (or `https://your-domain.com/studio/` if behind a proxy).

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `401 Unauthorized` on `/api/config` | API key not set. Create `.agnes_config/config.json` or set `AGNES_API_KEY` env var |
| `502 Bad Gateway` behind proxy | Backend not running. Check `systemctl status agnes-studio` |
| Task fails at 1% | Check `journalctl -u agnes-studio -f` for error logs. Ensure API key is valid |
| Image generation 503 | Agnes AI rate limit (free tier: 1 video/min, 20 image/min). Wait and retry |
