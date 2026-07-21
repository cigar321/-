# 犟种宝宝 — 云端 AI 服务部署指南

## 本地调试

```bash
cd server
pip install -r requirements.txt
python ai_service.py
# 服务启动在 http://localhost:8080
```

测试 API：

```bash
curl -X POST http://localhost:8080/api/v1/character/generate \
  -F "image=@test_photo.jpg"
```

## 腾讯云 SCF 部署

1. 在腾讯云控制台创建 SCF 函数，Runtime 选 Python 3.10
2. 将 `ai_service.py` 作为入口文件，入口函数设为 `main_handler`
3. 创建层（Layer）包含 MediaPipe + OpenCV 依赖（约 200MB）
4. 配置 API 网关触发器
5. 设置环境变量确保函数有足够内存（建议 1024MB）

## 阿里云函数计算部署

1. 使用 `fun` 或 Serverless Devs 工具
2. 将 `ai_service.py` + `requirements.txt` 部署为 HTTP 函数

## 冷启动优化

- MediaPipe 模型加载约需 3-5 秒（冷启动时）
- 建议设置预留实例（每月约 ¥50-100）来消除冷启动
- 或在非高峰时段定时触发 `/api/v1/health` 保持实例活跃
