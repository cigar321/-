"""
犟种宝宝 — AI 定制服务（本地开发版）
======================================
- Mock 模式（默认）：返回模拟 AI 结果，无需 MediaPipe/OpenCV
- 生产模式：部署到云端时自动使用 MediaPipe 真实检测

启动: python server.py
测试: curl -X POST http://localhost:8080/api/v1/character/generate -F "image=@test.jpg"
"""

import io
import json
import logging
import os
import random
import time
import uuid

from flask import Flask, request, jsonify
from PIL import Image

# ── 配置 ──
USE_MOCK = os.environ.get("MOCK_MODE", "1") == "1"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


# ═══════════════════════════════════════════════════════════
# Mock 数据生成（本地开发用）
# ═══════════════════════════════════════════════════════════

def mock_blend_shapes():
    """生成随机的 Blend Shape 参数（模拟不同人脸）"""
    return {
        "BS_FaceWidth":    round(random.uniform(0.3, 0.8), 3),
        "BS_CheekPuff":    round(random.uniform(0.2, 0.6), 3),
        "BS_ChinPoint":    round(random.uniform(0.3, 0.7), 3),
        "BS_EyeDistance":  round(random.uniform(0.3, 0.7), 3),
        "BS_EyeSize":      round(random.uniform(0.4, 0.8), 3),
        "BS_MouthWidth":   round(random.uniform(0.3, 0.7), 3),
        "BS_MouthHeight":  round(random.uniform(0.3, 0.7), 3),
        "BS_BrowThick":    round(random.uniform(0.3, 0.7), 3),
        "BS_BrowAngle":    round(random.uniform(-0.3, 0.3), 3),
    }


MOCK_STYLES = ["hair_short", "hair_medium", "hair_long", "hair_tied", "hair_none"]
MOCK_TONES  = ["fair", "natural", "tan"]

def mock_hair():
    return {
        "style": random.choice(MOCK_STYLES),
        "color_hex": random.choice(["#1A1A1A", "#3A2A1A", "#6B4226",
                                     "#8B4513", "#DAA520"])
    }

def mock_skin():
    return {
        "tone": random.choice(MOCK_TONES),
        "color_hex": random.choice(["#FDEBD0", "#FDDCB5", "#F5C5A3",
                                    "#E8B88A", "#C6865A"])
    }

def mock_process(image_bytes):
    """模拟 AI 处理：随机延迟 0.5-1.5 秒后返回结果"""
    import time
    time.sleep(random.uniform(0.3, 1.0))

    return {
        "code": 0,
        "data": {
            "task_id": str(uuid.uuid4()),
            "blend_shapes": mock_blend_shapes(),
            "hair": mock_hair(),
            "skin": mock_skin(),
            "glasses": random.choice([True, False]),
            "confidence": round(random.uniform(0.88, 0.99), 3)
        }
    }


# ═══════════════════════════════════════════════════════════
# 真实处理（生产环境，需要 MediaPipe + OpenCV）
# ═══════════════════════════════════════════════════════════

_real_processor = None

def get_real_processor():
    global _real_processor
    if _real_processor is None:
        try:
            from ai_service import process_image
            _real_processor = process_image
            logger.info("✓ MediaPipe 真实处理器已加载")
        except ImportError as e:
            logger.warning(f"⚠ 无法加载 MediaPipe: {e}，回退到 Mock 模式")
            _real_processor = None
    return _real_processor


# ═══════════════════════════════════════════════════════════
# API 路由
# ═══════════════════════════════════════════════════════════

@app.route("/api/v1/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "version": "1.0.0-dev",
        "mode": "mock" if USE_MOCK else "production",
        "mediapipe_available": get_real_processor() is not None
    })


@app.route("/api/v1/character/generate", methods=["POST"])
def generate():
    t0 = time.time()

    # 验证上传
    if "image" not in request.files:
        return jsonify({"code": 1, "message": "请上传图片"}), 400

    file = request.files["image"]
    image_bytes = file.read()

    if len(image_bytes) == 0:
        return jsonify({"code": 1, "message": "图片为空"}), 400

    if len(image_bytes) > 5 * 1024 * 1024:
        return jsonify({"code": 1, "message": "图片大小不能超过 5MB"}), 400

    # 验证图片格式
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.verify()
    except Exception:
        return jsonify({"code": 1, "message": "无法识别的图片格式"}), 400

    # 处理
    if USE_MOCK:
        result = mock_process(image_bytes)
    else:
        processor = get_real_processor()
        if processor is None:
            result = mock_process(image_bytes)
        else:
            result = processor(image_bytes)

    result["elapsed_ms"] = round((time.time() - t0) * 1000)
    logger.info(f"[{result['code']}] {result.get('message','OK')} "
                f"({result['elapsed_ms']}ms)")

    status = 200 if result["code"] == 0 else 400
    return jsonify(result), status


# ═══════════════════════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════╗
    ║    犟种宝宝 AI 定制服务 v1.0-dev    ║
    ║    模式: {mode:8s}              ║
    ║    地址: http://localhost:8080      ║
    ╚══════════════════════════════════════╝
    """.format(mode="MOCK" if USE_MOCK else "PRODUCTION"))
    app.run(host="0.0.0.0", port=8080, debug=True)
