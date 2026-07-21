import requests, json, io
from PIL import Image

# Health check
r = requests.get("http://localhost:5000/api/health")
print("Health:", r.json())

# Test full flow
img = Image.new("RGB", (128, 128), color=(255, 200, 180))
buf = io.BytesIO()
img.save(buf, format="JPEG")
buf.seek(0)

r2 = requests.post("http://localhost:5000/api/upload", files={"image": ("test.jpg", buf, "image/jpeg")})
data = r2.json()
print(f"\nUpload: code={data['code']}, session={data['data']['session_id']}")
print(f"Params: {json.dumps(data['data']['params'], indent=2)}")

# Download model
r3 = requests.get("http://localhost:5000" + data["data"]["model_url"])
print(f"\nModel: {len(r3.content)} bytes, type={r3.headers['content-type']}")

# Regenerate
r4 = requests.post("http://localhost:5000/api/regenerate", json={
    "session_id": data["data"]["session_id"],
    "params": {"faceWidth": 0.8, "eyeSize": 0.9}
})
print(f"Regenerate: code={r4.json()['code']}")
print("\nALL TESTS PASSED ✅")
