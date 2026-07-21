// 犟种宝宝 — 上传页脚本

const uploadZone = document.getElementById('uploadZone');
const fileInput = document.getElementById('fileInput');
const previewImage = document.getElementById('previewImage');
const progressSection = document.getElementById('progressSection');
const progressSub = document.getElementById('progressSub');
const resultSection = document.getElementById('resultSection');
const resultParams = document.getElementById('resultParams');
const btnPreview = document.getElementById('btnPreview');
const btnDownload = document.getElementById('btnDownload');
const toast = document.getElementById('toast');

let currentSessionId = null;

// ── 上传触发 ──
uploadZone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', (e) => {
    if (e.target.files[0]) handleFile(e.target.files[0]);
});

// ── 拖拽 ──
uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.classList.add('drag-over');
});
uploadZone.addEventListener('dragleave', () => {
    uploadZone.classList.remove('drag-over');
});
uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('drag-over');
    if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
});

// ── 粘贴 ──
document.addEventListener('paste', (e) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of items) {
        if (item.type.startsWith('image/')) {
            handleFile(item.getAsFile());
            break;
        }
    }
});

// ── 核心流程 ──
async function handleFile(file) {
    // 验证
    if (!file.type.startsWith('image/')) {
        showToast('请选择图片文件');
        return;
    }
    if (file.size > 10 * 1024 * 1024) {
        showToast('图片不能超过 10MB');
        return;
    }

    // 预览
    const reader = new FileReader();
    reader.onload = (e) => {
        previewImage.src = e.target.result;
        previewImage.style.display = 'block';
    };
    reader.readAsDataURL(file);

    // 隐藏上传区，显示进度
    uploadZone.style.display = 'none';
    progressSection.classList.add('active');
    resultSection.classList.remove('active');

    // 上传
    const formData = new FormData();
    formData.append('image', file);

    const steps = [
        '检测人脸特征点...',
        '分析脸型与五官...',
        '映射 Q 版参数...',
        '生成 3D 模型网格...',
    ];
    let stepIdx = 0;
    const stepInterval = setInterval(() => {
        progressSub.textContent = steps[stepIdx % steps.length];
        stepIdx++;
    }, 800);

    try {
        const resp = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        clearInterval(stepInterval);

        const data = await resp.json();
        if (data.code !== 0) {
            showToast(data.message || '处理失败');
            resetForm();
            return;
        }

        // 显示结果
        currentSessionId = data.data.session_id;
        showResult(data.data);

    } catch (err) {
        clearInterval(stepInterval);
        showToast('网络错误，请重试');
        resetForm();
    }
}

function showResult(data) {
    progressSection.classList.remove('active');
    resultSection.classList.add('active');

    // 参数展示
    const p = data.params;
    resultParams.innerHTML = Object.entries(p).map(([k, v]) =>
        `<div class="param-row"><span class="label">${k}</span><span class="value">${v}</span></div>`
    ).join('');

    // 按钮链接
    btnPreview.href = data.preview_url;
    btnDownload.href = data.model_url;
}

function resetForm() {
    uploadZone.style.display = '';
    previewImage.style.display = 'none';
    progressSection.classList.remove('active');
    resultSection.classList.remove('active');
    fileInput.value = '';
    currentSessionId = null;
}

function showToast(msg) {
    toast.textContent = msg;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 2500);
}
