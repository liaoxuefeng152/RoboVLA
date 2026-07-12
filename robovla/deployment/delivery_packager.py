#!/usr/bin/env python3
"""
RoboVLA V2.0 一键交付打包脚本
用法: python deployment/delivery_packager.py --version 2.0.1 --output ./delivery/

产出:
  - delivery/robovla-v2.0.1-jetson/        完整 Jetson 端交付包
  - delivery/robovla-v2.0.1-cloud/         云端 SaaS 交付包
  - delivery/robovla-v2.0.1-SHA256.txt     校验文件
"""

import os
import sys
import shutil
import hashlib
import argparse
import zipfile
import subprocess
from datetime import datetime
import json


def sha256_file(filepath: str) -> str:
    """计算文件 SHA256"""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_dir(dirpath: str, relative_to: str = None) -> dict:
    """计算目录下所有文件的 SHA256"""
    hashes = {}
    base = relative_to or dirpath
    for root, _, files in os.walk(dirpath):
        for f in files:
            fp = os.path.join(root, f)
            rel = os.path.relpath(fp, base)
            hashes[rel] = sha256_file(fp)
    return hashes


def pack_jetson(version: str, output_dir: str, base_dir: str) -> str:
    """打包 Jetson 边缘端交付包"""
    print("  [Jetson] 打包边缘交付包...")

    pkg_name = f"robovla-v{version}-jetson"
    pkg_path = os.path.join(output_dir, pkg_name)
    os.makedirs(pkg_path, exist_ok=True)

    # 需要打包的目录
    includes = [
        "hardware_plugin",
        "visual_engine",
        "decision_engine",
        "qt_ui",
        "deployment",
        "main.py",
        "requirements.txt",
        "pyproject.toml",
        "README.md",
        "CLAUDE.md",
    ]

    for item in includes:
        src = os.path.join(base_dir, item)
        dst = os.path.join(pkg_path, item)
        if os.path.isdir(src):
            # 排除 __pycache__
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(
                "__pycache__", "*.pyc", ".DS_Store", "*.egg-info"))
        elif os.path.isfile(src):
            shutil.copy2(src, dst)

    # 添加交付文档
    docs_dst = os.path.join(pkg_path, "docs")
    os.makedirs(docs_dst, exist_ok=True)
    docs_src = os.path.join(base_dir, "docs")
    if os.path.exists(docs_src):
        for f in os.listdir(docs_src):
            src = os.path.join(docs_src, f)
            if os.path.isfile(src):
                shutil.copy2(src, docs_dst)

    # 生成版本信息文件
    version_info = {
        "version": version,
        "build_date": datetime.now().isoformat(),
        "compatible_hardware": ["aubo_i5", "aubo_i10", "dobot_d06"],
        "min_jetpack": "6.0",
        "min_python": "3.10",
    }
    with open(os.path.join(pkg_path, "version.json"), "w") as f:
        json.dump(version_info, f, indent=2)

    # 创建 zip
    zip_path = pkg_path + ".zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(pkg_path):
            for f in files:
                fp = os.path.join(root, f)
                zf.write(fp, os.path.relpath(fp, pkg_path))

    return zip_path


def pack_cloud(version: str, output_dir: str, base_dir: str) -> str:
    """打包云端 SaaS 交付包"""
    print("  [Cloud] 打包云端交付包...")

    pkg_name = f"robovla-v{version}-cloud"
    pkg_path = os.path.join(output_dir, pkg_name)
    os.makedirs(pkg_path, exist_ok=True)

    cloud_src = os.path.join(base_dir, "cloud_backend")
    # 复制后端源码
    shutil.copytree(
        os.path.join(cloud_src, "backend"),
        os.path.join(pkg_path, "backend"),
        ignore=shutil.ignore_patterns("target", ".mvn", "__pycache__")
    )
    # 复制前端源码
    shutil.copytree(
        os.path.join(cloud_src, "frontend"),
        os.path.join(pkg_path, "frontend"),
        ignore=shutil.ignore_patterns("node_modules", "dist", ".DS_Store")
    )
    # 复制 docker-compose
    for f in ["docker-compose.yml"]:
        src = os.path.join(cloud_src, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(pkg_path, f))

    # 生成部署说明
    with open(os.path.join(pkg_path, "DEPLOY.md"), "w") as f:
        f.write(f"""# RoboVLA Cloud SaaS 部署说明 v{version}

## 前置要求
- Docker 20.10+
- Docker Compose 2.0+
- 4GB+ 可用内存

## 部署步骤

### 1. 解压交付包
```bash
unzip robovla-v{version}-cloud.zip
cd robovla-v{version}-cloud
```

### 2. 修改配置(可选)
编辑 docker-compose.yml 中的环境变量:
- JWT_SECRET: 随机字符串
- 数据库密码: 修改 MYSQL_ROOT_PASSWORD

### 3. 构建并启动
```bash
docker-compose up -d --build
```

### 4. 验证
```bash
curl http://localhost:8080/actuator/health
# 浏览器打开 http://localhost
```

### 默认账号
- 管理员: admin / admin123
- 运维: maintainer / maintain123
> ⚠️ 上线后请立即修改默认密码!

## 常用运维命令
```bash
docker-compose logs -f backend    # 查看后端日志
docker-compose restart backend    # 重启后端
docker-compose down -v            # 完全清理(会删除数据!)
```

## 数据备份
```bash
docker exec robovla-mysql mysqldump -u robovla -p robovla_cloud > backup.sql
```
""")

    # 创建 zip
    zip_path = pkg_path + ".zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(pkg_path):
            for f in files:
                fp = os.path.join(root, f)
                zf.write(fp, os.path.relpath(fp, pkg_path))

    return zip_path


def main():
    parser = argparse.ArgumentParser(description="RoboVLA 交付包生成器")
    parser.add_argument("--version", default="2.0.0", help="版本号")
    parser.add_argument("--output", default="./delivery", help="输出目录")
    parser.add_argument("--type", choices=["jetson", "cloud", "all"],
                        default="all", help="打包类型")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_dir = os.path.abspath(args.output)
    os.makedirs(output_dir, exist_ok=True)

    print(f"RoboVLA V{args.version} 交付包生成器")
    print(f"输出目录: {output_dir}")
    print()

    checksums = {}

    if args.type in ("jetson", "all"):
        zip_path = pack_jetson(args.version, output_dir, base_dir)
        sha = sha256_file(zip_path)
        checksums[os.path.basename(zip_path)] = sha
        print(f"  ✅ Jetson 交付包: {zip_path}")
        print(f"     SHA256: {sha}")

    if args.type in ("cloud", "all"):
        zip_path = pack_cloud(args.version, output_dir, base_dir)
        sha = sha256_file(zip_path)
        checksums[os.path.basename(zip_path)] = sha
        print(f"  ✅ Cloud 交付包: {zip_path}")
        print(f"     SHA256: {sha}")

    # 写校验文件
    checksum_path = os.path.join(output_dir, f"robovla-v{args.version}-SHA256.txt")
    with open(checksum_path, "w") as f:
        f.write(f"RoboVLA V{args.version} 交付包校验文件\n")
        f.write(f"生成时间: {datetime.now().isoformat()}\n")
        f.write("=" * 60 + "\n\n")
        for name, sha in checksums.items():
            f.write(f"{sha}  {name}\n")

    print()
    print(f"全部交付包生成完成!")
    print(f"校验文件: {checksum_path}")


if __name__ == "__main__":
    main()
