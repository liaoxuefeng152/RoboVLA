#!/bin/bash
# RoboVLA V2.0 - Jetson Orin 一键安装脚本
# 适配: Ubuntu 22.04 + JetPack 6.0 + ROS2 Humble
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_err() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# === 0. 环境检测 ===
check_jetpack() {
    log_info "检测 JetPack 版本..."
    if [ -f /etc/nv_tegra_release ]; then
        JETPACK_VER=$(dpkg-query -W -f='${Version}' nvidia-jetpack 2>/dev/null || echo "unknown")
        log_info "JetPack 版本: $JETPACK_VER"
    else
        log_warn "未检测到 JetPack，确认为 Jetson 设备"
    fi
}

# === 1. 系统基础配置 ===
setup_system() {
    log_info "配置系统基础环境..."
    sudo apt-get update -y
    sudo apt-get upgrade -y
    sudo apt-get install -y \
        build-essential cmake git wget curl \
        python3-dev python3-pip python3-venv \
        libssl-dev libffi-dev libusb-1.0-0-dev \
        v4l-utils ffmpeg sshpass net-tools htop \
        sqlite3 libsqlite3-dev libyaml-cpp-dev \
        gstreamer1.0-tools gstreamer1.0-plugins-good \
        libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev
}

# === 2. 配置 pip 国内镜像源 ===
setup_pip_mirror() {
    log_info "配置 pip 阿里云镜像源..."
    mkdir -p ~/.pip
    cat > ~/.pip/pip.conf << 'EOF'
[global]
index-url = https://mirrors.aliyun.com/pypi/simple/
trusted-host = mirrors.aliyun.com
EOF
    python3 -m pip install --upgrade pip setuptools wheel
}

# === 3. ROS2 Humble 安装 ===
install_ros2() {
    log_info "安装 ROS2 Humble..."
    if [ -d /opt/ros/humble ]; then
        log_warn "ROS2 Humble 已安装，跳过"
        return
    fi
    sudo apt-get install -y software-properties-common
    sudo add-apt-repository -y universe
    sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
        -o /usr/share/keyrings/ros-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" \
        | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
    sudo apt-get update -y
    sudo apt-get install -y ros-humble-ros-base ros-humble-ros2-control \
        ros-humble-ros2-controllers ros-humble-moveit ros-humble-rviz2 \
        ros-humble-tf-transformations ros-humble-cv-bridge \
        python3-colcon-common-extensions python3-rosdep
    sudo rosdep init 2>/dev/null || true
    rosdep update
    log_info "ROS2 Humble 安装完成"
}

# === 4. OpenCV 4.8 编译安装 (CUDA加速) ===
install_opencv() {
    log_info "编译安装 OpenCV 4.8 (CUDA加速)..."
    python3 -c "import cv2; print(cv2.__version__)" 2>/dev/null && {
        log_warn "OpenCV 已安装，检查 CUDA 支持..."
        python3 -c "import cv2; assert cv2.cuda.getCudaEnabledDeviceCount()>0, 'CUDA not enabled'" 2>/dev/null && {
            log_info "OpenCV CUDA 已启用，跳过编译"
            return
        }
        log_warn "OpenCV 无 CUDA，重新编译"
    }

    OPENCV_VER="4.8.0"
    cd /tmp
    wget -q https://github.com/opencv/opencv/archive/${OPENCV_VER}.zip -O opencv.zip
    wget -q https://github.com/opencv/opencv_contrib/archive/${OPENCV_VER}.zip -O opencv_contrib.zip
    unzip -q opencv.zip && unzip -q opencv_contrib.zip
    cd opencv-${OPENCV_VER} && mkdir -p build && cd build

    cmake -D CMAKE_BUILD_TYPE=RELEASE \
          -D CMAKE_INSTALL_PREFIX=/usr/local \
          -D OPENCV_ENABLE_NONFREE=ON \
          -D WITH_CUDA=ON \
          -D WITH_CUDNN=ON \
          -D OPENCV_DNN_CUDA=ON \
          -D CUDA_ARCH_BIN="8.7" \
          -D WITH_OPENGL=ON \
          -D WITH_GSTREAMER=ON \
          -D OPENCV_EXTRA_MODULES_PATH=../../opencv_contrib-${OPENCV_VER}/modules \
          -D BUILD_opencv_python3=ON \
          -D PYTHON3_EXECUTABLE=$(which python3) \
          ..

    make -j$(nproc)
    sudo make install
    sudo ldconfig
    cd / && rm -rf /tmp/opencv*
    log_info "OpenCV 4.8 CUDA 编译完成"
}

# === 5. TensorRT 验证 ===
verify_tensorrt() {
    log_info "验证 TensorRT..."
    python3 -c "import tensorrt as trt; print(f'TensorRT {trt.__version__}')" || \
        log_warn "TensorRT Python 绑定未找到，尝试安装..."
    pip install /usr/src/tensorrt/python/tensorrt-*.whl 2>/dev/null || \
        log_warn "请手动安装 TensorRT Python Wheel"
}

# === 6. PyTorch for Jetson ===
install_pytorch_jetson() {
    log_info "安装 PyTorch for Jetson Orin..."
    python3 -c "import torch; print(f'PyTorch {torch.__version__}')" 2>/dev/null && return
    # Jetson Orin 专用 wheel (PyTorch 2.0 + CUDA 11.4)
    wget -q https://developer.download.nvidia.com/compute/redist/jp/v60/pytorch/torch-2.0.0+nv23.05-cp310-cp310-linux_aarch64.whl -O /tmp/torch.whl
    pip install /tmp/torch.whl
    rm /tmp/torch.whl
}

# === 7. 项目依赖安装 ===
install_project_deps() {
    log_info "安装 RoboVLA 项目依赖..."
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

    # 创建虚拟环境
    python3 -m venv "$PROJECT_ROOT/venv_robovla"
    source "$PROJECT_ROOT/venv_robovla/bin/activate"

    pip install wheel cython

    # 核心视觉
    pip install scipy scikit-learn matplotlib pillow pandas pyyaml

    # Transformers + 量化支持
    pip install transformers accelerate
    pip install bitsandbytes  # 4bit 量化

    # 加密
    pip install pycryptodome cryptography

    # 语音
    pip install vosk sounddevice

    # 工具
    pip install tqdm click coloredlogs

    # 测试
    pip install pytest pytest-cov

    deactivate
    log_info "项目依赖安装完成"
}

# === 8. Qt 5.15 编译环境 ===
install_qt() {
    log_info "安装 Qt 5.15 编译环境..."
    sudo apt-get install -y qtbase5-dev qt5-qmake qtchooser \
        qtdeclarative5-dev qt3d5-dev libqt5serialport5-dev \
        libqt5sql5-sqlite qttools5-dev-tools
}

# === 9. 验证全部环境 ===
verify_all() {
    log_info "========== 环境验证 =========="
    echo ""

    echo -n "CUDA: "
    nvcc --version 2>/dev/null | grep "release" || echo "未找到"

    echo -n "Python: "
    python3 --version

    echo -n "ROS2: "
    test -f /opt/ros/humble/setup.bash && echo "Humble ✓" || echo "未安装 ✗"

    echo -n "OpenCV(Python): "
    python3 -c "import cv2; print(f'{cv2.__version__} ✓')" 2>/dev/null || echo "未安装 ✗"

    echo -n "OpenCV(CUDA): "
    python3 -c "import cv2; print(f'CUDA devices: {cv2.cuda.getCudaEnabledDeviceCount()} ✓')" 2>/dev/null || echo "无CUDA ✗"

    echo -n "TensorRT: "
    python3 -c "import tensorrt as trt; print(f'{trt.__version__} ✓')" 2>/dev/null || echo "未安装 ✗"

    echo -n "PyTorch(CUDA): "
    python3 -c "import torch; print(f'{torch.__version__}, CUDA={torch.cuda.is_available()} ✓')" 2>/dev/null || echo "未安装 ✗"

    echo -n "Camera: "
    v4l2-ctl --list-devices 2>/dev/null | head -3 || echo "未检测到USB相机"

    echo ""
    log_info "========== 验证完成 =========="
}

# === 10. 生成环境变量脚本 ===
gen_env_script() {
    cat > ~/robovla_env.sh << 'ENVEOF'
#!/bin/bash
# RoboVLA 环境变量
source /opt/ros/humble/setup.bash
source ~/robovla_ws/install/setup.bash 2>/dev/null || true
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID=42
export DISPLAY=:0
export QT_QPA_PLATFORM=xcb
ENVEOF
    chmod +x ~/robovla_env.sh
    log_info "环境变量脚本已生成: ~/robovla_env.sh"
}

# === 主流程 ===
main() {
    echo "=========================================="
    echo " RoboVLA V2.0 Jetson Orin 一键安装脚本"
    echo " 目标: Ubuntu 22.04 + JetPack 6.0"
    echo "=========================================="
    echo ""
    sleep 2

    check_jetpack
    setup_system
    setup_pip_mirror
    install_ros2
    install_opencv
    verify_tensorrt
    install_pytorch_jetson
    install_qt
    install_project_deps
    gen_env_script
    verify_all

    echo ""
    log_info "=========================================="
    log_info " 安装完成! 请执行:"
    log_info "   source ~/robovla_env.sh"
    log_info "   cd robovla && source venv_robovla/bin/activate"
    log_info "=========================================="
}

main "$@"
