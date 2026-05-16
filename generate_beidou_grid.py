"""
北斗二维网格位置码 SpatiaLite 空间数据库生成脚本
基于 GB/T 39409-2020《北斗网格位置码》国家标准

生成 1-7 级北斗二维网格空间数据图层，输出为 SpatiaLite 数据库。
地理范围：广深区域（113.7°-114.5° E, 22.4°-23.5° N）

此脚本为命令行入口，所有逻辑位于 beidou_grid_engine.py。
亦可直接运行: python generate_beidou_grid.py
"""

import os
from beidou_params import BeiDou2DConfig, LEVEL_LABELS, LEVEL_CODE_LENGTHS
from beidou_grid_engine import generate_2d_grid


def main():
    """使用默认配置生成2D网格（命令行入口）"""
    config = BeiDou2DConfig()

    print("=" * 60)
    print("北斗二维网格位置码 SpatiaLite 数据库生成")
    print("标准: GB/T 39409-2020")
    print(f"坐标参考系: {config.crs}")
    print(f"区域: {config.west}-{config.east}E, {config.south}-{config.north}N")
    print("=" * 60)

    def progress(percent, msg):
        print(f"  [{percent:>3}%] {msg}")

    gdfs = generate_2d_grid(config, progress_callback=progress)

    # 输出路径
    output_path = os.path.join(config.output_dir, config.output_db_name)
    file_size = os.path.getsize(output_path) / (1024 * 1024)

    # 统计汇总
    print(f"\n{'=' * 60}")
    print(f"输出文件: {output_path}")
    print(f"文件大小: {file_size:.1f} MB")
    print(f"\n{'级别':<6}{'网格数':<10}{'编码长度':<10}{'单元尺寸'}")
    print("-" * 45)
    for level in range(1, 11):
        if level in gdfs:
            count = len(gdfs[level])
            code_len = LEVEL_CODE_LENGTHS.get(level, "-")
            label = LEVEL_LABELS.get(level, "-")
            print(f"  {level:<4}{count:<10}{code_len:<10}{label}")
    print()

    # 样例编码
    print("各级别样例编码:")
    for level in range(1, 11):
        if level in gdfs and len(gdfs[level]) > 0:
            gdf = gdfs[level]
            sample = gdf.iloc[min(3, len(gdf) - 1)]["grid_code"]
            print(f"  Level {level}: {sample}")
    print()


if __name__ == "__main__":
    main()
