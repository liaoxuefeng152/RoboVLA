"""
RoboVLA V2.0 - 机器人抽象基类
定义统一机器人接口，所有品牌插件必须继承并实现

版本: V2.0
作者: RoboVLA Team
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Dict, Tuple, Callable
import numpy as np
import logging

logger = logging.getLogger(__name__)


# ============================================================
# 数据类型定义
# ============================================================

class RobotState(Enum):
    """机器人运行状态"""
    DISCONNECTED = auto()
    IDLE = auto()
    MOVING = auto()
    DRAGGING = auto()
    HOMING = auto()
    PAUSED = auto()
    ERROR = auto()
    EMERGENCY_STOP = auto()


class GripperState(Enum):
    """夹爪状态"""
    OPEN = auto()
    CLOSED = auto()
    HOLDING = auto()
    UNKNOWN = auto()


@dataclass
class JointState:
    """关节状态数据"""
    positions: np.ndarray       # 6个关节角度(rad)
    velocities: np.ndarray      # 6个关节角速度(rad/s)
    efforts: np.ndarray         # 6个关节力矩(Nm)
    timestamp: float = 0.0

    def __post_init__(self):
        if self.positions is not None:
            self.positions = np.asarray(self.positions, dtype=np.float32)
        if self.velocities is not None:
            self.velocities = np.asarray(self.velocities, dtype=np.float32)
        if self.efforts is not None:
            self.efforts = np.asarray(self.efforts, dtype=np.float32)


@dataclass
class CartesianPose:
    """末端位姿(TCP)"""
    position: np.ndarray        # [x, y, z] 单位: mm
    orientation: np.ndarray     # [rx, ry, rz] 单位: rad (RPY)
    timestamp: float = 0.0

    def __post_init__(self):
        if self.position is not None:
            self.position = np.asarray(self.position, dtype=np.float32)
        if self.orientation is not None:
            self.orientation = np.asarray(self.orientation, dtype=np.float32)

    def to_pose_matrix(self) -> np.ndarray:
        """转为4x4齐次变换矩阵"""
        return self._rpy_to_matrix(self.position, self.orientation)

    @staticmethod
    def _rpy_to_matrix(pos: np.ndarray, rpy: np.ndarray) -> np.ndarray:
        """RPY转旋转矩阵 + 平移 → 4x4变换矩阵"""
        r, p, y = rpy
        cr, cp, cy = np.cos([r, p, y])
        sr, sp, sy = np.sin([r, p, y])

        R = np.array([
            [cy*cp, cy*sp*sr - sy*cr, cy*sp*cr + sy*sr],
            [sy*cp, sy*sp*sr + cy*cr, sy*sp*cr - cy*sr],
            [-sp,   cp*sr,            cp*cr]
        ])

        T = np.eye(4, dtype=np.float32)
        T[:3, :3] = R
        T[:3, 3] = pos
        return T


@dataclass
class MotionParams:
    """运动参数约束"""
    speed: float = 0.2            # 相对速度(0.0 ~ 1.0)
    acceleration: float = 0.3     # 相对加速度(0.0 ~ 1.0)
    blend_radius: float = 5.0     # 转弯半径(mm)
    force_limit: float = 50.0     # 力限制(N)


@dataclass
class TrajectoryPoint:
    """示教轨迹点"""
    id: int
    joint_positions: np.ndarray      # 关节角
    cartesian_pose: CartesianPose    # 末端位姿
    gripper_state: GripperState      # 夹爪状态
    dwell_time: float = 0.0          # 停留时间(s)
    force_sensor: np.ndarray = None  # 力传感器读数
    camera_frame_id: Optional[int] = None  # 关联图像帧ID


@dataclass
class FaultInfo:
    """故障信息"""
    code: int
    message: str
    severity: str = "warning"    # warning / error / critical
    timestamp: float = 0.0
    recoverable: bool = True


# ============================================================
# 机器人抽象基类
# ============================================================

class RobotBase(ABC):
    """
    机器人统一抽象接口

    所有品牌机器人插件必须实现此基类中的全部抽象方法。
    上层算法模块仅依赖此接口，与具体硬件完全解耦。
    """

    def __init__(self, robot_ip: str = "192.168.1.100", port: int = 8899):
        self._robot_ip = robot_ip
        self._port = port
        self._state = RobotState.DISCONNECTED
        self._joint_state = JointState(np.zeros(6), np.zeros(6), np.zeros(6))
        self._cartesian_pose = CartesianPose(np.zeros(3), np.zeros(3))
        self._gripper_state = GripperState.UNKNOWN
        self._fault_history: List[FaultInfo] = []
        self._state_callbacks: List[Callable[[RobotState], None]] = []
        self._fault_callbacks: List[Callable[[FaultInfo], None]] = []

        # 安全硬限位
        self._speed_limit = 0.8
        self._accel_limit = 0.6
        self._force_limit = 100.0
        self._joint_limits: List[Tuple[float, float]] = []

        # 硬件信息
        self._serial_number: str = ""
        self._firmware_version: str = ""
        self._model_name: str = ""

    # ========== 连接管理 ==========

    @abstractmethod
    def connect(self) -> bool:
        """
        连接机器人控制器
        Returns: True=连接成功, False=失败
        """
        ...

    @abstractmethod
    def disconnect(self) -> bool:
        """断开连接并安全停止"""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """检查连接状态"""
        ...

    # ========== 运动控制 ==========

    @abstractmethod
    def home(self) -> bool:
        """
        回零操作
        安全返回机械零点，自动避开障碍物
        Returns: True=回零成功
        """
        ...

    @abstractmethod
    def move_joint(self, target_positions: np.ndarray,
                   params: MotionParams = MotionParams()) -> bool:
        """
        关节空间运动
        Args:
            target_positions: 6维目标关节角度(rad)
            params: 运动参数
        Returns: True=运动执行成功
        """
        ...

    @abstractmethod
    def move_cartesian(self, target_pose: CartesianPose,
                       params: MotionParams = MotionParams()) -> bool:
        """
        笛卡尔空间运动
        Args:
            target_pose: 目标末端位姿(位置 + RPY)
            params: 运动参数
        Returns: True=运动执行成功
        """
        ...

    @abstractmethod
    def move_linear(self, target_pose: CartesianPose,
                    params: MotionParams = MotionParams()) -> bool:
        """
        直线运动(BLEND=0)
        Args:
            target_pose: 目标末端位姿
            params: 运动参数
        Returns: True=运动执行成功
        """
        ...

    @abstractmethod
    def stop(self, mode: str = "smooth") -> bool:
        """
        停止运动
        Args:
            mode: "smooth"=平滑停止, "immediate"=立即停止
        """
        ...

    @abstractmethod
    def emergency_stop(self) -> bool:
        """紧急停止 - 立即断电/制动"""
        ...

    # ========== 拖拽示教 ==========

    @abstractmethod
    def enable_drag_mode(self) -> bool:
        """
        开启拖拽示教模式
        释放各关节抱闸，允许人工拖拽
        """
        ...

    @abstractmethod
    def disable_drag_mode(self) -> bool:
        """关闭拖拽示教模式，重新锁紧抱闸"""
        ...

    @abstractmethod
    def is_dragging(self) -> bool:
        """是否正在被拖拽中"""
        ...

    # ========== 状态查询 ==========

    @abstractmethod
    def get_joint_state(self) -> JointState:
        """获取当前关节状态"""
        ...

    @abstractmethod
    def get_cartesian_pose(self) -> CartesianPose:
        """获取末端笛卡尔位姿"""
        ...

    @abstractmethod
    def get_gripper_state(self) -> GripperState:
        """获取夹爪状态"""
        ...

    @abstractmethod
    def get_state(self) -> RobotState:
        """获取机器人运行状态"""
        ...

    @abstractmethod
    def get_faults(self) -> List[FaultInfo]:
        """获取当前故障列表"""
        ...

    # ========== 夹爪控制(通过IO) ==========

    @abstractmethod
    def gripper_open(self, force: float = 50.0) -> bool:
        """打开夹爪"""
        ...

    @abstractmethod
    def gripper_close(self, force: float = 50.0) -> bool:
        """闭合夹爪"""
        ...

    @abstractmethod
    def gripper_set_force(self, force: float) -> bool:
        """设置夹爪抓取力(N)"""
        ...

    # ========== 参数配置 ==========

    @abstractmethod
    def set_speed_limit(self, ratio: float) -> bool:
        """
        设置速度上限比例(0.0 ~ 1.0)
        低于硬件原生限位，用于二次安全防护
        """
        ...

    @abstractmethod
    def set_force_limit(self, force_n: float) -> bool:
        """设置力矩上限(N)"""
        ...

    @abstractmethod
    def load_config(self, config_path: str) -> bool:
        """加载机器人配置文件(YAML)"""
        ...

    # ========== 硬件信息 ==========

    @abstractmethod
    def get_serial_number(self) -> str:
        """获取硬件序列号(用于授权绑定)"""
        ...

    @abstractmethod
    def get_model_info(self) -> Dict:
        """获取型号/固件等信息"""
        ...

    # ========== 状态回调 ==========

    def register_state_callback(self, callback: Callable[[RobotState], None]):
        """注册状态变更回调"""
        self._state_callbacks.append(callback)

    def register_fault_callback(self, callback: Callable[[FaultInfo], None]):
        """注册故障回调"""
        self._fault_callbacks.append(callback)

    def _notify_state_change(self, new_state: RobotState):
        """通知状态变更"""
        self._state = new_state
        for cb in self._state_callbacks:
            try:
                cb(new_state)
            except Exception as e:
                logger.error(f"State callback error: {e}")

    def _notify_fault(self, fault: FaultInfo):
        """通知故障"""
        self._fault_history.append(fault)
        for cb in self._fault_callbacks:
            try:
                cb(fault)
            except Exception as e:
                logger.error(f"Fault callback error: {e}")

    # ========== 安全检测 ==========

    def check_collision_risk(self) -> Optional[str]:
        """
        碰撞风险检测
        基于当前力矩与运动趋势判断碰撞可能
        Returns: None=安全, str=风险描述
        """
        if self._joint_state.efforts is not None:
            max_effort = np.max(np.abs(self._joint_state.efforts))
            if max_effort > self._force_limit * 0.9:
                return f"力矩接近限位: {max_effort:.1f}/{self._force_limit:.1f}N"
        return None

    def is_within_joint_limits(self, positions: np.ndarray) -> bool:
        """检查目标关节角是否在硬限位内"""
        if not self._joint_limits:
            return True
        for i, (lo, hi) in enumerate(self._joint_limits):
            if i < len(positions):
                if positions[i] < lo or positions[i] > hi:
                    return False
        return True

    def __del__(self):
        """析构时安全断开"""
        try:
            if self.is_connected():
                self.disconnect()
        except Exception:
            pass
