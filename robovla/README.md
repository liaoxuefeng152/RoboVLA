# RoboVLA V2.0 — 工业轻量化具身示教智能系统

> **一个软件大脑，驱动万千机械臂。**  
> 不造硬件，只为成品协作机械臂提供 AI 大脑。

---

## 项目简介

RoboVLA 是一套面向中小制造企业的**轻量化具身智能软件系统**。工人只需拖拽机械臂完成一次装配动作，系统通过视觉-语言-动作（VLA）多模态算法自动泛化到工件位置变化场景，实现自适应生产。

| 指标 | 数值 |
|---|---|
| 单次示教+训练时间 | ≤ 5 分钟 |
| VLA 端到端推理延迟 | ≤ 700ms |
| 工件偏移自适应范围 | ±15mm |
| 抓取成功率 | ≥ 96% |
| 断网可用 | 全功能离线运行 |

---

## 技术架构

```
┌─────────────┐  ┌──────────┐  ┌──────────────┐
│  Qt 上位机   │  │ Vue3 SaaS│  │ SpringBoot   │
│ (C++)        │  │ 前端      │  │ 后端 (Java)  │
├─────────────┤  ├──────────┤  ├──────────────┤
│   硬件插件层   │  │ 视觉感知层  │  │  决策引擎     │
│ 遨博|越疆|宇树 │  │ 标定|匹配  │  │ VLA|LLM|模仿  │
└─────────────┘  └──────────┘  └──────────────┘
```

## 快速开始

### 开发环境（电脑端）

```bash
cd robovla
pip install -r requirements.txt
python main.py                    # 启动 Qt 上位机
python main.py --calibrate        # 相机标定模式
python main.py --headless         # 无界面后台模式
```

### Jetson 边缘部署

```bash
chmod +x deployment/jetson_setup.sh
sudo ./deployment/jetson_setup.sh
```

### 云端 SaaS 部署

```bash
cd cloud_backend
docker-compose up -d
```

---

## 目录结构

```
robovla/
├── main.py                     # 主启动脚本
├── hardware_plugin/            # 硬件插件层
│   ├── robot_base.py           #   抽象基类
│   └── plugins/                #   遨博/越疆/宇树适配器
├── visual_engine/              # 视觉感知层
│   └── vision_engine.py        #   标定/特征匹配/偏移计算
├── decision_engine/            # 具身决策层(核心壁垒)
│   ├── vla_inference/          #   VLA 推理引擎
│   ├── imitation_learning/     #   模仿学习+轨迹平滑
│   └── llm_agent/              #   离线 LLM + 语音交互
├── qt_ui/                      # Qt 上位机
│   ├── main_window.py          #   6 页面主界面
│   ├── local_database.py       #   SQLite 本地数据库
│   └── license_manager.py      #   一机一码授权
├── cloud_backend/              # 云端 SaaS
│   ├── backend/                #   SpringBoot 后端
│   └── frontend/               #   Vue3 前端
├── deployment/                 # 部署工具
│   ├── jetson_setup.sh         #   Jetson 一键安装
│   └── update_packager.sh      #   U盘离线更新制作
└── tests/                      # 单元测试
```

---

## 开发规范

详见 [CLAUDE.md](./CLAUDE.md)，包含：
- Python 代码命名规范
- 模块间接口契约
- 日志与异常处理标准
- Git 提交信息格式

---

## 测试

```bash
# 运行所有单元测试
python -m pytest tests/ -v

# 覆盖率报告
python -m pytest tests/ --cov=. --cov-report=html
```

---

## 许可证

本项目为商业软件，采用**一机一码授权**模式，未经授权禁止复制、分发和使用。

---

*RoboVLA — 让每一台机械臂都拥有 AI 大脑.*
