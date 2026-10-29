#!/usr/bin/env bash
set -euo pipefail
# Usage: bash deploy/install-user-service.sh /absolute/path/to/project /absolute/path/to/venv
PROJECT=$(realpath "${1:?project directory required}")
VENV=$(realpath "${2:?venv directory required}")
mkdir -p "$PROJECT/data" "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/paperpilot-api.service" <<EOF
[Unit]
Description=PaperPilot Agent API
After=network-online.target
[Service]
WorkingDirectory=$PROJECT
ExecStart=$VENV/bin/python -m uvicorn paperpilot.api:create_app --factory --host 127.0.0.1 --port 18080 --workers 1
Environment=OPENBLAS_NUM_THREADS=1
Environment=OMP_NUM_THREADS=1
Environment=PYTHONUTF8=1
Restart=on-failure
RestartSec=5
[Install]
WantedBy=default.target
EOF
cat > "$HOME/.config/systemd/user/paperpilot-web.service" <<EOF
[Unit]
Description=PaperPilot Agent Web
After=paperpilot-api.service
[Service]
WorkingDirectory=$PROJECT
ExecStart=$VENV/bin/python -m streamlit run paperpilot/ui.py --server.address=127.0.0.1 --server.port=18501 --server.headless=true --browser.gatherUsageStats=false
Environment=PAPERPILOT_API_URL=http://127.0.0.1:18080
Environment=OPENBLAS_NUM_THREADS=1
Environment=OMP_NUM_THREADS=1
Restart=on-failure
RestartSec=5
[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now paperpilot-api paperpilot-web
systemctl --user --no-pager status paperpilot-api paperpilot-web
