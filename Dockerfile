FROM python:3.12
WORKDIR /app
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl tzdata libgl1 libglib2.0-0 && \
    ln -sf /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
RUN curl -sSf https://sh.rustup.rs  | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"
ENV TZ=Asia/Shanghai
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt  -i https://pypi.tuna.tsinghua.edu.cn/simple
COPY . .
RUN playwright install --with-deps chromium
ENV BTB_SERVER_NAME="0.0.0.0"
ENV GRADIO_SERVER_PORT 7860

CMD ["python", "main.py"]
