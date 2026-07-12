# RoboVLA V2.0 开发规范

## 项目概述
工业轻量化具身示教智能系统，五层解耦架构：硬件适配插件层 → 视觉感知层 → 具身决策层 → 应用交互层 → 云端服务层

## 代码规范

### 命名规则
- 类名: PascalCase (RobotBase, VisionEngine)
- 函数/方法: snake_case (connect_robot, capture_frame)
- 变量: snake_case (joint_positions, offset_x)
- 常量: UPPER_SNAKE_CASE (MAX_RETRY_COUNT, DEFAULT_SPEED)
- 文件名: snake_case (robot_base.py, camera_calib.py)
- 私有成员: _前缀 (_joint_states, _camera_matrix)

### 文件分层
```
robovla/
├── hardware_plugin/        # 第一层：硬件适配插件层
│   ├── robot_base.py       # 机器人抽象基类
│   └── plugins/            # 各品牌适配插件
├── visual_engine/          # 第二层：视觉感知层
├── decision_engine/        # 第三层：具身决策层
│   ├── vla_inference/      # VLA多模态推理
│   ├── imitation_learning/ # 拖拽模仿学习
│   └── llm_agent/          # 离线LLM语言Agent
├── qt_ui/                  # 第四层：Qt上位机
├── cloud_backend/          # 第五层：云端服务
│   ├── backend/            # SpringBoot后端
│   └── frontend/           # Vue3前端
├── deployment/             # 部署脚本与交付工具
├── test_data/              # 测试数据
└── docs/                   # 文档
```

### Python规范
- 类型注解必须: def process(frame: np.ndarray) -> Dict[str, float]:
- 异常处理: 所有IO操作、网络通信必须try-except
- 日志: 使用logging模块，禁止print
- 配置: 使用YAML配置文件，禁止硬编码
- 线程安全: 决策层针对推理线程加锁

### C++规范 (Qt/插件)
- Qt信号槽命名: on_xxx_changed, on_btn_xxx_clicked
- 内存管理: 使用智能指针 shared_ptr/unique_ptr
- ROS2节点: 单节点单职责原则

### 性能约束
- VLA推理延迟 ≤ 700ms (TensorRT)
- 视觉处理 ≤ 200ms/frame
- 轨迹采样率 ≥ 50Hz
- LLM指令解析 ≤ 1500ms

### 安全约束
- 本地数据AES-256加密
- 日志留存 ≥ 180天
- 远程运维需二次授权
- 所有操作留痕

## AI协作规则
- 每个模块必须先写单元测试，再写实现
- 接口变更必须同步更新文档注释
- 新增依赖必须写入requirements.txt
- 关键算法必须添加数学注释说明原理
