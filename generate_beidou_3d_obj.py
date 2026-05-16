"""
北斗三维网格位置码 OBJ 文件生成脚本
基于 GB/T 39409-2020《北斗网格位置码》国家标准

生成 7 个 OBJ 格式文件，每个文件对应一个级别的三维网格。
坐标系：CGCS2000 / 3度高斯-克吕格投影 中央经线114E (EPSG:4547)

此脚本为命令行入口，所有逻辑位于 beidou_3d_engine.py。
"""

import os
from beidou_params import BeiDou3DConfig, LEVEL_LABELS
from beidou_3d_engine import generate_3d_grid

def main():
    config = BeiDou3DConfig()
    
    print("=" * 60)
    print("北斗三维网格位置码 OBJ 文件生成")
    print("标准: GB/T 39409-2020")
    print(f"坐标系: {config.source_crs} -> {config.target_crs}")
    print(f"高度范围: {config.h_min:.0f}-{config.h_max:.0f} m")
    print(f"区域: {config.west}-{config.east}E, {config.south}-{config.north}N")
    print("=" * 60)
    
    def progress(percent, msg):
        print(f"  [{percent:>3}%] {msg}")
    
    results = generate_3d_grid(config, progress_callback=progress)
    
    print(f"\n{'=' * 60}")
    print("生成完成! 各级别汇总:")
    print(f"{'级别':<6}{'3D网格数':<12}{'高度层':<8}{'文件大小'}")
    print("-" * 45)
    for level in range(1, 11):
        if level in results:
            r = results[level]
            print(f"  {level:<4}{r['cells']:<12}{r['height_layers']:<8}{r['size_kb']:.1f} KB")
    
if __name__ == "__main__":
    main()
