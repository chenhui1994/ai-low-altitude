"""
北斗三维网格位置码 3D 网格生成引擎 — 可参数化的生成核心
基于 GB/T 39409-2020《北斗网格位置码》国家标准

将所有 3D OBJ 生成逻辑从 generate_beidou_3d_obj.py 中提取出来，
接受 beidou_params.BeiDou3DConfig 对象控制所有参数。
支持进度回调和取消（通过 threading.Event）。
不依赖 PySide6。
"""

import math
import os
import threading

from pyproj import Transformer

from beidou_params import (
    BeiDou3DConfig,
    BeiDou2DConfig,
    LEVEL_SIZES,
    LEVEL_LABELS,
)
from beidou_grid_engine import (
    encode_level1,
    encode_level2,
    encode_level3,
    encode_level4,
    compute_full_code,
    get_generation_bounds,
)


# ============================================================
# 坐标投影转换
# ============================================================

def lonlat_to_projected(lon, lat, transformer):
    """
    将经纬度转换为投影坐标。

    lon: 经度 (度)
    lat: 纬度 (度)
    transformer: pyproj Transformer 对象
    返回: (easting, northing) 单位为米
    """
    easting, northing = transformer.transform(lon, lat)
    return easting, northing


# ============================================================
# 3D 生成范围计算 (直接复用2D网格的范围逻辑)
# ============================================================

def get_3d_generation_bounds(level, config_2d):
    """
    计算3D网格生成的水平范围。
    直接使用2D网格的范围计算逻辑，保持地理覆盖一致。

    level: 网格级别 (1-7)
    config_2d: BeiDou2DConfig
    """
    return get_generation_bounds(level, config_2d)


# ============================================================
# 网格生成（复用2D逻辑 + 高度层）
# ============================================================

def generate_2d_cells(level, config, bounds):
    """
    生成指定范围内某级的所有2D网格单元。

    level: 网格级别 (1-7)
    config: BeiDou3DConfig
    bounds: (west, east, south, north)
    返回: [(grid_code, west, east, south, north), ...]
    """
    bounds_w, bounds_e, bounds_s, bounds_n = bounds
    cell_lon, cell_lat = LEVEL_SIZES[level]
    cells = []

    if level <= 4:
        # 对于 Level 1-4, 使用逐级细化方式
        # Level 1
        l1_cells = []
        for lon_band in range(1, 61):
            l1_w = (lon_band - 1) * 6 - 180
            l1_e = l1_w + 6
            if l1_e <= bounds_w or l1_w >= bounds_e:
                continue
            for lat_band in range(22):
                l1_s = lat_band * 4
                l1_n = l1_s + 4
                if l1_n <= bounds_s or l1_s >= bounds_n:
                    continue
                code = encode_level1(lon_band, lat_band, 'N')
                l1_cells.append((code, l1_w, l1_e, l1_s, l1_n))

        if level == 1:
            return l1_cells

        # Level 2
        l2_cells = []
        for p_code, p_w, p_e, p_s, p_n in l1_cells:
            for col in range(12):
                c_w = p_w + col * LEVEL_SIZES[2][0]
                c_e = c_w + LEVEL_SIZES[2][0]
                if c_e <= bounds_w or c_w >= bounds_e:
                    continue
                for row in range(8):
                    c_s = p_s + row * LEVEL_SIZES[2][1]
                    c_n = c_s + LEVEL_SIZES[2][1]
                    if c_n <= bounds_s or c_s >= bounds_n:
                        continue
                    code = p_code + encode_level2(col, row)
                    l2_cells.append((code, c_w, c_e, c_s, c_n))

        if level == 2:
            return l2_cells

        # Level 3
        l3_cells = []
        for p_code, p_w, p_e, p_s, p_n in l2_cells:
            for col in range(2):
                c_w = p_w + col * LEVEL_SIZES[3][0]
                c_e = c_w + LEVEL_SIZES[3][0]
                if c_e <= bounds_w or c_w >= bounds_e:
                    continue
                for row in range(3):
                    c_s = p_s + row * LEVEL_SIZES[3][1]
                    c_n = c_s + LEVEL_SIZES[3][1]
                    if c_n <= bounds_s or c_s >= bounds_n:
                        continue
                    code = p_code + encode_level3(col, row)
                    l3_cells.append((code, c_w, c_e, c_s, c_n))

        if level == 3:
            return l3_cells

        # Level 4
        l4_cells = []
        for p_code, p_w, p_e, p_s, p_n in l3_cells:
            for col in range(15):
                c_w = p_w + col * LEVEL_SIZES[4][0]
                c_e = c_w + LEVEL_SIZES[4][0]
                if c_e <= bounds_w or c_w >= bounds_e:
                    continue
                for row in range(10):
                    c_s = p_s + row * LEVEL_SIZES[4][1]
                    c_n = c_s + LEVEL_SIZES[4][1]
                    if c_n <= bounds_s or c_s >= bounds_n:
                        continue
                    code = p_code + encode_level4(col, row)
                    l4_cells.append((code, c_w, c_e, c_s, c_n))

        return l4_cells

    else:
        # Level 5-7: 直接使用 compute_full_code
        lon = bounds_w
        while lon < bounds_e:
            lat = bounds_s
            while lat < bounds_n:
                center_lon = lon + cell_lon / 2
                center_lat = lat + cell_lat / 2
                code, g_w, g_e, g_s, g_n = compute_full_code(center_lon, center_lat, level)
                cells.append((code, g_w, g_e, g_s, g_n))
                lat += cell_lat
            lon += cell_lon

        # 去重
        seen = set()
        unique_cells = []
        for cell in cells:
            if cell[0] not in seen:
                seen.add(cell[0])
                unique_cells.append(cell)
        return unique_cells


# ============================================================
# 3D 盒体顶点生成
# ============================================================

def generate_box_vertices(west, east, south, north, h_bottom, h_top, transformer):
    """
    生成一个六面体的8个投影坐标顶点。
    底面4个点 + 顶面4个点。

    west, east, south, north: 地理边界 (度)
    h_bottom, h_top: 高度边界 (米)
    transformer: pyproj Transformer 对象
    返回: [(easting, northing, height), ...] 共8个顶点
          顺序: SW底, SE底, NE底, NW底, SW顶, SE顶, NE顶, NW顶
    """
    # 投影4个角点 (只需投影4个唯一的经纬度位置)
    sw_e, sw_n = lonlat_to_projected(west, south, transformer)
    se_e, se_n = lonlat_to_projected(east, south, transformer)
    ne_e, ne_n = lonlat_to_projected(east, north, transformer)
    nw_e, nw_n = lonlat_to_projected(west, north, transformer)

    # 底面: SW, SE, NE, NW (+ h_bottom)
    v1 = (sw_e, sw_n, h_bottom)
    v2 = (se_e, se_n, h_bottom)
    v3 = (ne_e, ne_n, h_bottom)
    v4 = (nw_e, nw_n, h_bottom)
    # 顶面: SW, SE, NE, NW (+ h_top)
    v5 = (sw_e, sw_n, h_top)
    v6 = (se_e, se_n, h_top)
    v7 = (ne_e, ne_n, h_top)
    v8 = (nw_e, nw_n, h_top)

    return [v1, v2, v3, v4, v5, v6, v7, v8]


# ============================================================
# 高度域编码
# ============================================================

def generate_height_code(layer_idx, level):
    """
    生成高度域编码。
    简化规则：方向标识(0=地上) + 层索引编码

    layer_idx: 高度层索引
    level: 网格级别
    """
    return f"0{layer_idx:02X}"


# ============================================================
# OBJ 文件写入
# ============================================================

def write_obj_file(cells_3d, filepath, level, bounds, height_layers, config, mtl_filename):
    """
    将3D网格单元写入OBJ文件（半透明面 + 框线边）。
    每个网格体输出6个面(face) + 12条边线(line)。

    cells_3d: [(grid_code_3d, vertices_8), ...]
    filepath: 输出 OBJ 文件路径
    level: 网格级别
    bounds: (west, east, south, north)
    height_layers: [(h_bottom, h_top), ...]
    config: BeiDou3DConfig
    mtl_filename: 对应的 MTL 文件名
    """
    with open(filepath, 'w') as f:
        # 文件头注释
        f.write(f"# BeiDou 3D Grid - Level {level}\n")
        f.write(f"# Standard: GB/T 39409-2020\n")
        f.write(f"# Coordinate System: CGCS2000 / 3-degree Gauss-Kruger CM 114E (EPSG:4547)\n")
        f.write(f"# X = Easting (m), Y = Northing (m), Z = Height (m)\n")
        f.write(f"# Geographic Bounds: {bounds[0]:.6f}-{bounds[1]:.6f}E, {bounds[2]:.6f}-{bounds[3]:.6f}N\n")
        f.write(f"# Height Range: {config.h_min:.1f}-{config.h_max:.1f} m\n")
        f.write(f"# Height Layers: {len(height_layers)}\n")
        f.write(f"# Total Cells: {len(cells_3d)}\n")
        f.write(f"# Height Resolution: {config.get_height_resolution(level):.1f} m\n")
        f.write(f"# Geometry: Semi-transparent faces + wireframe edges\n")
        f.write(f"#\n")

        # 材质库引用
        f.write(f"mtllib {mtl_filename}\n")
        f.write(f"usemtl grid_cell\n\n")

        vertex_offset = 0

        for grid_code, vertices in cells_3d:
            # 分组
            f.write(f"g {grid_code}\n")

            # 写入8个顶点 (easting, northing, height)
            for vx, vy, vz in vertices:
                f.write(f"v {vx:.3f} {vy:.3f} {vz:.3f}\n")

            # 写入6个面 (CCW winding, outward normals)
            # 顶点编号: 1=SW底, 2=SE底, 3=NE底, 4=NW底, 5=SW顶, 6=SE顶, 7=NE顶, 8=NW顶
            base = vertex_offset + 1
            # 底面 (法线朝下): f 4 3 2 1
            f.write(f"f {base+3} {base+2} {base+1} {base}\n")
            # 顶面 (法线朝上): f 5 6 7 8
            f.write(f"f {base+4} {base+5} {base+6} {base+7}\n")
            # 南面 (法线朝南): f 1 2 6 5
            f.write(f"f {base} {base+1} {base+5} {base+4}\n")
            # 北面 (法线朝北): f 3 4 8 7
            f.write(f"f {base+2} {base+3} {base+7} {base+6}\n")
            # 西面 (法线朝西): f 4 1 5 8
            f.write(f"f {base+3} {base} {base+4} {base+7}\n")
            # 东面 (法线朝东): f 2 3 7 6
            f.write(f"f {base+1} {base+2} {base+6} {base+5}\n")

            # 写入12条边线
            # 底面4条边
            f.write(f"l {base} {base+1}\n")
            f.write(f"l {base+1} {base+2}\n")
            f.write(f"l {base+2} {base+3}\n")
            f.write(f"l {base+3} {base}\n")
            # 顶面4条边
            f.write(f"l {base+4} {base+5}\n")
            f.write(f"l {base+5} {base+6}\n")
            f.write(f"l {base+6} {base+7}\n")
            f.write(f"l {base+7} {base+4}\n")
            # 垂直4条边
            f.write(f"l {base} {base+4}\n")
            f.write(f"l {base+1} {base+5}\n")
            f.write(f"l {base+2} {base+6}\n")
            f.write(f"l {base+3} {base+7}\n")

            vertex_offset += 8


# ============================================================
# MTL 材质文件写入
# ============================================================

def write_mtl_file(filepath, config):
    """
    生成 MTL 材质文件。

    filepath: 输出 MTL 文件路径
    config: BeiDou3DConfig
    """
    with open(filepath, 'w') as f:
        f.write("# BeiDou 3D Grid Material\n")
        f.write("# Semi-transparent for 3D visualization\n\n")
        f.write("newmtl grid_cell\n")
        f.write(f"Ka {config.mtl_ka_r} {config.mtl_ka_g} {config.mtl_ka_b}\n")
        f.write(f"Kd {config.mtl_kd_r} {config.mtl_kd_g} {config.mtl_kd_b}\n")
        f.write(f"Ks {config.mtl_ks_r} {config.mtl_ks_g} {config.mtl_ks_b}\n")
        f.write(f"Ns {config.mtl_ns}\n")
        f.write(f"d {config.mtl_d}\n")
        f.write(f"illum {config.mtl_illum}\n")


# ============================================================
# 单级 3D 网格生成
# ============================================================

def generate_level_3d(level, config, transformer):
    """
    生成某级的所有3D网格单元。

    level: 网格级别 (1-7)
    config: BeiDou3DConfig
    transformer: pyproj Transformer 对象
    返回: (cells_3d, bounds, height_layers)
    """
    # 创建 BeiDou2DConfig 用于范围计算
    config_2d = BeiDou2DConfig(
        west=config.west,
        east=config.east,
        south=config.south,
        north=config.north,
        center_lon=config.center_lon,
        center_lat=config.center_lat,
    )

    # 获取生成范围
    bounds = get_3d_generation_bounds(level, config_2d)

    # 获取高度层
    height_layers = config.get_height_layers(level)

    # 生成2D网格
    cells_2d = generate_2d_cells(level, config, bounds)

    # 组合2D网格 × 高度层 = 3D网格
    cells_3d = []
    for grid_code_2d, west, east, south, north in cells_2d:
        for layer_idx, (h_bottom, h_top) in enumerate(height_layers):
            # 3D编码 = 2D编码 + 高度域编码
            h_code = generate_height_code(layer_idx, level)
            grid_code_3d = f"{grid_code_2d}-{h_code}"

            # 生成8个投影坐标顶点
            vertices = generate_box_vertices(west, east, south, north, h_bottom, h_top, transformer)

            cells_3d.append((grid_code_3d, vertices))

    return cells_3d, bounds, height_layers


# ============================================================
# 主入口函数
# ============================================================

def generate_3d_grid(config, progress_callback=None, stop_event=None):
    """
    根据配置生成北斗三维网格 OBJ + MTL 文件。

    参数
    ----------
    config : BeiDou3DConfig
        包含所有范围、高度、层级、输出路径等配置。
    progress_callback : callable | None
        签名 f(percent: int, message: str)，每完成一个层级调用一次。
    stop_event : threading.Event | None
        设置后，在下一个层级开始前停止生成并返回已完成的层级。

    返回
    ----------
    dict
        {level: {"cells": N, "height_layers": N, "obj_path": "...", "mtl_path": "...", "size_kb": N}}
    """
    levels = sorted(config.levels)
    if not levels:
        return {}

    # 创建 pyproj Transformer
    transformer = Transformer.from_crs(config.source_crs, config.target_crs, always_xy=True)

    results = {}
    n_levels = len(levels)

    for i, level in enumerate(levels):
        # ---- 取消检查 ----
        if stop_event is not None and stop_event.is_set():
            break

        # ---- 进度回调 ----
        if progress_callback is not None:
            percent = int(i / n_levels * 100)
            label = LEVEL_LABELS.get(level, "")
            progress_callback(percent, f"生成 Level {level} ({label}) 三维网格...")

        # ---- 生成 3D 网格 ----
        cells_3d, bounds, height_layers = generate_level_3d(level, config, transformer)

        # ---- 构造文件路径 ----
        obj_path = os.path.join(config.output_dir, config.obj_pattern.format(level=level) + '.obj')
        mtl_path = os.path.join(config.output_dir, config.obj_pattern.format(level=level) + '.mtl')
        mtl_filename = os.path.basename(mtl_path)

        # ---- 写入文件 ----
        write_mtl_file(mtl_path, config)
        write_obj_file(cells_3d, obj_path, level, bounds, height_layers, config, mtl_filename)

        # ---- 记录结果 ----
        size_kb = os.path.getsize(obj_path) / 1024
        results[level] = {
            "cells": len(cells_3d),
            "height_layers": len(height_layers),
            "obj_path": obj_path,
            "mtl_path": mtl_path,
            "size_kb": size_kb,
        }

        # ---- 进度回调 ----
        if progress_callback is not None:
            percent = int((i + 1) / n_levels * 100)
            progress_callback(percent, f"Level {level}: {len(cells_3d)} cells, {size_kb:.1f} KB")

    return results


# ============================================================
# 命令行入口（兼容独立的测试运行方式）
# ============================================================

if __name__ == "__main__":
    config = BeiDou3DConfig()
    config.levels = [1, 2, 3]

    print("=" * 60)
    print("北斗三维网格位置码 3D 引擎测试")
    print("标准: GB/T 39409-2020")
    print(f"坐标系: {config.source_crs} -> {config.target_crs}")
    print(f"高度范围: {config.h_min:.0f}-{config.h_max:.0f} m")
    print(f"区域: {config.west}-{config.east}E, {config.south}-{config.north}N")
    print(f"测试级别: {config.levels}")
    print("=" * 60)

    def progress(percent, msg):
        print(f"  [{percent:>3}%] {msg}")

    results = generate_3d_grid(config, progress_callback=progress)

    print(f"\n{'=' * 60}")
    print("测试完成! 各级别汇总:")
    print(f"{'级别':<6}{'3D网格数':<12}{'高度层':<8}{'文件大小'}")
    print("-" * 45)
    for level in sorted(results.keys()):
        r = results[level]
        print(f"  {level:<4}{r['cells']:<12}{r['height_layers']:<8}{r['size_kb']:.1f} KB")
