#!/bin/sh
set -eu

MIRROR="${PIP_MIRROR:-https://pypi.tuna.tsinghua.edu.cn/simple}"

echo "[docker_install_deps] install opencv-headless + rapidocr deps (skip opencv-python)..."
pip install --no-cache-dir \
    "opencv-python-headless>=4.8.0" \
    "onnxruntime>=1.19.0" \
    "pyclipper" "shapely" "pyyaml" "six" \
    "colorlog" "omegaconf!=2.2.1" "tqdm" "requests" \
    -i "$MIRROR"

pip install --no-cache-dir "rapidocr>=3.8.0" --no-deps -i "$MIRROR"

echo "[docker_install_deps] install core requirements (exclude ocr packages)..."
grep -vE '^(opencv-python-headless|rapidocr|onnxruntime)([=<>]|$)' requirements.txt > /tmp/requirements-core.txt
pip install --no-cache-dir -r /tmp/requirements-core.txt -i "$MIRROR"

echo "[docker_install_deps] verify cv2 + RapidOCR..."
python -c "import cv2; from rapidocr import RapidOCR; RapidOCR(); print('RapidOCR ok', cv2.__file__)"
