#!/bin/bash
# RoboVLA V2.0 - U盘离线更新包制作工具
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VERSION="${1:-2.0.0}"
OUTPUT_DIR="${2:-/tmp/robovla_update}"

echo "=========================================="
echo " RoboVLA V2.0 更新包制作工具"
echo " 版本: $VERSION"
echo " 输出: $OUTPUT_DIR"
echo "=========================================="

mkdir -p "$OUTPUT_DIR/robovla_update_$VERSION"

# 1. 复制核心文件
cp -r "$PROJECT_ROOT/hardware_plugin" "$OUTPUT_DIR/robovla_update_$VERSION/"
cp -r "$PROJECT_ROOT/visual_engine" "$OUTPUT_DIR/robovla_update_$VERSION/"
cp -r "$PROJECT_ROOT/decision_engine" "$OUTPUT_DIR/robovla_update_$VERSION/"
cp -r "$PROJECT_ROOT/qt_ui" "$OUTPUT_DIR/robovla_update_$VERSION/"
cp "$PROJECT_ROOT/requirements.txt" "$OUTPUT_DIR/robovla_update_$VERSION/"
cp "$PROJECT_ROOT/CLAUDE.md" "$OUTPUT_DIR/robovla_update_$VERSION/"

# 2. 生成安装脚本
cat > "$OUTPUT_DIR/robovla_update_$VERSION/install.sh" << 'EOF'
#!/bin/bash
# RoboVLA 离线安装脚本
set -e
echo "正在安装 RoboVLA 更新..."
UPDATE_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_DIR="$HOME/robovla"

mkdir -p "$TARGET_DIR"
cp -r "$UPDATE_DIR"/* "$TARGET_DIR/"
cd "$TARGET_DIR"

# 安装依赖
source venv_robovla/bin/activate 2>/dev/null || {
    python3 -m venv venv_robovla
    source venv_robovla/bin/activate
}
pip install -r requirements.txt --quiet

echo "✅ RoboVLA V2.0 安装完成!"
echo "启动: cd $TARGET_DIR && python qt_ui/main_window.py"
EOF

chmod +x "$OUTPUT_DIR/robovla_update_$VERSION/install.sh"

# 3. 打包
cd "$OUTPUT_DIR"
tar -czf "robovla_v$VERSION.tar.gz" "robovla_update_$VERSION"/
rm -rf "robovla_update_$VERSION"

echo "✅ 更新包已生成: $OUTPUT_DIR/robovla_v$VERSION.tar.gz"
echo "   大小: $(du -h "$OUTPUT_DIR/robovla_v$VERSION.tar.gz" | cut -f1)"
echo ""
echo "部署方式: U盘拷贝 robovla_v$VERSION.tar.gz → 目标设备 → tar xzf → ./install.sh"
