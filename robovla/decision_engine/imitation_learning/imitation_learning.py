"""
RoboVLA V2.0 - 拖拽模仿学习系统

核心功能:
1. 分段拖拽示教录制(取料/装配/检测/下料)
2. 全维度数据采集(关节轨迹/末端姿态/力度/视觉帧)
3. B样条轨迹平滑滤波(消除人工抖动)
4. 轻量化本地VLA训练(5分钟内生成任务模型)
5. 任务模板库管理(JSON存储，支持导入导出)
"""

import json
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Deque
from collections import deque
import numpy as np
from scipy.interpolate import splprep, splev
from scipy.signal import savgol_filter

from hardware_plugin.robot_base import (
    RobotBase, JointState, CartesianPose, TrajectoryPoint,
    GripperState, MotionParams, RobotState
)

logger = logging.getLogger(__name__)


# ============================================================
# 数据类型
# ============================================================

@dataclass
class TaskSegment:
    """示教任务段(分段独立录制)"""
    id: int
    name: str                          # 取料/装配/检测/下料
    seq: int                           # 顺序编号
    trajectory: List[np.ndarray]       # 关节轨迹列表
    cartesian_path: List[np.ndarray]   # 末端笛卡尔轨迹
    gripper_actions: List[GripperState]  # 夹爪动作序列
    force_readings: List[np.ndarray]   # 力度传感器读数
    dwell_times: List[float]           # 每点停留时间
    visual_frames: List[int]           # 关联视觉帧ID
    smooth_trajectory: Optional[np.ndarray] = None  # 平滑后轨迹


@dataclass
class TaskTemplate:
    """完整工序任务模板"""
    id: str
    name: str
    category: str                     # 锁付/组装/检测/包装
    segments: List[TaskSegment] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    vla_model_path: Optional[str] = None
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "name": self.name, "category": self.category,
            "segments_count": len(self.segments),
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ============================================================
# 拖拽示教录制器
# ============================================================

class DragRecorder:
    """
    拖拽示教分段录制器

    工作流程:
    1. 开启拖拽模式 → enable_drag_mode()
    2. 开始采集 → start_recording(segment_name="取料")
    3. 人工拖拽机械臂完成工序
    4. 停止采集 → stop_recording()
    5. 自动平滑轨迹
    6. 重复步骤2-4录制其他段

    采样率: 50Hz (每20ms采集一帧)
    """

    SAMPLE_RATE_HZ = 50          # Hz
    SAMPLE_INTERVAL_S = 0.02    # 20ms

    def __init__(self, robot: RobotBase):
        self.robot = robot
        self._segments: List[TaskSegment] = []
        self._current_segment: Optional[TaskSegment] = None
        self._is_recording = False
        self._trajectory_buffer: Deque[np.ndarray] = deque(maxlen=5000)
        self._cartesian_buffer: Deque[np.ndarray] = deque(maxlen=5000)
        self._gripper_buffer: Deque[GripperState] = deque(maxlen=5000)
        self._force_buffer: Deque[np.ndarray] = deque(maxlen=5000)
        self._dwell_buffer: Deque[float] = deque(maxlen=5000)
        self._prev_positions: Optional[np.ndarray] = None
        self._segment_counter = 0

    def start_recording(self, name: str) -> bool:
        """
        开始录制一段示教

        Args:
            name: 段名称(取料/装配/检测/下料)
        """
        if self._is_recording:
            logger.warning("已在录制中，请先停止当前段")
            return False

        if not self.robot.enable_drag_mode():
            logger.error("无法开启拖拽模式")
            return False

        self._segment_counter += 1
        self._is_recording = True
        self._prev_positions = None

        # 清空缓冲区
        for buf in [self._trajectory_buffer, self._cartesian_buffer,
                     self._gripper_buffer, self._force_buffer, self._dwell_buffer]:
            buf.clear()

        self._current_segment = TaskSegment(
            id=self._segment_counter,
            name=name,
            seq=self._segment_counter,
            trajectory=[],
            cartesian_path=[],
            gripper_actions=[],
            force_readings=[],
            dwell_times=[],
            visual_frames=[],
        )

        logger.info(f"🔴 开始录制段 [{self._segment_counter}] {name}")
        return True

    def stop_recording(self) -> Optional[TaskSegment]:
        """停止当前段录制并自动平滑轨迹"""
        if not self._is_recording:
            logger.warning("当前未在录制")
            return None

        self.robot.disable_drag_mode()
        self._is_recording = False

        # 转移缓冲区数据
        self._current_segment.trajectory = list(self._trajectory_buffer)
        self._current_segment.cartesian_path = list(self._cartesian_buffer)
        self._current_segment.gripper_actions = list(self._gripper_buffer)
        self._current_segment.force_readings = list(self._force_buffer)
        self._current_segment.dwell_times = list(self._dwell_buffer)

        # 自动轨迹平滑
        self._smooth_trajectory()

        self._segments.append(self._current_segment)
        logger.info(f"⏹️ 停止录制 [{self._current_segment.name}] "
                    f"| {len(self._current_segment.trajectory)} 个轨迹点")
        return self._current_segment

    def tick(self) -> bool:
        """
        单帧采集(每20ms调用一次)

        应在定时器循环中调用，自动采集关节/末端/力度数据
        Returns: True=采集成功
        """
        if not self._is_recording:
            return False

        try:
            joint = self.robot.get_joint_state()
            pose = self.robot.get_cartesian_pose()
            gripper = self.robot.get_gripper_state()

            self._trajectory_buffer.append(joint.positions.copy())
            self._cartesian_buffer.append(np.hstack([
                pose.position, pose.orientation
            ]))
            self._gripper_buffer.append(gripper)
            self._force_buffer.append(joint.efforts.copy() if joint.efforts is not None
                                       else np.zeros(6))

            # 计算停留时间(上次位移变化量)
            if self._prev_positions is not None:
                displacement = np.linalg.norm(
                    joint.positions - self._prev_positions
                )
                if displacement < 0.005:
                    self._dwell_buffer[-1] += self.SAMPLE_INTERVAL_S
                else:
                    self._dwell_buffer.append(self.SAMPLE_INTERVAL_S)
            else:
                self._dwell_buffer.append(0.0)

            self._prev_positions = joint.positions.copy()
            return True

        except Exception as e:
            logger.error(f"采集帧异常: {e}")
            return False

    def delete_segment(self, seg_id: int) -> bool:
        """删除一个录制的段"""
        for i, seg in enumerate(self._segments):
            if seg.id == seg_id:
                self._segments.pop(i)
                logger.info(f"已删除段 [{seg_id}] {seg.name}")
                return True
        return False

    def re_record_segment(self, seg_id: int, name: str = None) -> bool:
        """重录指定段"""
        self.delete_segment(seg_id)
        return self.start_recording(name or f"段{seg_id}")

    def get_segments(self) -> List[Dict]:
        """获取所有段概要"""
        return [
            {"id": s.id, "name": s.name, "seq": s.seq,
             "points": len(s.trajectory)}
            for s in self._segments
        ]

    def _smooth_trajectory(self):
        """
        B样条 + Savitzky-Golay 平滑轨迹

        目的: 消除人工拖拽产生的手部抖动和速度不均匀
        """
        if len(self._current_segment.trajectory) < 3:
            return

        traj = np.array(self._current_segment.trajectory)
        n, dof = traj.shape

        # === 1. Savitzky-Golay 初次滤波(去高频抖动) ===
        window = min(11, n - 2 if n % 2 == 0 else n - 1)
        if window >= 5:
            smoothed = np.zeros_like(traj)
            for j in range(dof):
                smoothed[:, j] = savgol_filter(traj[:, j], window, 3)
        else:
            smoothed = traj

        # === 2. B样条插值重采样(均匀化轨迹速度) ===
        t = np.linspace(0, 1, n)
        try:
            tck, u = splprep([smoothed[:, j] for j in range(dof)],
                             u=t, s=1.0, k=min(3, n - 1))
            # 等弧长重采样回原长度
            u_new = np.linspace(0, 1, n)
            spline_result = np.array(splev(u_new, tck)).T
            self._current_segment.smooth_trajectory = spline_result
        except Exception as e:
            logger.warning(f"B样条平滑失败: {e}, 使用S-G结果")
            self._current_segment.smooth_trajectory = smoothed

        # 计算平滑前后最大偏差
        max_deviation = np.max(np.abs(smoothed - traj)) if smoothed is not None else 0
        logger.info(f"轨迹平滑完成 | 最大修正: {max_deviation:.4f} rad")


# ============================================================
# 任务模板管理器
# ============================================================

class TaskTemplateManager:
    """
    标准化任务模板库

    支持:
    - 任务创建/重命名/复制/删除
    - 工序段拖拽排序
    - JSON 导入/导出(U盘)
    - 按行业场景分类(锁付/组装/检测/包装)
    """

    CATEGORIES = ["锁付", "组装", "检测", "包装", "上下料", "其他"]

    def __init__(self, storage_dir: str = "test_data/task_templates"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._templates: Dict[str, TaskTemplate] = {}
        self._load_all()

    def _load_all(self):
        """从存储目录加载所有任务模板"""
        for f in self.storage_dir.glob("*.json"):
            try:
                with open(f, 'r') as fp:
                    data = json.load(fp)
                t = TaskTemplate(
                    id=data["id"], name=data["name"],
                    category=data.get("category", "其他"),
                    metadata=data.get("metadata", {}),
                    vla_model_path=data.get("vla_model_path"),
                    created_at=data.get("created_at", 0),
                    updated_at=data.get("updated_at", 0),
                )
                self._templates[t.id] = t
            except Exception as e:
                logger.warning(f"加载模板失败 {f.name}: {e}")
        logger.info(f"已加载 {len(self._templates)} 个任务模板")

    def create(self, name: str, category: str = "其他",
               segments: List[TaskSegment] = None) -> TaskTemplate:
        """创建新任务模板"""
        tid = f"task_{int(time.time() * 1000)}_{len(self._templates):03d}"
        template = TaskTemplate(
            id=tid, name=name, category=category,
            segments=segments or [],
            metadata={"version": "2.0", "dof": 6},
            created_at=time.time(), updated_at=time.time(),
        )
        self._templates[tid] = template
        self._save(template)
        logger.info(f"✅ 创建任务模板: {name} [{tid}]")
        return template

    def update_segments(self, task_id: str,
                        segments: List[TaskSegment]) -> bool:
        """更新任务模板的工序段(支持拖拽排序后保存)"""
        template = self._templates.get(task_id)
        if not template:
            return False
        template.segments = sorted(segments, key=lambda s: s.seq)
        template.updated_at = time.time()
        self._save(template)
        return True

    def duplicate(self, task_id: str, new_name: str = None) -> Optional[TaskTemplate]:
        """复制任务模板"""
        src = self._templates.get(task_id)
        if not src:
            return None
        new_tid = f"task_{int(time.time() * 1000)}_{len(self._templates):03d}"
        new_template = TaskTemplate(
            id=new_tid, name=new_name or f"{src.name}_副本",
            category=src.category,
            segments=list(src.segments),  # shallow copy
            metadata=dict(src.metadata),
            vla_model_path=src.vla_model_path,
            created_at=time.time(), updated_at=time.time(),
        )
        self._templates[new_tid] = new_template
        self._save(new_template)
        return new_template

    def delete(self, task_id: str) -> bool:
        """删除任务模板"""
        template = self._templates.pop(task_id, None)
        if template:
            f = self.storage_dir / f"{task_id}.json"
            f.unlink(missing_ok=True)
            if template.vla_model_path:
                Path(template.vla_model_path).unlink(missing_ok=True)
            logger.info(f"已删除任务模板: {template.name}")
            return True
        return False

    def list_by_category(self) -> Dict[str, List[Dict]]:
        """按分类列出"""
        result = {cat: [] for cat in self.CATEGORIES}
        for t in self._templates.values():
            result[t.category].append(t.to_dict())
        return result

    def export_to_json(self, task_id: str, export_path: str) -> bool:
        """导出单个任务模板为JSON文件(U盘)"""
        template = self._templates.get(task_id)
        if not template:
            return False
        src = self.storage_dir / f"{task_id}.json"
        if src.exists():
            import shutil
            shutil.copy(src, export_path)
            logger.info(f"已导出任务模板: {export_path}")
            return True
        return False

    def import_from_json(self, json_path: str) -> Optional[TaskTemplate]:
        """从JSON文件导入任务模板"""
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
            template = TaskTemplate(
                id=data["id"], name=data["name"],
                category=data.get("category", "其他"),
                metadata=data.get("metadata", {}),
                vla_model_path=data.get("vla_model_path"),
                created_at=data.get("created_at", time.time()),
                updated_at=data.get("updated_at", time.time()),
            )
            self._templates[template.id] = template
            self._save(template)
            logger.info(f"已导入任务模板: {template.name}")
            return template
        except Exception as e:
            logger.error(f"导入失败: {e}")
            return None

    def _save(self, template: TaskTemplate):
        """保存到磁盘"""
        data = {
            "id": template.id,
            "name": template.name,
            "category": template.category,
            "segments": [{
                "id": s.id, "name": s.name, "seq": s.seq,
                "trajectory_points": len(s.trajectory),
                # 轨迹数据由 VLA 模型存储, 此处仅存元数据
            } for s in template.segments],
            "metadata": template.metadata,
            "vla_model_path": template.vla_model_path,
            "created_at": template.created_at,
            "updated_at": template.updated_at,
        }
        f = self.storage_dir / f"{template.id}.json"
        with open(f, 'w') as fp:
            json.dump(data, fp, indent=2, ensure_ascii=False)


# ============================================================
# 模仿学习训练器
# ============================================================

class ImitationLearningTrainer:
    """
    拖拽模仿学习本地训练模块

    目标: 5分钟内完成本地离线训练，生成具备±15mm泛化能力的任务模型

    训练流程:
    1. 收集示教数据集(多段拖拽轨迹)
    2. 数据增强(加噪声、旋转、平移)
    3. 轻量化网络训练(MLP/轻量Transformer)
    4. 导出 ONNX 模型 → TensorRT 优化

    硬性指标:
    - 训练时长 ≤ 5 分钟
    - 泛化范围 ±15mm
    - 模型大小 ≤ 50MB(量化后)
    """

    def __init__(self, output_dir: str = "test_data/models"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def train(self, segments: List[TaskSegment],
              task_name: str = "unnamed",
              epochs: int = 100,
              validation_split: float = 0.2) -> str:
        """
        轻量化训练: 多层感知机 + 数据增强

        Args:
            segments: 示教段列表
            task_name: 任务名称
            epochs: 训练轮数
            validation_split: 验证集比例
        Returns:
            ONNX 模型文件路径
        """
        logger.info(f"开始训练任务模型: {task_name}")
        t0 = time.time()

        # === 1. 准备训练数据 ===
        X, Y = self._prepare_dataset(segments)
        logger.info(f"训练数据集: {len(X)} samples, {X.shape[1]} features "
                    f"→ {Y.shape[1]} outputs")

        # === 2. 数据增强(模拟偏移) ===
        X_aug, Y_aug = self._augment_data(X, Y, noise_scale=0.02, num_augments=3)
        X_all = np.vstack([X, X_aug])
        Y_all = np.vstack([Y, Y_aug])
        logger.info(f"增强后数据集: {len(X_all)} samples")

        # === 3. 训练/验证集分割 ===
        indices = np.random.permutation(len(X_all))
        split_idx = int(len(X_all) * (1 - validation_split))
        X_train, X_val = X_all[indices[:split_idx]], X_all[indices[split_idx:]]
        Y_train, Y_val = Y_all[indices[:split_idx]], Y_all[indices[split_idx:]]

        # === 4. 构建轻量级网络 ===
        model = self._build_model(X_train.shape[1], Y_train.shape[1])

        # === 5. 训练 ===
        import torch
        import torch.nn as nn
        import torch.optim as optim

        X_train_t = torch.FloatTensor(X_train)
        Y_train_t = torch.FloatTensor(Y_train)
        X_val_t = torch.FloatTensor(X_val)
        Y_val_t = torch.FloatTensor(Y_val)

        optimizer = optim.AdamW(model.parameters(), lr=0.001, weight_decay=1e-5)
        scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, epochs)
        loss_fn = nn.HuberLoss(delta=0.01)

        best_val_loss = float('inf')
        for epoch in range(epochs):
            model.train()
            optimizer.zero_grad()
            pred = model(X_train_t)
            loss = loss_fn(pred, Y_train_t)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()

            # 验证
            model.eval()
            with torch.no_grad():
                val_pred = model(X_val_t)
                val_loss = loss_fn(val_pred, Y_val_t).item()

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                # 保存最佳权重
                best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

            if epoch % 20 == 0:
                logger.debug(f"Epoch {epoch}/{epochs} | "
                             f"train_loss={loss.item():.5f} val_loss={val_loss:.5f}")

        model.load_state_dict(best_state)
        elapsed = time.time() - t0
        logger.info(f"✅ 训练完成 | 用时 {elapsed:.1f}s | best_val_loss={best_val_loss:.5f}")

        # === 6. 导出 ONNX ===
        onnx_path = str(self.output_dir / f"{task_name}_{int(time.time())}.onnx")
        dummy_input = torch.randn(1, X.shape[1])
        torch.onnx.export(
            model, dummy_input, onnx_path,
            input_names=["input"], output_names=["output"],
            opset_version=14,
            dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}}
        )
        logger.info(f"模型已导出: {onnx_path}")

        # === 7. 泛化验证 ===
        self._validate_generalization(model, X_val, Y_val)

        return onnx_path

    def _prepare_dataset(self, segments: List[TaskSegment]) -> Tuple[np.ndarray, np.ndarray]:
        """
        从示教段构建监督学习数据集

        输入X: [关节角(6) + 末端位姿(6) + 前一帧动作(6) + 视觉特征(64)] = 82维
        输出Y: [目标关节角(6)]
        """
        all_X, all_Y = [], []

        for seg in segments:
            traj = (seg.smooth_trajectory if seg.smooth_trajectory is not None
                    else np.array(seg.trajectory))

            for i in range(1, len(traj)):
                # 当前状态: 关节 + 位姿 + 前一帧
                prev_joint = traj[i - 1]
                curr_joint = traj[i]

                # 模拟位姿(从关节角估算)
                curr_pose = np.hstack([
                    curr_joint[:3] * 0.1,  # 位置
                    curr_joint[3:] * 0.01   # 姿态
                ])

                # 输入特征
                x = np.hstack([
                    curr_joint,           # 6
                    curr_pose,            # 6
                    prev_joint,           # 6
                    np.zeros(64),         # 视觉特征(占位)
                ])
                all_X.append(x)
                all_Y.append(traj[min(i + 1, len(traj) - 1)])

        return np.array(all_X, dtype=np.float32), np.array(all_Y, dtype=np.float32)

    def _augment_data(self, X: np.ndarray, Y: np.ndarray,
                      noise_scale: float = 0.02,
                      num_augments: int = 3) -> Tuple[np.ndarray, np.ndarray]:
        """数据增强: 加噪声 + 平移(模拟工件偏移)"""
        X_list, Y_list = [X], [Y]
        for i in range(num_augments):
            noise_std = noise_scale * (i + 1)
            X_noisy = X + np.random.normal(0, noise_std, X.shape).astype(np.float32)
            Y_noisy = Y + np.random.normal(0, noise_std * 0.5, Y.shape).astype(np.float32)
            X_list.append(X_noisy)
            Y_list.append(Y_noisy)

            # 平移增强(模拟工件偏移±15mm)
            if i < 2:
                shift = np.zeros_like(X)
                shift[:, :3] = 0.015 * (2 * i - 1)  # ±15mm 偏移
                X_list.append(X + shift.astype(np.float32))
                Y_list.append(Y)

        return np.vstack(X_list), np.vstack(Y_list)

    def _build_model(self, input_dim: int, output_dim: int):
        """构建轻量级多层感知机"""
        import torch
        import torch.nn as nn

        class LightweightTrajectoryNet(nn.Module):
            def __init__(self):
                super().__init__()
                self.net = nn.Sequential(
                    nn.Linear(input_dim, 256),
                    nn.BatchNorm1d(256),
                    nn.GELU(),
                    nn.Dropout(0.1),
                    nn.Linear(256, 256),
                    nn.BatchNorm1d(256),
                    nn.GELU(),
                    nn.Dropout(0.1),
                    nn.Linear(256, 128),
                    nn.BatchNorm1d(128),
                    nn.GELU(),
                    nn.Linear(128, output_dim),
                )
                self._init_weights()

            def _init_weights(self):
                for m in self.modules():
                    if isinstance(m, nn.Linear):
                        nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
                        if m.bias is not None:
                            nn.init.zeros_(m.bias)

            def forward(self, x):
                return self.net(x)

        return LightweightTrajectoryNet()

    def _validate_generalization(self, model, X_val, Y_val):
        """验证泛化能力"""
        import torch
        model.eval()
        with torch.no_grad():
            X_t = torch.FloatTensor(X_val)
            Y_t = torch.FloatTensor(Y_val)
            pred = model(X_t)
            errors = torch.norm(pred - Y_t, dim=1).numpy()
            mean_err = np.mean(errors)
            max_err = np.max(errors)
            logger.info(f"泛化验证 | 平均误差: {mean_err:.4f} rad | 最大误差: {max_err:.4f} rad")
            # 粗略检查: 0.01 rad ≈ 末端 5mm @ 500mm臂展
            if mean_err > 0.02:
                logger.warning(f"泛化误差偏大，建议增加示教数据")


# ============================================================
# 模仿学习执行器
# ============================================================

class ImitationExecutor:
    """
    基于训练好的任务模型执行生产循环

    工作流程:
    1. 加载 ONNX/TensorRT 模型
    2. 实时读取视觉偏移量
    3. 模型推理 → 修正目标关节角
    4. 下发机器人运动指令
    """

    def __init__(self, robot: RobotBase):
        self.robot = robot
        self._model = None
        self._session = None

    def load_model(self, model_path: str):
        """加载 ONNX 模型(TensorRT 优化)"""
        import onnxruntime as ort
        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
        self._session = ort.InferenceSession(model_path, providers=providers)
        logger.info(f"模型已加载: {model_path}")

    def infer_action(self, state: np.ndarray) -> np.ndarray:
        """
        模型推理 → 输出目标关节角

        Args:
            state: 当前状态向量 [关节(6), 位姿(6), 上一帧动作(6), 视觉特征(64)]
        Returns:
            目标关节角(6)
        """
        input_feed = {"input": state.reshape(1, -1).astype(np.float32)}
        output = self._session.run(["output"], input_feed)[0]
        return output.flatten()

    def execute_loop(self, task_template: TaskTemplate,
                     vision_offset_fn, max_cycles: int = 9999):
        """
        生产循环执行

        Args:
            task_template: 任务模板
            vision_offset_fn: 视觉偏移回调 → (dx, dy, da)
            max_cycles: 最大循环次数
        """
        for cycle in range(max_cycles):
            # 1. 获取视觉偏移
            dx, dy, da = vision_offset_fn()

            # 2. 构建状态向量
            joint = self.robot.get_joint_state()
            pose = self.robot.get_cartesian_pose()
            state = np.hstack([
                joint.positions,
                np.hstack([pose.position, pose.orientation]),
                np.zeros(6),   # 上一帧动作
                self._encode_offset(dx, dy, da),
            ])

            # 3. 推理目标关节角
            target_joints = self.infer_action(state)

            # 4. 安全校验
            if not self.robot.is_within_joint_limits(target_joints):
                logger.warning("推理结果超出限位, 跳过")
                break

            # 5. 执行运动
            self.robot.move_joint(target_joints)
            logger.debug(f"Cycle {cycle}: joints={np.round(target_joints, 3)}")

    def _encode_offset(self, dx: float, dy: float, da: float) -> np.ndarray:
        """编码偏移量到特征向量"""
        return np.array([dx, dy, da, 0, 0, 0,
                         0, 0, 0, 0, 0, 0,
                         0, 0, 0, 0,  # 16维
                         ] + [0] * 48)  # 补齐64维
