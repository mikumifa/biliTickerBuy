FROM python:3.12-slim

ENV TZ=Asia/Shanghai \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BTB_SERVER_NAME=0.0.0.0 \
    GRADIO_SERVER_PORT=7860 \
    GRADIO_NUM_PORTS=100 \
    BTB_DOCKER=1 \
    DISPLAY=:99

ARG PIP_INDEX_URL=https://pypi.org/simple

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    fluxbox \
    fontconfig \
    fonts-wqy-microhei \
    fonts-wqy-zenhei \
    libasound2 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxkbcommon0 \
    supervisor \
    tzdata \
    x11vnc \
    xauth \
    xvfb && \
    ln -snf "/usr/share/zoneinfo/${TZ}" /etc/localtime && \
    echo "${TZ}" > /etc/timezone && \
    fc-cache -f && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install --upgrade --index-url "${PIP_INDEX_URL}" -r requirements.txt && \
    python - <<'PY'
import fastapi
import gradio
import jinja2
import starlette

print(
    "Resolved runtime versions:",
    {
        "gradio": gradio.__version__,
        "fastapi": fastapi.__version__,
        "starlette": starlette.__version__,
        "jinja2": jinja2.__version__,
    },
)
PY

COPY . .

RUN mkdir -p /etc/supervisor/conf.d

COPY <<EOF /etc/supervisor/conf.d/supervisord.conf
[supervisord]
nodaemon=true
user=root

[program:xvfb]
command=/usr/bin/Xvfb :99 -screen 0 1280x720x16
autorestart=true
priority=100

[program:fluxbox]
command=/usr/bin/fluxbox
environment=DISPLAY=":99"
autorestart=true
priority=200

[program:x11vnc]
command=/usr/bin/x11vnc -display :99 -nopw -shared -forever -loop -noxdamage -repeat -nobell -wait 50
autorestart=true
priority=300
startsecs=5

[program:app]
command=python main.py
directory=/app
environment=DISPLAY=":99"
autorestart=unexpected
stopasgroup=true
killasgroup=true
startsecs=5
startretries=3
stdout_logfile=/dev/fd/1
stdout_logfile_maxbytes=0
stderr_logfile=/dev/fd/2
stderr_logfile_maxbytes=0
priority=400
EOF

EXPOSE 5900 7860

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
