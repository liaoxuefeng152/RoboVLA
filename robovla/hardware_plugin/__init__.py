"""
RoboVLA V2.0 - 硬件适配插件层
提供跨品牌机器人统一抽象接口和适配插件
"""

from hardware_plugin.robot_base import (
    RobotBase, RobotState, JointState, CartesianPose,
    MotionParams, TrajectoryPoint, GripperState, FaultInfo
)
from hardware_plugin.plugins.plugin_factory import RobotPluginFactory

__all__ = [
    'RobotBase', 'RobotState', 'JointState', 'CartesianPose',
    'MotionParams', 'TrajectoryPoint', 'GripperState', 'FaultInfo',
    'RobotPluginFactory'
]
