"""
RoboVLA V2.0 - 遨博(Aubo)机械臂适配插件

基于遨博原厂 ROS2 SDK 二次封装，实现 RobotBase 统一接口
适配型号: i3, i5, i10
"""

import time
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
import numpy as np

# ROS2 imports (在实际 Jetson 环境中取消注释)
# import rclpy
# from rclpy.node import Node
# from sensor_msgs.msg import JointState as RosJointState
# from geometry_msgs.msg import PoseStamped

from hardware_plugin.robot_base import (
    RobotBase, RobotState, JointState, CartesianPose,
    MotionParams, TrajectoryPoint, GripperState, FaultInfo
)

logger = logging.getLogger(__name__)


# ============================================================
# 遨博专用数据类
# ============================================================

@dataclass
class AuboConfig:
    """遨博机械臂配置参数"""
    DEFAULT_IP: str = "192.168.1.100"
    DEFAULT_PORT: int = 8899
    JOINT_LIMITS: List[List[float]] = None

    def __post_init__(self):
        if self.JOINT_LIMITS is None:
            # i5 默认关节限位(rad)
            self.JOINT_LIMITS = [
                [-3.05, 3.05],   # J1: 基础 ±175°
                [-3.05, 3.05],   # J2: 肩部 ±175°
                [-3.05, 3.05],   # J3: 肘部 ±175°
                [-3.05, 3.05],   # J4: 腕部1 ±175°
                [-3.05, 3.05],   # J5: 腕部2 ±175°
                [-3.05, 3.05],   # J6: 腕部3 ±175°
            ]


# Aubo 故障码映射
AUBO_FAULT_MAP = {
    0x0001: FaultInfo(0x0001, "关节1过载", "error"),
    0x0002: FaultInfo(0x0002, "关节2过载", "error"),
    0x0003: FaultInfo(0x0003, "关节3过载", "error"),
    0x0004: FaultInfo(0x0004, "关节4过载", "error"),
    0x0005: FaultInfo(0x0005, "关节5过载", "error"),
    0x0006: FaultInfo(0x0006, "关节6过载", "error"),
    0x0010: FaultInfo(0x0010, "控制器通信超时", "critical"),
    0x0011: FaultInfo(0x0011, "抱闸异常", "critical"),
    0x0012: FaultInfo(0x0012, "电机过温", "error"),
    0x0013: FaultInfo(0x0013, "驱动器故障", "critical"),
    0x0020: FaultInfo(0x0020, "碰撞检测触发", "warning"),
    0x0021: FaultInfo(0x0021, "安全急停触发", "critical"),
    0x0022: FaultInfo(0x0022, "力矩超限", "error"),
    0x0030: FaultInfo(0x0030, "姿态异常", "error"),
    0x0031: FaultInfo(0x0031, "轨迹规划失败", "error"),
    0x00FF: FaultInfo(0x00FF, "未知故障", "error"),
}


class AuboPlugin(RobotBase):
    """
    遨博协作机械臂适配插件

    使用方式:
        robot = AuboPlugin(robot_ip="192.168.1.100")
        robot.connect()
        robot.move_joint(target_positions)
        print(robot.get_cartesian_pose())
    """

    def __init__(self, robot_ip: str = "192.168.1.100",
                 port: int = 8899):
        super().__init__(robot_ip, port)
        self._config = AuboConfig()
        self._model_name = "Aubo"

        # # ROS2节点初始化 (真机部署时启用)
        # self._node: Optional[Node] = None
        # self._joint_sub = None
        # self._pose_sub = None

        self._joint_limits = [
            tuple(lim) for lim in self._config.JOINT_LIMITS
        ]
        self._last_pose = CartesianPose(np.zeros(3), np.zeros(3))

        # 拖拽示教标志
        self._in_drag_mode = False

        logger.info(f"AuboPlugin 初始化, IP={robot_ip}:{port}")

    # ========== 连接管理 ==========

    def connect(self) -> bool:
        """连接遨博机械臂控制器"""
        logger.info(f"连接遨博机器人 {self._robot_ip}:{self._port}...")
        try:
            # ==============================================
            # 真机部署时替换为以下代码:
            # rclpy.init(args=None)
            # self._node = Node('aubo_plugin_node')
            #
            # # 订阅关节状态
            # self._joint_sub = self._node.create_subscription(
            #     RosJointState, '/joint_states', self._on_joint_state, 10)
            #
            # # 订阅末端位姿
            # self._pose_sub = self._node.create_subscription(
            #     PoseStamped, '/aubo/tcp_pose', self._on_pose, 10)
            #
            # # 等待首次数据到达
            # start = time.time()
            # while self._joint_state.positions.sum() == 0:
            #     rclpy.spin_once(self._node, timeout_sec=0.1)
            #     if time.time() - start > 5.0:
            #         raise TimeoutError("等待关节状态超时")
            # ==============================================

            # 模拟连接成功
            self._joint_state = JointState(
                np.zeros(6), np.zeros(6), np.zeros(6),
                timestamp=time.time()
            )
            self._serial_number = f"AUBO-{hash(self._robot_ip) & 0xFFFFFF:06X}"
            self._firmware_version = "v4.5.2"
            self._model_name = "Aubo-i5"

            self._notify_state_change(RobotState.IDLE)
            logger.info(f"遨博连接成功 SN={self._serial_number}")
            return True

        except Exception as e:
            logger.error(f"遨博连接失败: {e}")
            self._notify_state_change(RobotState.ERROR)
            return False

    def disconnect(self) -> bool:
        """断开遨博连接"""
        logger.info("断开遨博连接...")
        try:
            self.stop("immediate")
            # if self._node:
            #     self._node.destroy_node()
            #     rclpy.shutdown()
            self._notify_state_change(RobotState.DISCONNECTED)
            return True
        except Exception as e:
            logger.error(f"断开连接异常: {e}")
            return False

    def is_connected(self) -> bool:
        return self._state not in [RobotState.DISCONNECTED, RobotState.ERROR]

    # ========== 运动控制 ==========

    def home(self) -> bool:
        """回零操作"""
        logger.info("执行回零...")
        self._notify_state_change(RobotState.HOMING)
        try:
            home_pose = np.array([0.0, -0.3, 0.6, -0.3, 0.0, 0.0])
            return self.move_joint(home_pose)
        except Exception as e:
            logger.error(f"回零失败: {e}")
            return False

    def move_joint(self, target_positions: np.ndarray,
                   params: MotionParams = MotionParams()) -> bool:
        """关节空间运动"""
        target = np.asarray(target_positions, dtype=np.float32)

        # 安全检查
        if not self.is_within_joint_limits(target):
            logger.error("目标关节角超出硬限位")
            return False

        logger.debug(f"关节运动 → {np.round(target, 3)}")

        # # 真机代码:
        # goal = JointTrajectory()
        # goal.joint_names = [f'joint{i+1}' for i in range(6)]
        # point = JointTrajectoryPoint()
        # point.positions = target.tolist()
        # point.time_from_start = Duration(seconds=2.0)
        # goal.points = [point]
        # self._trajectory_client.send_goal(goal)

        self._notify_state_change(RobotState.MOVING)
        time.sleep(0.5)  # 模拟运动时间

        # 更新内部状态
        self._joint_state.positions = target
        self._last_pose = CartesianPose(
            target[:3] * 0.1, target[3:] * 0.01, time.time()
        )

        self._notify_state_change(RobotState.IDLE)
        return True

    def move_cartesian(self, target_pose: CartesianPose,
                       params: MotionParams = MotionParams()) -> bool:
        """笛卡尔空间运动"""
        logger.debug(f"笛卡尔运动 → pos={target_pose.position}, rpy={target_pose.orientation}")
        self._notify_state_change(RobotState.MOVING)

        # 模拟逆运动学求解 + 运动执行
        self._last_pose = target_pose
        time.sleep(0.5)

        self._notify_state_change(RobotState.IDLE)
        return True

    def move_linear(self, target_pose: CartesianPose,
                    params: MotionParams = MotionParams()) -> bool:
        """直线运动(末端保持直线路径)"""
        logger.debug(f"直线运动 → pos={target_pose.position}")
        self._notify_state_change(RobotState.MOVING)

        # 计算当前姿态到目标的线性插值
        start = self._last_pose.position
        steps = 10
        for i in range(1, steps + 1):
            interp_pos = start + (target_pose.position - start) * (i / steps)
            # 每步做一次逆运动学 + 微调
            time.sleep(0.05)

        self._last_pose = target_pose
        self._notify_state_change(RobotState.IDLE)
        return True

    def stop(self, mode: str = "smooth") -> bool:
        """停止运动"""
        accel = -50.0 if mode == "immediate" else -10.0
        logger.debug(f"停止运动 mode={mode}, decel={accel}")
        self._notify_state_change(RobotState.PAUSED)
        return True

    def emergency_stop(self) -> bool:
        """紧急停止"""
        logger.warning("⚠️ 紧急停止触发!")
        try:
            # 立即断电制动
            self._notify_state_change(RobotState.EMERGENCY_STOP)
            self._notify_fault(FaultInfo(
                0x0021, "安全急停触发", "critical",
                time.time(), recoverable=False
            ))
            return True
        except Exception as e:
            logger.error(f"急停异常: {e}")
            return False

    # ========== 拖拽示教 ==========

    def enable_drag_mode(self) -> bool:
        """开启拖拽示教 - 释放抱闸"""
        logger.info("开启拖拽示教模式, 释放各关节抱闸...")
        try:
            # # 真机: 发送Freedrive指令
            # self._node.call_service('/aubo/enable_drag', ...)
            self._in_drag_mode = True
            self._notify_state_change(RobotState.DRAGGING)
            logger.info("拖拽示教模式已开启，请手动拖拽机械臂")
            return True
        except Exception as e:
            logger.error(f"开启拖拽示教失败: {e}")
            return False

    def disable_drag_mode(self) -> bool:
        """关闭拖拽示教 - 锁紧抱闸"""
        logger.info("关闭拖拽示教模式, 锁紧关节抱闸...")
        try:
            self._in_drag_mode = False
            self._notify_state_change(RobotState.IDLE)
            return True
        except Exception as e:
            logger.error(f"关闭拖拽示教失败: {e}")
            return False

    def is_dragging(self) -> bool:
        return self._in_drag_mode

    # ========== 状态查询 ==========

    def get_joint_state(self) -> JointState:
        """读取当前关节状态"""
        # # 真机: 从 ROS2 订阅获取
        # rclpy.spin_once(self._node, timeout_sec=0.01)
        return JointState(
            np.copy(self._joint_state.positions),
            np.copy(self._joint_state.velocities),
            np.copy(self._joint_state.efforts),
            timestamp=time.time()
        )

    def get_cartesian_pose(self) -> CartesianPose:
        """末端位姿 - 基于正运动学实时计算"""
        # # 真机: 从 URDF + 关节角计算正运动学
        # return self._compute_fk(self._joint_state.positions)
        return CartesianPose(
            np.copy(self._last_pose.position),
            np.copy(self._last_pose.orientation),
            timestamp=time.time()
        )

    def get_gripper_state(self) -> GripperState:
        return self._gripper_state

    def get_state(self) -> RobotState:
        return self._state

    def get_faults(self) -> List[FaultInfo]:
        """获取当前活跃故障"""
        active = []
        # # 真机: 读取故障寄存器
        # for code_str in self._node.get_parameter('faults').value:
        #     active.append(AUBO_FAULT_MAP.get(int(code_str)))
        return active

    # ========== 夹爪控制 ==========

    def gripper_open(self, force: float = 50.0) -> bool:
        logger.info("打开夹爪")
        self._gripper_state = GripperState.OPEN
        return True

    def gripper_close(self, force: float = 50.0) -> bool:
        logger.info("闭合夹爪")
        self._gripper_state = GripperState.CLOSED
        return True

    def gripper_set_force(self, force: float) -> bool:
        logger.info(f"设置夹爪力: {force}N")
        return True

    # ========== 参数配置 ==========

    def set_speed_limit(self, ratio: float) -> bool:
        ratio = max(0.01, min(1.0, ratio))
        self._speed_limit = ratio
        logger.info(f"速度上限设置为 {ratio:.0%}")
        return True

    def set_force_limit(self, force_n: float) -> bool:
        self._force_limit = force_n
        logger.info(f"力矩上限设置为 {force_n}N")
        return True

    def load_config(self, config_path: str) -> bool:
        import yaml
        with open(config_path, 'r') as f:
            cfg = yaml.safe_load(f)
        if 'speed_limit' in cfg:
            self.set_speed_limit(cfg['speed_limit'])
        if 'force_limit' in cfg:
            self.set_force_limit(cfg['force_limit'])
        logger.info(f"已加载配置: {config_path}")
        return True

    # ========== 硬件信息 ==========

    def get_serial_number(self) -> str:
        return self._serial_number

    def get_model_info(self) -> Dict:
        return {
            "brand": "Aubo",
            "model": self._model_name,
            "firmware": self._firmware_version,
            "serial": self._serial_number,
            "dof": 6,
            "payload_kg": 5.0,
            "reach_mm": 880,
        }

    # ========== ROS2 回调(真机) ==========

    def _on_joint_state(self, msg):
        """ROS2 关节状态回调"""
        self._joint_state.positions = np.array(msg.position[:6])
        self._joint_state.velocities = np.array(msg.velocity[:6])
        self._joint_state.efforts = np.array(msg.effort[:6])
        self._joint_state.timestamp = time.time()

        # 碰撞检测
        risk = self.check_collision_risk()
        if risk:
            logger.warning(f"碰撞风险: {risk}")

    def _on_pose(self, msg):
        """ROS2 位姿回调"""
        from scipy.spatial.transform import Rotation
        self._last_pose.position = np.array([
            msg.pose.position.x, msg.pose.position.y, msg.pose.position.z
        ])
        rot = Rotation.from_quat([
            msg.pose.orientation.x, msg.pose.orientation.y,
            msg.pose.orientation.z, msg.pose.orientation.w
        ])
        self._last_pose.orientation = np.array(rot.as_euler('xyz'))
        self._last_pose.timestamp = time.time()
