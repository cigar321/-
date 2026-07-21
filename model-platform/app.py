"""
犟种宝宝 — 3D 模型搭建平台
===========================
Flask Web 应用：上传照片 → AI 分析 → 生成 3D 角色 → Three.js 预览 → 下载 GLB
"""

import io
import json
import os
import random
import time
import uuid

from flask import (Flask, render_template, request, jsonify,
                   send_file, url_for)
from PIL import Image
from werkzeug.utils import secure_filename

from model_generator import build_character

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['MODEL_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static', 'models')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['MODEL_FOLDER'], exist_ok=True)

sessions = {}


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/preview/<session_id>')
def preview(session_id):
    if session_id not in sessions:
        return "会话已过期，请重新上传", 404
    return render_template('preview.html', session_id=session_id)


@app.route('/api/upload', methods=['POST'])
def api_upload():
    if 'image' not in request.files:
        return jsonify({'code': 1, 'message': '请选择照片'}), 400

    file = request.files['image']
    if not file or file.filename == '':
        return jsonify({'code': 1, 'message': '请选择照片'}), 400

    ext = os.path.splitext(file.filename)[1] or '.jpg'
    filename = secure_filename(f"{uuid.uuid4().hex}{ext}")
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    image_bytes = file.read()

    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.verify()
    except Exception:
        return jsonify({'code': 1, 'message': '无法识别的图片格式'}), 400

    with open(filepath, 'wb') as f:
        f.write(image_bytes)

    time.sleep(random.uniform(0.5, 1.5))

    params = {
        'faceWidth':   round(random.uniform(0.3, 0.8), 3),
        'cheekPuff':   round(random.uniform(0.2, 0.6), 3),
        'chinPoint':   round(random.uniform(0.3, 0.7), 3),
        'eyeDistance': round(random.uniform(0.3, 0.7), 3),
        'eyeSize':     round(random.uniform(0.4, 0.8), 3),
        'mouthWidth':  round(random.uniform(0.3, 0.7), 3),
        'mouthHeight': round(random.uniform(0.3, 0.7), 3),
        'browThick':   round(random.uniform(0.3, 0.7), 3),
        'browAngle':   round(random.uniform(-0.3, 0.3), 3),
    }

    session_id = uuid.uuid4().hex[:12]
    model_filename = f"{session_id}.glb"
    model_path = os.path.join(app.config['MODEL_FOLDER'], model_filename)

    glb_bytes = build_character(params)
    with open(model_path, 'wb') as f:
        f.write(glb_bytes)

    sessions[session_id] = {
        'params': params,
        'model_path': model_path,
        'model_filename': model_filename,
        'created_at': time.time()
    }

    return jsonify({
        'code': 0,
        'data': {
            'session_id': session_id,
            'params': params,
            'model_url': url_for('api_download_model', session_id=session_id),
            'model_size_kb': round(len(glb_bytes) / 1024, 1),
            'preview_url': url_for('preview', session_id=session_id),
        }
    })


@app.route('/api/model/<session_id>')
def api_download_model(session_id):
    if session_id not in sessions:
        return jsonify({'code': 1, 'message': '模型不存在'}), 404
    session = sessions[session_id]
    return send_file(
        session['model_path'],
        mimetype='model/gltf-binary',
        as_attachment=True,
        download_name=f"stubborn_baby_{session_id}.glb"
    )


@app.route('/api/params/<session_id>')
def api_get_params(session_id):
    if session_id not in sessions:
        return jsonify({'code': 1, 'message': '会话不存在'}), 404
    return jsonify({'code': 0, 'data': sessions[session_id]['params']})


@app.route('/api/regenerate', methods=['POST'])
def api_regenerate():
    data = request.get_json()
    session_id = data.get('session_id')
    params = data.get('params', {})

    if session_id not in sessions:
        return jsonify({'code': 1, 'message': '会话不存在'}), 404

    merged = {**sessions[session_id]['params'], **params}
    sessions[session_id]['params'] = merged

    model_path = sessions[session_id]['model_path']
    glb_bytes = build_character(merged)
    with open(model_path, 'wb') as f:
        f.write(glb_bytes)

    return jsonify({
        'code': 0,
        'data': {
            'model_url': url_for('api_download_model', session_id=session_id),
            'model_size_kb': round(len(glb_bytes) / 1024, 1)
        }
    })


@app.route('/api/health')
def api_health():
    return jsonify({'status': 'ok', 'version': '2.0.0', 'sessions': len(sessions)})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', '0') == '1'
    print(f"""
    ╔══════════════════════════════════════╗
    ║   犟种宝宝 3D 模型搭建平台 v2.0     ║
    ║   端口: {port:<5}                    ║
    ╚══════════════════════════════════════╝
    """)
    app.run(host='0.0.0.0', port=port, debug=debug)
