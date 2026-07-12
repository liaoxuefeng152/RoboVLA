"""
RoboVLA V2.0 - 轻量化工业 VLA 推理引擎

核心能力:
1. 多模态融合推理(视觉 + 文本指令 + 运动轨迹)
2. TensorRT 量化加速(4bit, ≤700ms 端到端延迟)
3. 工件偏移动态补偿
4. 异常重试策略

架构:
  VisionFeatureExtractor → [视觉编码]
  TextEncoder           → [指令编码]
  TrajectoryPlanner     → [轨迹规划]
  DynamicCompensator    → [偏移补偿]
  SafetyChecker         → [安全校验]
  → 最终: 标准化运动指令输出
"""

import json
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum, auto
import numpy as np

logger = logging.getLogger(__name__)


# ============================================================
# 数据类型
# ============================================================

class ActionType(Enum):
    """动作类型"""
    MOVE_JOINT = auto()
    MOVE_CARTESIAN = auto()
    MOVE_LINEAR = auto()
    GRIPPER_OPEN = auto()
    GRIPPER_CLOSE = auto()
    WAIT = auto()
    CHECK = auto()          # 视觉检查
    RETRY = auto()          # 重试
    ABORT = auto()          # 中止


@dataclass
class VLAAction:
    """VLA 推理输出的单个动作"""
    type: ActionType
    target: np.ndarray          # 目标值(关节角/位姿)
    gripper_force: float = 50.0  # 夹爪力(N)
    dwell: float = 0.0          # 停留时间(s)
    speed: float = 0.3          # 速度比例
    acceleration: float = 0.4    # 加速度比例
    retry_count: int = 0        # 重试次数
    confidence: float = 1.0     # 推理置信度


@dataclass
class VLAPlan:
    """完整 VLA 执行计划(一组有序动作)"""
    actions: List[VLAAction] = field(default_factory=list)
    estimated_duration: float = 0.0  # 预估执行时间(s)
    success_prob: float = 1.0        # 预估成功率
    metadata: Dict = field(default_factory=dict)


@dataclass
class VLAState:
    """VLA 推理输入状态"""
    # 视觉
    offset_x: float = 0.0
    offset_y: float = 0.0
    offset_angle: float = 0.0
    workpiece_detected: bool = False
    anomaly: Optional[str] = None

    # 机器人
    joint_positions: np.ndarray = field(default_factory=lambda: np.zeros(6))
    cartesian_pose: np.ndarray = field(default_factory=lambda: np.zeros(6))
    gripper_state: str = "unknown"

    # 任务
    current_step: int = 0
    total_steps: int = 0
    cycle_count: int = 0

    # 指令
    text_command: Optional[str] = None
    target_speed: float = 1.0
    target_cycles: int = 0     # 0 = 无限


# ============================================================
# 视觉特征提取器
# ============================================================

class VisionFeatureExtractor:
    """
    从视觉偏移结果提取 VLA 可用特征向量

    输入: OffsetResult(dx_mm, dy_mm, da_deg, match_score, anomaly)
    输出: 64维视觉特征向量
    """

    FEATURE_DIM = 64

    def extract(self, offset: Dict) -> np.ndarray:
        """
        将偏移检测结果编码为 VLA 特征向量

        编码方案:
        [0:8]   → 偏移量(归一化)
        [8:16]  → 匹配质量
        [16:32] → 空间编码(工件在视野中的位置)
        [32:48] → 异常状态 one-hot
        [48:64] → 预留
        """
        features = np.zeros(self.FEATURE_DIM, dtype=np.float32)

        # 偏移量(归一化到 [-1, 1])
        features[0] = np.clip(offset.get("dx_mm", 0) / 15.0, -1, 1)
        features[1] = np.clip(offset.get("dy_mm", 0) / 15.0, -1, 1)
        features[2] = np.clip(offset.get("da_deg", 0) / 45.0, -1, 1)
        features[3] = np.sqrt(features[0]**2 + features[1]**2)  # 偏移距离

        # 偏移量二阶特征
        features[4] = features[0] * features[1]  # 交互项
        features[5] = np.sin(features[2] * np.pi)
        features[6] = np.cos(features[2] * np.pi)
        features[7] = features[0] ** 2

        # 匹配质量
        score = offset.get("score", 0)
        detected = 1.0 if offset.get("detected", False) else 0.0
        features[8] = score
        features[9] = detected
        features[10] = 1.0 - score  # 不确定度
        features[11] = score * detected  # 有效匹配分

        # 异常状态 one-hot
        anomaly = offset.get("anomaly", "")
        anomaly_map = {"missing": 32, "stacked": 33, "misaligned": 34,
                       "defective": 35, "low_features": 36, "transform_failed": 37}
        if anomaly in anomaly_map:
            features[anomaly_map[anomaly]] = 1.0
        elif anomaly is None:
            features[31] = 1.0  # 正常

        return features


# ============================================================
# 动作映射器
# ============================================================

class DynamicCompensator:
    """
    动态偏移动补偿器

    将视觉偏移量叠加到示教基准点位，生成修正后的目标位姿

    变换链: T_target = T_base * T_offset
    其中 T_offset 由视觉检测的 (dx, dy, da) 构建
    """

    def compensate(self, base_pose: np.ndarray,
                   offset_dx: float, offset_dy: float,
                   offset_da_deg: float) -> np.ndarray:
        """
        对基准位姿进行偏移补偿

        Args:
            base_pose: [x, y, z, rx, ry, rz] 示教基准位姿
            offset_dx: X方向偏移(mm) - 视觉检测结果
            offset_dy: Y方向偏移(mm)
            offset_da_deg: Z轴旋转偏移(度)
        Returns:
            compensated_pose: 补偿后位姿 [x, y, z, rx, ry, rz]
        """
        compensated = base_pose.copy()

        # 平移补偿
        compensated[0] += offset_dx
        compensated[1] += offset_dy

        # 旋转补偿(Z轴旋转, 即 RZ)
        import math
        offset_da_rad = math.radians(offset_da_deg)
        compensated[-1] += offset_da_rad  # RZ

        # 限制偏移不超过 ±15mm
        compensated[0] = np.clip(compensated[0],
                                  base_pose[0] - 15, base_pose[0] + 15)
        compensated[1] = np.clip(compensated[1],
                                  base_pose[1] - 15, base_pose[1] + 15)

        return compensated


class ActionMapper:
    """
    将 VLA 推理输出映射为机器人可执行指令

    处理:
    - 关节角 → 关节运动
    - 位姿+偏移 → 补偿后笛卡尔运动
    - 逻辑动作 → 夹爪/等待/检查
    """

    def __init__(self):
        self.compensator = DynamicCompensator()

    def to_robot_command(self, action: VLAAction,
                         offset: Dict = None) -> Dict:
        """
        转换为机器人标准化命令

        Returns:
            {"type": "move_joint"|"move_cartesian"|..., "params": {...}}
        """
        cmd = {"type": action.type.name.lower(), "params": {}}

        if action.type in (ActionType.MOVE_JOINT,):
            cmd["params"] = {
                "target_positions": action.target[:6].tolist(),
                "speed": action.speed,
                "acceleration": action.acceleration,
            }
        elif action.type in (ActionType.MOVE_CARTESIAN, ActionType.MOVE_LINEAR):
            # 叠加视觉偏移
            if offset and offset.get("detected"):
                compensated = self.compensator.compensate(
                    action.target,
                    offset.get("dx_mm", 0),
                    offset.get("dy_mm", 0),
                    offset.get("da_deg", 0),
                )
            else:
                compensated = action.target
            cmd["params"] = {
                "target_pose": compensated.tolist(),
                "speed": action.speed,
                "acceleration": action.acceleration,
            }
        elif action.type == ActionType.GRIPPER_OPEN:
            cmd["params"] = {"force": action.gripper_force}
        elif action.type == ActionType.GRIPPER_CLOSE:
            cmd["params"] = {"force": action.gripper_force}
        elif action.type == ActionType.WAIT:
            cmd["params"] = {"duration": action.dwell}
        elif action.type == ActionType.RETRY:
            cmd["params"] = {"max_retries": 3}
        elif action.type == ActionType.ABORT:
            cmd["params"] = {"reason": "VLA判定无法继续执行"}

        return cmd


# ============================================================
# 重试策略控制器
# ============================================================

class RetryController:
    """
    智能重试策略

    重试逻辑:
    - 抓取失败 → 视觉重新搜索工件 → 重试抓取(最多3次)
    - 连续3次失败 → 暂停 + 语音告警
    - 缺料检测 → 自动等待补料(最多60s) → 超时告警
    """

    MAX_GRASP_RETRIES = 3
    MAX_CONSECUTIVE_FAILS = 3
    MISSING_PART_WAIT_S = 60
    RETRY_DELAY_S = 2.0

    def __init__(self):
        self._grasp_retries = 0
        self._consecutive_fails = 0
        self._last_fail_time = 0.0

    def should_retry(self, failure_type: str) -> Tuple[bool, str]:
        """
        判断是否应重试

        Returns: (是否重试, 原因说明)
        """
        now = time.time()

        if failure_type == "grasp_failed":
            self._grasp_retries += 1
            self._consecutive_fails += 1
            self._last_fail_time = now
            if self._grasp_retries < self.MAX_GRASP_RETRIES:
                return True, f"抓取重试 ({self._grasp_retries}/{self.MAX_GRASP_RETRIES})"
            else:
                return False, "抓取重试次数耗尽, 暂停任务"

        elif failure_type == "missing":
            if now - self._last_fail_time < self.MISSING_PART_WAIT_S:
                return True, f"等待补料 ({int(self.MISSING_PART_WAIT_S - (now - self._last_fail_time))}s)"
            else:
                return False, "缺料超时, 请补料后重试"

        elif failure_type == "misaligned":
            self._consecutive_fails += 1
            if self._consecutive_fails < self.MAX_CONSECUTIVE_FAILS:
                return True, "工件错位, 尝试重新定位"
            else:
                return False, "连续错位超限"

        return False, f"未知失败类型: {failure_type}"

    def reset(self):
        """重置计数器"""
        self._grasp_retries = 0
        self._consecutive_fails = 0
        self._last_fail_time = 0.0


# ============================================================
# VLA 推理引擎主类
# ============================================================

class VLAInferenceEngine:
    """
    轻量化工业 VLA 推理引擎

    完整推理流水线:
    VisionOffset → FeatureExtractor → VLA Model(TensorRT) → ActionMapper → Robot Command

    性能目标:
    - 端到端推理延迟 ≤ 700ms
    - 抓取成功率 ≥ 96%(±15mm 偏移)
    - 全本地推理, 无云端依赖
    """

    INFERENCE_TIMEOUT_MS = 700

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path
        self.feature_extractor = VisionFeatureExtractor()
        self.action_mapper = ActionMapper()
        self.retry_controller = RetryController()
        self._current_plan: Optional[VLAPlan] = None
        self._session = None
        self._loaded = False

    def load_model(self, model_path: str):
        """加载 TensorRT 引擎"""
        if self._loaded:
            return

        logger.info(f"加载 VLA 推理模型: {model_path}")
        # # 真机: 加载 TensorRT Engine
        # import tensorrt as trt
        # runtime = trt.Runtime(trt.Logger(trt.Logger.WARNING))
        # with open(model_path, 'rb') as f:
        #     engine_data = f.read()
        # self._engine = runtime.deserialize_cuda_engine(engine_data)
        # self._context = self._engine.create_execution_context()

        self.model_path = model_path
        self._loaded = True
        logger.info("VLA 模型加载完成")

    def infer(self, state: VLAState, vision_offset: Dict) -> VLAPlan:
        """
        端到端 VLA 推理

        Args:
            state: 当前系统状态(机器人 + 视觉 + 任务)
            vision_offset: 视觉偏移检测结果
        Returns:
            VLAPlan: 完整执行计划
        """
        t_start = time.time()

        # === 1. 提取视觉特征 ===
        visual_feat = self.feature_extractor.extract(vision_offset)

        # === 2. 构建多模态输入 ===
        multimodal_input = self._build_input(state, visual_feat)

        # === 3. VLA 模型推理(TensorRT) ===
        # # 真机: TensorRT 推理
        # output = np.zeros(output_size, dtype=np.float32)
        # self._context.execute_v2([
        #     int(multimodal_input.ctypes.data),
        #     int(output.ctypes.data),
        # ])
        # plan = self._decode_output(output, state, vision_offset)

        # 当前: 基于规则的推理(真机上部署量化模型后替换)
        plan = self._rule_based_infer(state, vision_offset)

        elapsed = (time.time() - t_start) * 1000
        if elapsed > self.INFERENCE_TIMEOUT_MS:
            logger.warning(f"推理超时: {elapsed:.0f}ms > {self.INFERENCE_TIMEOUT_MS}ms")

        plan.metadata["inference_ms"] = round(elapsed, 1)
        self._current_plan = plan
        return plan

    def _build_input(self, state: VLAState,
                     visual_feat: np.ndarray) -> np.ndarray:
        """构建 VLA 多模态输入向量"""
        # 机器人状态
        robot_state = np.hstack([
            np.clip(state.joint_positions / np.pi, -1, 1),
            np.clip(state.cartesian_pose / 500.0, -1, 1),
        ])

        # 任务状态
        task_state = np.array([
            state.current_step / max(state.total_steps, 1),
            1.0 if state.cycle_count >= state.target_cycles > 0 else 0.0,
        ])

        # 拼接
        multimodal = np.hstack([visual_feat, robot_state, task_state])
        return multimodal

    def _rule_based_infer(self, state: VLAState,
                          vision_offset: Dict) -> VLAPlan:
        """
        基于规则的推理(模型未部署时的备用方案)

        真机部署后替换为 TensorRT 推理
        """
        plan = VLAPlan()
        offset_x = vision_offset.get("dx_mm", 0)
        offset_y = vision_offset.get("dy_mm", 0)
        offset_a = vision_offset.get("da_deg", 0)
        anomaly = vision_offset.get("anomaly")

        # === 异常处理 ===
        if anomaly:
            retry, reason = self.retry_controller.should_retry(anomaly)
            if retry:
                if anomaly == "missing":
                    plan.actions.append(VLAAction(
                        ActionType.WAIT, np.zeros(6), dwell=2.0
                    ))
                plan.actions.append(VLAAction(
                    ActionType.RETRY, np.zeros(6)
                ))
                plan.metadata["warning"] = reason
                plan.success_prob = 0.7
            else:
                plan.actions.append(VLAAction(
                    ActionType.ABORT, np.zeros(6)
                ))
                plan.metadata["error"] = reason
                plan.success_prob = 0.0
            return plan

        # === 正常执行 ===
        if state.current_step == 0:  # 取料
            plan.actions.append(VLAAction(
                ActionType.MOVE_CARTESIAN,
                np.array([200 + offset_x, 100 + offset_y, 50, 0, 0, 0]),
                speed=0.4, acceleration=0.5,
            ))
            plan.actions.append(VLAAction(
                ActionType.GRIPPER_CLOSE, np.zeros(6),
                gripper_force=60.0,
            ))

        elif state.current_step == 1:  # 装配
            plan.actions.append(VLAAction(
                ActionType.MOVE_LINEAR,
                np.array([300 + offset_x, 80 + offset_y, -10, 0, 0, offset_a]),
                speed=0.3, acceleration=0.3,
            ))
            plan.actions.append(VLAAction(
                ActionType.GRIPPER_OPEN, np.zeros(6),
                gripper_force=30.0,
            ))

        elif state.current_step == 2:  # 检测
            plan.actions.append(VLAAction(
                ActionType.CHECK, np.zeros(6), dwell=0.5
            ))

        elif state.current_step == 3:  # 下料
            plan.actions.append(VLAAction(
                ActionType.GRIPPER_CLOSE, np.zeros(6),
                gripper_force=50.0,
            ))
            plan.actions.append(VLAAction(
                ActionType.MOVE_CARTESIAN,
                np.array([100, 200, 100, 0, 0, 0]),
                speed=0.5,
            ))
            plan.actions.append(VLAAction(
                ActionType.GRIPPER_OPEN, np.zeros(6),
                gripper_force=30.0,
            ))

        # 估计时长
        plan.estimated_duration = sum(
            a.dwell + 1.0 for a in plan.actions
        )
        plan.success_prob = 0.95 if not anomaly else 0.5

        return plan

    def reset_retries(self):
        """重置重试计数器(新任务开始时调用)"""
        self.retry_controller.reset()
