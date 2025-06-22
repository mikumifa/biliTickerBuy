FROM python:3.12
WORKDIR /app
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl tzdata xvfb x11vnc supervisor xauth \
    fluxbox xterm fonts-wqy-zenhei fonts-wqy-microhei \
    fontconfig && \
    ln -sf /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone && \
    fc-cache -fv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
RUN curl -sSf https://sh.rustup.rs  | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"
ENV TZ=Asia/Shanghai
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt  -i https://pypi.tuna.tsinghua.edu.cn/simple
COPY . .
RUN playwright install chromium
RUN apt-get update --allow-unauthenticated && \
    apt-get install -y --allow-unauthenticated --no-install-recommends \
    libnss3 libnspr4 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
    libgtk-3-0 libgbm1 libasound2 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ENV BTB_SERVER_NAME="0.0.0.0"
ENV GRADIO_SERVER_PORT=7860
ENV DISPLAY=:99
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
autorestart=true
priority=400
EOF
EXPOSE 5900
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
