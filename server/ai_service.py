# 犟种宝宝 — AI 定制云端服务
# 部署：腾讯云 SCF / 阿里云函数计算
# Runtime: Python 3.10+
#
# 依赖安装（部署时在 SCF 层或 Docker 镜像中预装）：
#   mediapipe==0.10.11
#   opencv-python-headless==4.9.0.80
#   numpy==1.26.0
#   flask==3.0.0
#   pillow==10.2.0

import base64
import io
import json
import logging
import time
import uuid

import cv2
import mediapipe as mp
import numpy as np

# ---------------------------------------------------------------------------
# 初始化（模块级别，利用 SCF 实例复用，避免冷启动时重复加载模型）
# ---------------------------------------------------------------------------

mp_face_mesh = mp.solutions.face_mesh

face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=True,
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MediaPipe 关键点索引常量
# ---------------------------------------------------------------------------

FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288,
             397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136,
             172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]

NOSE_TIP = 1
CHIN = 152
FOREHEAD = 10

LEFT_EYE_TOP = 159; LEFT_EYE_BOTTOM = 145
LEFT_EYE_LEFT = 33; LEFT_EYE_RIGHT = 133
LEFT_EYE_INNER = 133

RIGHT_EYE_TOP = 386; RIGHT_EYE_BOTTOM = 374
RIGHT_EYE_LEFT = 362; RIGHT_EYE_RIGHT = 263
RIGHT_EYE_INNER = 362

MOUTH_LEFT = 61; MOUTH_RIGHT = 291
MOUTH_TOP = 13; MOUTH_BOTTOM = 14

LEFT_BROW_TOP = 105; LEFT_BROW_BOTTOM = 55
RIGHT_BROW_TOP = 334; RIGHT_BROW_BOTTOM = 285

LEFT_CHEEK = 50; RIGHT_CHEEK = 280


def clamp(value, min_val=0.0, max_val=1.0):
    return max(min_val, min(max_val, value))


def distance(p1, p2):
    return np.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2 + (p1[2]-p2[2])**2)


def get_landmark_xy(landmarks, idx, image_shape):
    h, w = image_shape[:2]
    lm = landmarks.landmark[idx]
    return np.array([lm.x * w, lm.y * h, lm.z * w])


# ---------------------------------------------------------------------------
# 核心：9 个 Blend Shape 参数提取
# ---------------------------------------------------------------------------

def extract_blend_shapes(landmarks, image_shape):
    """
    从 MediaPipe 468 关键点提取 9 个 Blend Shape 参数。
    返回值：dict，键为 BS_ 前缀的 Blend Shape 名称，值范围 [0, 1]，
    BS_BrowAngle 例外，范围 [-1, 1]。
    """
    h, w = image_shape[:2]

    def xy(idx):
        return get_landmark_xy(landmarks, idx, image_shape)

    result = {}

    # --- 1. 脸型宽高比 -> BS_FaceWidth ---
    face_width = distance(xy(234), xy(454))
    face_height = abs(xy(CHIN)[1] - xy(FOREHEAD)[1])
    ratio = face_width / max(face_height, 1)
    result['BS_FaceWidth'] = round(clamp((ratio - 0.55) / 0.25), 3)

    # --- 2. 脸颊饱满度 -> BS_CheekPuff ---
    cheek_width = distance(xy(LEFT_CHEEK), xy(RIGHT_CHEEK))
    zygo_width = distance(xy(LEFT_EYE_LEFT), xy(RIGHT_EYE_RIGHT))
    cheek_ratio = cheek_width / max(zygo_width, 1)
    result['BS_CheekPuff'] = round(clamp(cheek_ratio * 0.8), 3)

    # --- 3. 下巴尖度 -> BS_ChinPoint ---
    chin = xy(CHIN)
    v1 = xy(172) - chin
    v2 = xy(397) - chin
    cos_a = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-8)
    angle = np.arccos(clamp(cos_a, -1, 1)) * 180 / np.pi
    result['BS_ChinPoint'] = round(clamp((angle - 60) / 40), 3)

    # --- 4. 眼距 -> BS_EyeDistance ---
    eye_d = distance(xy(LEFT_EYE_INNER), xy(RIGHT_EYE_INNER))
    result['BS_EyeDistance'] = round(clamp((eye_d / max(face_width,1) - 0.15) / 0.20), 3)

    # --- 5. 眼大小 -> BS_EyeSize ---
    left_h = distance(xy(LEFT_EYE_TOP), xy(LEFT_EYE_BOTTOM))
    left_w = distance(xy(LEFT_EYE_LEFT), xy(LEFT_EYE_RIGHT))
    right_h = distance(xy(RIGHT_EYE_TOP), xy(RIGHT_EYE_BOTTOM))
    right_w = distance(xy(RIGHT_EYE_LEFT), xy(RIGHT_EYE_RIGHT))
    avg_ratio = ((left_h/max(left_w,1)) + (right_h/max(right_w,1))) / 2
    result['BS_EyeSize'] = round(clamp(avg_ratio * 3.0), 3)

    # --- 6. 嘴宽度 -> BS_MouthWidth ---
    mouth_w = distance(xy(MOUTH_LEFT), xy(MOUTH_RIGHT))
    result['BS_MouthWidth'] = round(clamp((mouth_w/max(face_width,1) - 0.15) / 0.25), 3)

    # --- 7. 嘴位置 -> BS_MouthHeight ---
    nose_y = xy(NOSE_TIP)[1]
    chin_y = xy(CHIN)[1]
    mouth_y = (xy(MOUTH_TOP)[1] + xy(MOUTH_BOTTOM)[1]) / 2
    r = abs(mouth_y - nose_y) / max(abs(chin_y - nose_y), 1)
    result['BS_MouthHeight'] = round(clamp((r - 0.30) / 0.25), 3)

    # --- 8. 眉毛粗细 -> BS_BrowThick ---
    lb = abs(xy(LEFT_BROW_TOP)[1] - xy(LEFT_BROW_BOTTOM)[1])
    rb = abs(xy(RIGHT_BROW_TOP)[1] - xy(RIGHT_BROW_BOTTOM)[1])
    result['BS_BrowThick'] = round(clamp(((lb+rb)/2) / max(face_height,1) * 30), 3)

    # --- 9. 眉毛角度 -> BS_BrowAngle (-1 ~ 1) ---
    li = xy(LEFT_EYE_INNER); lo = xy(LEFT_EYE_RIGHT)
    la = np.arctan2(lo[1]-li[1], lo[0]-li[0]) * 180 / np.pi
    ri = xy(RIGHT_EYE_INNER); ro = xy(RIGHT_EYE_LEFT)
    ra = np.arctan2(ro[1]-ri[1], ri[0]-ro[0]) * 180 / np.pi
    result['BS_BrowAngle'] = round(clamp((la+ra)/2 / 20, -1.0, 1.0), 3)

    return result


# ---------------------------------------------------------------------------
# 发型检测
# ---------------------------------------------------------------------------

def detect_hair(image_bgr, landmarks):
    h, w = image_bgr.shape[:2]
    fx = int(landmarks.landmark[FOREHEAD].x * w)
    fy = int(landmarks.landmark[FOREHEAD].y * h)
    hair_rect = (max(0, fx - int(w*0.25)), 0,
                 int(w*0.5), max(1, fy - 10))

    mask = np.zeros((h, w), np.uint8)
    bgd, fgd = np.zeros((1,65), np.float64), np.zeros((1,65), np.float64)
    try:
        cv2.grabCut(image_bgr, mask, hair_rect, bgd, fgd, 3, cv2.GC_INIT_WITH_RECT)
        hair_mask = np.where((mask==1)|(mask==3), 1, 0).astype('uint8')
    except Exception:
        hair_mask = np.zeros((h, w), np.uint8)

    hair_count = np.sum(hair_mask)
    area = max(1, hair_rect[2] * hair_rect[3])
    ratio = hair_count / area

    if ratio < 0.05:    style = 'hair_none'
    elif ratio < 0.15:  style = 'hair_short'
    elif ratio < 0.30:  style = 'hair_medium'
    else:               style = 'hair_long'

    if hair_count > 50:
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        avg = np.mean(rgb[hair_mask==1], axis=0)
    else:
        avg = np.array([60, 45, 30])

    color_hex = '#{:02X}{:02X}{:02X}'.format(
        int(clamp(avg[0],0,255)), int(clamp(avg[1],0,255)), int(clamp(avg[2],0,255)))

    return {'style': style, 'color_hex': color_hex}


# ---------------------------------------------------------------------------
# 肤色检测
# ---------------------------------------------------------------------------

def detect_skin_tone(image_bgr, landmarks):
    h, w = image_bgr.shape[:2]
    pixels = []
    for idx in [LEFT_CHEEK, RIGHT_CHEEK]:
        cx = int(landmarks.landmark[idx].x * w)
        cy = int(landmarks.landmark[idx].y * h)
        r = int(w * 0.03)
        for dy in range(-r, r+1):
            for dx in range(-r, r+1):
                px, py = cx+dx, cy+dy
                if 0 <= px < w and 0 <= py < h:
                    pixels.append(image_bgr[py, px])

    if not pixels:
        return {'tone': 'natural', 'color_hex': '#FDDCB5'}

    avg_bgr = np.mean(np.array(pixels, dtype=np.float32), axis=0)
    lum = 0.114*avg_bgr[0] + 0.587*avg_bgr[1] + 0.299*avg_bgr[2]

    if lum > 180:     tone = 'fair'
    elif lum > 130:   tone = 'natural'
    else:             tone = 'tan'

    rgb = cv2.cvtColor(np.uint8([[avg_bgr]]), cv2.COLOR_BGR2RGB)[0][0]
    color_hex = '#{:02X}{:02X}{:02X}'.format(
        int(clamp(rgb[0],0,255)), int(clamp(rgb[1],0,255)), int(clamp(rgb[2],0,255)))

    return {'tone': tone, 'color_hex': color_hex}


# ---------------------------------------------------------------------------
# 主处理函数
# ---------------------------------------------------------------------------

def process_image(image_bytes: bytes) -> dict:
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return {'code': 1, 'message': '无法解码图片'}

    h, w = img.shape[:2]
    max_dim = 1024
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        img = cv2.resize(img, (int(w*scale), int(h*scale)))

    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(rgb)

    if not results.multi_face_landmarks:
        return {'code': 1, 'message': '未检测到人脸，请重新拍照。确保光线充足、面部正对镜头。'}

    landmarks = results.multi_face_landmarks[0]

    return {
        'code': 0,
        'data': {
            'task_id': str(uuid.uuid4()),
            'blend_shapes': extract_blend_shapes(landmarks, img.shape),
            'hair': detect_hair(img, landmarks),
            'skin': detect_skin_tone(img, landmarks),
            'glasses': False,
            'confidence': 0.95
        }
    }


# ---------------------------------------------------------------------------
# Flask（本地调试）
# ---------------------------------------------------------------------------

try:
    from flask import Flask, request, jsonify
    app = Flask(__name__)

    @app.route('/api/v1/health', methods=['GET'])
    def health():
        return jsonify({'status': 'ok', 'version': '1.0.0'})

    @app.route('/api/v1/character/generate', methods=['POST'])
    def generate():
        t0 = time.time()
        if 'image' not in request.files:
            return jsonify({'code':1,'message':'请上传图片'}), 400
        f = request.files['image']
        b = f.read()
        if len(b) > 5*1024*1024:
            return jsonify({'code':1,'message':'图片不能超过5MB'}), 400
        result = process_image(b)
        result['elapsed_ms'] = round((time.time()-t0)*1000)
        return jsonify(result)

    if __name__ == '__main__':
        app.run(host='0.0.0.0', port=8080, debug=True)
except ImportError:
    pass


# ---------------------------------------------------------------------------
# 腾讯云 SCF 入口
# ---------------------------------------------------------------------------

def main_handler(event, context):
    t0 = time.time()
    try:
        body = event.get('body', '')
        if event.get('isBase64Encoded', False):
            image_bytes = base64.b64decode(body)
        else:
            image_bytes = body if isinstance(body, bytes) else body.encode('latin-1')

        result = process_image(image_bytes)
        result['elapsed_ms'] = round((time.time()-t0)*1000)
        return {
            'statusCode': 200 if result['code']==0 else 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(result, ensure_ascii=False)
        }
    except Exception as e:
        logger.exception("处理失败")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'code':2, 'message': f'服务器错误: {str(e)}',
                'elapsed_ms': round((time.time()-t0)*1000)
            }, ensure_ascii=False)
        }
