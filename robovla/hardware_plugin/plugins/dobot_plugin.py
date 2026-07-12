"""
RoboVLA V2.0 - 越疆(Dobot)机械臂适配插件

适配型号: D03, D06
基于越疆原厂 SDK 二次封装
"""

import time
import logging
from typing import List, Dict, Optional
import numpy as np

from hardware_plugin.robot_base import (
    RobotBase, RobotState, JointState, CartesianPose,
    MotionParams, GripperState, FaultInfo
)

logger = logging.getLogger(__name__)


class DobotPlugin(RobotBase):
    """
    越疆协作机械臂适配插件

    使用方式:
        robot = DobotPlugin(robot_ip="192.168.5.1", port=6000)
        robot.connect()
        robot.enable_drag_mode()
    """

    DOBOT_JOINT_LIMITS = [
        (-2.356, 2.356),   # J1
        (-2.356, 2.356),   # J2
        (-2.356, 2.356),   # J3
        (-2.356, 2.356),   # J4
        (-2.356, 2.356),   # J5
        (-2.356, 2.356),   # J6
    ]

    def __init__(self, robot_ip: str = "192.168.5.1",
                 port: int = 6000):
        super().__init__(robot_ip, port)
        self._joint_limits = [
            tuple(lim) for lim in self.DOBOT_JOINT_LIMITS
        ]
        self._model_name = "Dobot-D06"
        self._in_drag_mode = False

    def connect(self) -> bool:
        logger.info(f"连接越疆机器人 {self._robot_ip}:{self._port}")
        try:
            # # 真机: import DobotSDK
            # self._dashboard = DobotSDK.Dashboard(ip=self._robot_ip)
            # self._dashboard.EnableRobot()
            # self._move = DobotSDK.Move(ip=self._robot_ip)

            self._joint_state = JointState(np.zeros(6), np.zeros(6), np.zeros(6))
            self._serial_number = f"DOBOT-{hash(self._robot_ip) & 0xFFFFFF:06X}"
            self._firmware_version = "v3.8.0"
            self._notify_state_change(RobotState.IDLE)
            logger.info(f"越疆连接成功 SN={self._serial_number}")
            return True
        except Exception as e:
            logger.error(f"越疆连接失败: {e}")
            return False

    def disconnect(self) -> bool:
        self.stop("immediate")
        self._notify_state_change(RobotState.DISCONNECTED)
        return True

    def is_connected(self) -> bool:
        return self._state not in [RobotState.DISCONNECTED, RobotState.ERROR]

    def home(self) -> bool:
        self._notify_state_change(RobotState.HOMING)
        home_j = np.array([0.0, 0.0, 0.0, 0.0, 1.57, 0.0])
        return self.move_joint(home_j)

    def move_joint(self, target_positions: np.ndarray,
                   params: MotionParams = MotionParams()) -> bool:
        target = np.asarray(target_positions, dtype=np.float32)
        if not self.is_within_joint_limits(target):
            return False

        self._notify_state_change(RobotState.MOVING)
        # # 真机:
        # self._move.JointMovJ(target.tolist(), tool=0, user=0)
        self._joint_state.positions = target
        self._notify_state_change(RobotState.IDLE)
        return True

    def move_cartesian(self, target_pose: CartesianPose,
                       params: MotionParams = MotionParams()) -> bool:
        self._notify_state_change(RobotState.MOVING)
        # # 真机:
        # coord = np.hstack([target_pose.position, target_pose.orientation])
        # self._move.MovL(coord.tolist(), tool=0, user=0,
        #                  vel=params.speed*100, acc=params.acceleration*100)
        time.sleep(0.5)
        self._notify_state_change(RobotState.IDLE)
        return True

    def move_linear(self, target_pose: CartesianPose,
                    params: MotionParams = MotionParams()) -> bool:
        return self.move_cartesian(target_pose, params)  # 越疆MovL即直线

    def stop(self, mode: str = "smooth") -> bool:
        # # 真机:
        # if mode == "immediate":
        #     self._dashboard.EmergencyStop()
        # else:
        #     self._move.Stop()
        self._notify_state_change(RobotState.PAUSED)
        return True

    def emergency_stop(self) -> bool:
        self._notify_state_change(RobotState.EMERGENCY_STOP)
        self._notify_fault(FaultInfo(
            0x100, "越疆紧急停止", "critical",
            time.time(), recoverable=False
        ))
        return True

    def enable_drag_mode(self) -> bool:
        logger.info("开启越疆拖拽示教...")
        # # 真机:
        # self._dashboard.DragMode(True)
        self._in_drag_mode = True
        self._notify_state_change(RobotState.DRAGGING)
        return True

    def disable_drag_mode(self) -> bool:
        self._in_drag_mode = False
        self._notify_state_change(RobotState.IDLE)
        return True

    def is_dragging(self) -> bool:
        return self._in_drag_mode

    def get_joint_state(self) -> JointState:
        # # 真机:
        # pose_str = self._dashboard.GetAngle()
        # j = np.array([float(x) for x in pose_str.strip('{}').split(',')])
        return JointState(
            np.copy(self._joint_state.positions),
            np.copy(self._joint_state.velocities),
            np.copy(self._joint_state.efforts),
        )

    def get_cartesian_pose(self) -> CartesianPose:
        # # 真机: self._dashboard.GetPose()
        return CartesianPose(np.zeros(3), np.zeros(3))

    def get_gripper_state(self) -> GripperState:
        return self._gripper_state

    def get_state(self) -> RobotState:
        return self._state

    def get_faults(self) -> List[FaultInfo]:
        # # 真机: self._dashboard.GetErrorID()
        return []

    def gripper_open(self, force: float = 50.0) -> bool:
        self._gripper_state = GripperState.OPEN
        return True

    def gripper_close(self, force: float = 50.0) -> bool:
        self._gripper_state = GripperState.CLOSED
        return True

    def gripper_set_force(self, force: float) -> bool:
        return True

    def set_speed_limit(self, ratio: float) -> bool:
        self._speed_limit = max(0.01, min(1.0, ratio))
        # # 真机: self._dashboard.SpeedFactor(int(ratio * 100))
        return True

    def set_force_limit(self, force_n: float) -> bool:
        self._force_limit = force_n
        return True

    def load_config(self, config_path: str) -> bool:
        import yaml
        with open(config_path, 'r') as f:
            cfg = yaml.safe_load(f)
        if 'speed_limit' in cfg:
            self.set_speed_limit(cfg['speed_limit'])
        if 'force_limit' in cfg:
            self.set_force_limit(cfg['force_limit'])
        return True

    def get_serial_number(self) -> str:
        return self._serial_number

    def get_model_info(self) -> Dict:
        return {
            "brand": "Dobot",
            "model": self._model_name,
            "firmware": self._firmware_version,
            "serial": self._serial_number,
            "dof": 6,
            "payload_kg": 3.0,
            "reach_mm": 620,
        }
