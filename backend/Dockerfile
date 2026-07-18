FROM python:3.11-slim

WORKDIR /app

# 使用国内 Debian 镜像源加速 apt 下载
RUN sed -i 's|http://deb.debian.org/debian|https://mirrors.aliyun.com/debian|g' /etc/apt/sources.list.d/debian.sources \
    && sed -i 's|http://deb.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources

# 安装系统依赖（Playwright 浏览器需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libgomp1 \
    libgl1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    fonts-wqy-zenhei \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# 配置中文字体环境变量，确保 Playwright 截图能渲染中文
ENV LANG=zh_CN.UTF-8
ENV LC_ALL=zh_CN.UTF-8

# 安装 Python 依赖
# rapidocr 会拉 opencv-python（需 libGL）；Docker 用 headless + --no-deps，构建时自检 cv2
COPY backend/requirements.txt backend/docker_install_deps.sh ./
RUN chmod +x docker_install_deps.sh && ./docker_install_deps.sh

# 使用国内镜像安装 Playwright 浏览器（只装 Chromium，节省空间）
# 注意：系统依赖已在上面手动安装，不需要 playwright install-deps（Debian Trixie 部分包名不兼容）
ENV PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright
# browser-use 默认会下载 uBlock 等扩展，国内云环境易长时间卡住
ENV BROWSER_USE_DISABLE_EXTENSIONS=1
RUN playwright install chromium

# 复制代码与内置文档
COPY backend/ .
COPY docs-site ./docs-site

# 创建日志目录
RUN mkdir -p logs

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
