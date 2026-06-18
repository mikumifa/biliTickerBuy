FROM python:3.12-slim

ENV TZ=Asia/Shanghai \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BTB_SERVER_NAME=0.0.0.0 \
    GRADIO_SERVER_PORT=7860 \
    GRADIO_NUM_PORTS=100 \
    BTB_DOCKER=1

ARG PIP_INDEX_URL=https://pypi.org/simple

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    fontconfig \
    fonts-wqy-microhei \
    fonts-wqy-zenhei \
    tzdata && \
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
EXPOSE 7860

CMD ["python", "main.py"]
