"""
犟种宝宝 — 程序化 3D 角色模型生成器
=====================================
纯 Python 实现，零外部 3D 库依赖。
根据面部参数程序化创建 Q 版角色 GLB 模型。

GLB 格式: [12B header] [JSON chunk] [BIN chunk]
"""

import struct
import json
import math
import numpy as np


class MeshData:
    """原始网格数据容器"""
    def __init__(self):
        self.positions = []   # [x,y,z, x,y,z, ...] flat float32
        self.normals = []     # flat float32
        self.indices = []     # flat uint16
        self.min_pos = [float('inf')] * 3
        self.max_pos = [float('-inf')] * 3

    def add_triangle(self, v0, v1, v2):
        """添加一个三角形面"""
        n = len(self.positions) // 3
        self.indices.extend([n, n+1, n+2])

        for v in [v0, v1, v2]:
            self.positions.extend(v)
            for i in range(3):
                self.min_pos[i] = min(self.min_pos[i], v[i])
                self.max_pos[i] = max(self.max_pos[i], v[i])

        # 计算法线
        a = np.array(v1) - np.array(v0)
        b = np.array(v2) - np.array(v0)
        normal = np.cross(a, b)
        norm = np.linalg.norm(normal)
        if norm > 0:
            normal = normal / norm
        else:
            normal = np.array([0, 1, 0])
        for _ in range(3):
            self.normals.extend(normal.tolist())

    def merge(self, other):
        """合并另一个网格"""
        offset = len(self.positions) // 3
        self.positions.extend(other.positions)
        self.normals.extend(other.normals)
        for idx in other.indices:
            self.indices.append(idx + offset)
        for i in range(3):
            self.min_pos[i] = min(self.min_pos[i], other.min_pos[i])
            self.max_pos[i] = max(self.max_pos[i], other.max_pos[i])


def create_uv_sphere(radius, segments=12, rings=8):
    """创建 UV 球体网格"""
    mesh = MeshData()
    verts = []
    for r in range(rings + 1):
        phi = math.pi * r / rings
        ring_verts = []
        for s in range(segments + 1):
            theta = 2 * math.pi * s / segments
            x = radius * math.sin(phi) * math.cos(theta)
            y = radius * math.cos(phi)
            z = radius * math.sin(phi) * math.sin(theta)
            ring_verts.append((x, y, z))
        verts.append(ring_verts)
    for r in range(rings):
        for s in range(segments):
            mesh.add_triangle(verts[r][s], verts[r+1][s], verts[r][s+1])
            mesh.add_triangle(verts[r+1][s], verts[r+1][s+1], verts[r][s+1])
    return mesh


def create_cylinder(radius, height, segments=8, offset=(0, 0, 0)):
    """创建圆柱体"""
    mesh = MeshData()
    ox, oy, oz = offset
    half_h = height / 2
    top_center = (ox, oy + half_h, oz)
    bottom_center = (ox, oy - half_h, oz)
    top_ring = []
    bottom_ring = []
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        x = ox + radius * math.cos(angle)
        z = oz + radius * math.sin(angle)
        top_ring.append((x, oy + half_h, z))
        bottom_ring.append((x, oy - half_h, z))
    for i in range(segments):
        j = (i + 1) % segments
        # 侧面
        mesh.add_triangle(top_ring[i], bottom_ring[i], top_ring[j])
        mesh.add_triangle(bottom_ring[i], bottom_ring[j], top_ring[j])
        # 顶面
        mesh.add_triangle(top_center, top_ring[j], top_ring[i])
        # 底面
        mesh.add_triangle(bottom_center, bottom_ring[i], bottom_ring[j])
    return mesh


def create_rounded_box(w, h, d, offset=(0, 0, 0)):
    """创建圆角立方体（简化：普通立方体）"""
    mesh = MeshData()
    ox, oy, oz = offset
    hw, hh, hd = w/2, h/2, d/2
    verts = [
        (-hw+ox, -hh+oy, -hd+oz), ( hw+ox, -hh+oy, -hd+oz),
        ( hw+ox,  hh+oy, -hd+oz), (-hw+ox,  hh+oy, -hd+oz),
        (-hw+ox, -hh+oy,  hd+oz), ( hw+ox, -hh+oy,  hd+oz),
        ( hw+ox,  hh+oy,  hd+oz), (-hw+ox,  hh+oy,  hd+oz),
    ]
    faces = [
        (0,1,2,3), (4,7,6,5), (0,4,5,1),
        (1,5,6,2), (2,6,7,3), (3,7,4,0),
    ]
    for f in faces:
        mesh.add_triangle(verts[f[0]], verts[f[1]], verts[f[2]])
        mesh.add_triangle(verts[f[0]], verts[f[2]], verts[f[3]])
    return mesh


def create_cone(radius, height, segments=8, offset=(0, 0, 0)):
    """创建圆锥体"""
    mesh = MeshData()
    ox, oy, oz = offset
    half_h = height / 2
    tip = (ox, oy + half_h, oz)
    base_center = (ox, oy - half_h, oz)
    base_ring = []
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        x = ox + radius * math.cos(angle)
        z = oz + radius * math.sin(angle)
        base_ring.append((x, oy - half_h, z))
    for i in range(segments):
        j = (i + 1) % segments
        mesh.add_triangle(tip, base_ring[i], base_ring[j])
        mesh.add_triangle(base_center, base_ring[j], base_ring[i])
    return mesh


# ═══════════════════════════════════════════════════════
# GLB 导出
# ═══════════════════════════════════════════════════════

def pad_to_4(value):
    return (value + 3) & ~3


def build_glb(primitive_meshes, primitive_names):
    """
    primitive_meshes: list of MeshData
    primitive_names: list of str, same length
    返回 bytes (完整的 .glb 文件)
    """
    # 合并所有网格到一个 buffer
    all_positions = b''
    all_normals = b''
    all_indices = b''

    buffer_views = []
    accessors = []
    meshes_json = []
    nodes_json = []

    byte_offset = 0

    # 全局 min/max
    global_min = [float('inf')] * 3
    global_max = [float('-inf')] * 3

    for pi, (mesh, name) in enumerate(zip(primitive_meshes, primitive_names)):
        # positions
        pos_bytes = struct.pack(f'<{len(mesh.positions)}f', *mesh.positions)
        pos_bytes = pos_bytes + b'\x00' * (pad_to_4(len(pos_bytes)) - len(pos_bytes))

        pos_bv_idx = len(buffer_views)
        buffer_views.append({
            "buffer": 0, "byteOffset": byte_offset,
            "byteLength": len(pos_bytes), "target": 34962
        })
        pos_acc_idx = len(accessors)
        accessors.append({
            "bufferView": pos_bv_idx, "componentType": 5126,
            "count": len(mesh.positions) // 3, "type": "VEC3",
            "max": mesh.max_pos, "min": mesh.min_pos
        })
        byte_offset += len(pos_bytes)

        # normals
        norm_bytes = struct.pack(f'<{len(mesh.normals)}f', *mesh.normals)
        norm_bytes = norm_bytes + b'\x00' * (pad_to_4(len(norm_bytes)) - len(norm_bytes))

        norm_bv_idx = len(buffer_views)
        buffer_views.append({
            "buffer": 0, "byteOffset": byte_offset,
            "byteLength": len(norm_bytes), "target": 34962
        })
        norm_acc_idx = len(accessors)
        accessors.append({
            "bufferView": norm_bv_idx, "componentType": 5126,
            "count": len(mesh.normals) // 3, "type": "VEC3"
        })
        byte_offset += len(norm_bytes)

        # indices
        idx_bytes = struct.pack(f'<{len(mesh.indices)}H', *mesh.indices)
        idx_bytes = idx_bytes + b'\x00' * (pad_to_4(len(idx_bytes)) - len(idx_bytes))

        idx_bv_idx = len(buffer_views)
        buffer_views.append({
            "buffer": 0, "byteOffset": byte_offset,
            "byteLength": len(idx_bytes), "target": 34963
        })
        idx_acc_idx = len(accessors)
        accessors.append({
            "bufferView": idx_bv_idx, "componentType": 5123,
            "count": len(mesh.indices), "type": "SCALAR"
        })
        byte_offset += len(idx_bytes)

        # 更新全局 min/max
        for i in range(3):
            global_min[i] = min(global_min[i], mesh.min_pos[i])
            global_max[i] = max(global_max[i], mesh.max_pos[i])

        # mesh + node
        meshes_json.append({
            "name": name,
            "primitives": [{
                "attributes": {
                    "POSITION": pos_acc_idx,
                    "NORMAL": norm_acc_idx
                },
                "indices": idx_acc_idx,
                "material": pi,
                "mode": 4
            }]
        })
        nodes_json.append({
            "mesh": pi,
            "name": name
        })

    # 构建完整的 GLTF JSON
    gltf = {
        "asset": {"version": "2.0", "generator": "犟种宝宝 Model Builder"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes_json)))}],
        "nodes": nodes_json,
        "meshes": meshes_json,
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": byte_offset}],
        "materials": [
            # 为每个 primitive 创建材质（颜色不同）
            {
                "name": "head_material",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [1.0, 0.85, 0.75, 1.0],  # 肤色
                    "metallicFactor": 0, "roughnessFactor": 0.8
                }
            },
            {
                "name": "body_material",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [0.35, 0.35, 0.4, 1.0],  # 灰色西装
                    "metallicFactor": 0, "roughnessFactor": 0.7
                }
            },
            {
                "name": "eye_material",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [0.1, 0.1, 0.1, 1.0],    # 黑色眼睛
                    "metallicFactor": 0.1, "roughnessFactor": 0.3
                }
            },
            {
                "name": "mouth_material",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [0.8, 0.3, 0.3, 1.0],    # 红嘴巴
                    "metallicFactor": 0, "roughnessFactor": 0.5
                }
            },
            {
                "name": "limb_material",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [0.35, 0.35, 0.4, 1.0],
                    "metallicFactor": 0, "roughnessFactor": 0.7
                }
            },
            {
                "name": "cheek_material",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [1.0, 0.6, 0.6, 1.0],    # 粉色腮红
                    "metallicFactor": 0, "roughnessFactor": 0.6
                }
            },
        ]
    }

    json_str = json.dumps(gltf, separators=(',', ':'))
    json_bytes = json_str.encode('utf-8')
    json_bytes = json_bytes + b'\x20' * (pad_to_4(len(json_bytes)) - len(json_bytes))

    # 组装 buffer
    buffer_data = bytearray()
    for mesh in primitive_meshes:
        pos_bytes = struct.pack(f'<{len(mesh.positions)}f', *mesh.positions)
        buffer_data.extend(pos_bytes)
        buffer_data.extend(b'\x00' * (pad_to_4(len(pos_bytes)) - len(pos_bytes)))
        norm_bytes = struct.pack(f'<{len(mesh.normals)}f', *mesh.normals)
        buffer_data.extend(norm_bytes)
        buffer_data.extend(b'\x00' * (pad_to_4(len(norm_bytes)) - len(norm_bytes)))
        idx_bytes = struct.pack(f'<{len(mesh.indices)}H', *mesh.indices)
        buffer_data.extend(idx_bytes)
        buffer_data.extend(b'\x00' * (pad_to_4(len(idx_bytes)) - len(idx_bytes)))

    # GLB header
    total_length = 12 + 8 + len(json_bytes) + 8 + len(buffer_data)
    header = struct.pack('<I', 0x46546C67)  # magic
    header += struct.pack('<I', 2)           # version
    header += struct.pack('<I', total_length) # total length

    # JSON chunk
    json_chunk = struct.pack('<I', len(json_bytes))
    json_chunk += struct.pack('<I', 0x4E4F534A)
    json_chunk += json_bytes

    # BIN chunk
    bin_chunk = struct.pack('<I', len(buffer_data))
    bin_chunk += struct.pack('<I', 0x004E4942)
    bin_chunk += bytes(buffer_data)

    return header + json_chunk + bin_chunk


# ═══════════════════════════════════════════════════════
# 角色构建
# ═══════════════════════════════════════════════════════

def build_character(params: dict) -> bytes:
    """
    根据面部参数构建 3D 角色模型，返回 GLB bytes。

    params 包含：
      faceWidth, cheekPuff, chinPoint, eyeDistance, eyeSize,
      mouthWidth, mouthHeight, browThick, browAngle
      每个值范围 0~1
    """
    fw = params.get('faceWidth', 0.5)
    cp = params.get('cheekPuff', 0.4)
    chin = params.get('chinPoint', 0.5)
    eye_dist = params.get('eyeDistance', 0.5)
    eye_size = params.get('eyeSize', 0.6)
    mouth_w = params.get('mouthWidth', 0.5)
    mouth_h = params.get('mouthHeight', 0.5)

    primitives = []
    names = []

    # ── 1. 头部（球体，受脸型参数影响） ──
    head_radius_x = 0.5 + fw * 0.25       # 0.5 ~ 0.75 (脸宽)
    head_radius_y = 0.55
    head_radius_z = 0.45 + cp * 0.2       # 脸颊饱满度影响深度

    # 创建椭圆头（用球体 + 非均匀缩放模拟）
    head = create_uv_sphere(radius=1.0, segments=20, rings=14)
    # 对顶点做非均匀缩放
    for i in range(0, len(head.positions), 3):
        head.positions[i]   *= head_radius_x      # X
        head.positions[i+1] *= head_radius_y * (1.0 - chin * 0.1)  # Y (下巴影响)
        head.positions[i+2] *= head_radius_z      # Z
    # 上移头部
    for i in range(1, len(head.positions), 3):
        head.positions[i] += 1.6
    primitives.append(head)
    names.append("head")

    # ── 2. 身体（圆角立方体） ──
    body = create_rounded_box(0.55, 0.7, 0.35, offset=(0, 0.95, 0))
    primitives.append(body)
    names.append("body")

    # ── 3. 左眼（小球体） ──
    eye_r = 0.07 + eye_size * 0.06       # 0.07 ~ 0.13
    eye_x = 0.15 + eye_dist * 0.1        # 眼距
    left_eye = create_uv_sphere(eye_r, segments=10, rings=6)
    for i in range(0, len(left_eye.positions), 3):
        left_eye.positions[i] -= eye_x   # 左移
        left_eye.positions[i+1] += 1.72  # 上移到眼睛位置
        left_eye.positions[i+2] += 0.3
    primitives.append(left_eye)
    names.append("left_eye")

    # ── 4. 右眼 ──
    right_eye = create_uv_sphere(eye_r, segments=10, rings=6)
    for i in range(0, len(right_eye.positions), 3):
        right_eye.positions[i] += eye_x
        right_eye.positions[i+1] += 1.72
        right_eye.positions[i+2] += 0.3
    primitives.append(right_eye)
    names.append("right_eye")

    # ── 5. 嘴巴（小扁立方体） ──
    mw = 0.08 + mouth_w * 0.12
    mouth = create_rounded_box(mw, 0.02, 0.03,
                                offset=(0, 1.55 - mouth_h * 0.15, 0.35))
    primitives.append(mouth)
    names.append("mouth")

    # ── 6. 左臂 ──
    left_arm = create_cylinder(0.08, 0.5, offset=(-0.4, 1.3, 0))
    primitives.append(left_arm)
    names.append("left_arm")

    # ── 7. 右臂 ──
    right_arm = create_cylinder(0.08, 0.5, offset=(0.4, 1.3, 0))
    primitives.append(right_arm)
    names.append("right_arm")

    # ── 8. 左腿 ──
    left_leg = create_cylinder(0.09, 0.45, offset=(-0.15, 0.45, 0))
    primitives.append(left_leg)
    names.append("left_leg")

    # ── 9. 右腿 ──
    right_leg = create_cylinder(0.09, 0.45, offset=(0.15, 0.45, 0))
    primitives.append(right_leg)
    names.append("right_leg")

    # ── 10. 左腮红 ──
    left_cheek = create_uv_sphere(0.06, segments=8, rings=4)
    for i in range(0, len(left_cheek.positions), 3):
        left_cheek.positions[i] -= 0.25
        left_cheek.positions[i+1] += 1.58
        left_cheek.positions[i+2] += 0.28
    primitives.append(left_cheek)
    names.append("left_cheek")

    # ── 11. 右腮红 ──
    right_cheek = create_uv_sphere(0.06, segments=8, rings=4)
    for i in range(0, len(right_cheek.positions), 3):
        right_cheek.positions[i] += 0.25
        right_cheek.positions[i+1] += 1.58
        right_cheek.positions[i+2] += 0.28
    primitives.append(right_cheek)
    names.append("right_cheek")

    return build_glb(primitives, names)
