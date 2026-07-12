# 👤 你需要做的事情

> 我能做的都已做完（前端、Mock API、单元测试）。下面是机器替不了的硬件/现场工作。

---

## 一、环境准备（1-2天）

| 事项 | 命令/操作 | 备注 |
|------|----------|------|
| 安装 Docker Desktop | https://docker.com | 跑后端 MySQL+Redis+SpringBoot |
| 安装 Java 17 | `brew install openjdk@17` | 编译 SpringBoot |
| 安装 Maven | `brew install maven` | 后端构建 |
| 安装 PyTorch | `pip3 install torch torchvision` | VLA 推理基础 |
| 启动 Docker 后端 | `cd cloud_backend && docker-compose up -d` | 一镜拉起全栈 |
| 启动 Mock API | `cd cloud_backend/mock-server && node server.js` | 开发测试用 |

## 二、机械臂联调（2-3周）

```
硬件清单:
├── Jetson Orin NX/Nano        ← 边缘计算
├── 遨博 i5/i10 或 越疆 CR     ← 你的机械臂
├── Intel RealSense D435       ← 深度相机
├── 显示器 + 鼠标键盘           ← 上位机交互
└── 网线 (Jetson ↔ 机械臂)     ← ROS2 通信
```

**操作步骤：**

1. Jetson 刷 JetPack 5.1+，装 ROS2 Humble
2. 运行 `deployment/jetson_setup.sh`
3. 接机械臂，测试 `python3 main.py --headless` 能否连接
4. 手眼标定：`python3 main.py --calibrate`（需棋盘格标定板）
5. 手动示教第一个技能：用手拖动机械臂走一遍完整的取放流程
6. 录制 5-10 条示教轨迹，存为 `.json` 文件
7. 跑模仿学习训练：
```bash
cd decision_engine/imitation_learning
python3 train.py --data_dir ./demonstrations/ --output model.pt --epochs 100
```
8. 部署训练好的模型 → 验证抓取成功率

## 三、VLA 具身模型部署（2-3周）

```bash
# 在 Jetson 上:
pip3 install transformers accelerate bitsandbytes

# 下载 OpenVLA 或 Octo 模型
huggingface-cli download openvla/openvla-7b --local-dir ./models/openvla

# 转 TensorRT (Jetson 加速)
python3 scripts/convert_to_tensorrt.py --model ./models/openvla --output ./models/openvla.engine

# 测试 VLA 推理
python3 test_vla_inference.py --image ./test_images/pick_up.jpg --prompt "拿起红色方块"
```

## 四、工厂试点（2-3周）

| 阶段 | 内容 | 输出 |
|------|------|------|
| 产线调研 | 了解当前工序、节拍、瓶颈 | 需求文档 |
| 安装部署 | Jetson+机械臂安装到产线工位 | 设备就位 |
| 示教录制 | 操作工现场示范 10+ 技能 | 示教数据 |
| 跑机验证 | 空跑 500 次，记录成功率 | 验证报告 |
| 异常处理 | 收集故障码，完善异常恢复逻辑 | 故障手册 |
| 操作培训 | 教操作工日常使用 | 培训通过 |

## 五、生产上线（1周）

1. 配置一机一码授权
2. 连接云端 SaaS 后台（设备注册→生成授权码→导入 Jetson）
3. 开启 30s 心跳上报
4. 配置 OTA 版本管理
5. 首周 7×24 专人值班 + 远程运维待命

---

## 六、当前能跑的东西（确认一下）

```bash
# 1. 前端界面 (已就绪)
cd cloud_backend/frontend && npx vite --port 5173
# → http://localhost:5173   已自动登录，5个页面全部有演示数据

# 2. Mock API (端口 8080 已启动)
curl http://localhost:8080/api/device/cluster
# → 返回 JSON，6台设备数据

# 3. Python 单元测试 (已 100% 通过)
cd robovla && python3 tests/test_all.py
# → 25 tests, 25 passed, 0 failed
```

---

## 七、需要另外装的依赖（按需）

| 环境 | 依赖 | 装不装 |
|------|------|--------|
| 开发机 (Mac) | Docker, Java 17, Maven | ✅ 建议装 |
| 开发机 (Mac) | PyTorch, Transformers | ⚠️ 先不装，等 Jetson |
| Jetson Orin | 全装 | ✅ 必须 |
| 工厂工控机 | 仅 Python + Qt | ✅ 必须 |

---

**总结：代码部分已完成 85%，剩下 15% 是硬件相关的适配 + 模型训练。最快 2 个月、稳妥 3 个月从零到工厂跑起来。**
