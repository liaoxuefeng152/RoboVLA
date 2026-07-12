"""
RoboVLA V2.0 - B样条轨迹平滑处理
给定拖拽示教录制的原始轨迹点，过滤人工抖动，生成平滑运动轨迹
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import json
import logging

logger = logging.getLogger("RoboVLA.Trajectory")


@dataclass
class Waypoint:
    """示教轨迹点"""
    timestamp: float          # 采集时刻(ms)
    joints: List[float]       # 关节角度 [j1..j6]
    xyz: List[float]          # 末端位置 [x,y,z]
    rpy: List[float]          # 末端姿态 [roll,pitch,yaw]
    gripper: float = 0.0      # 夹爪开度
    image_id: Optional[int] = None  # 对应图像帧ID

    def to_dict(self) -> dict:
        return {
            "t": self.timestamp,
            "joints": self.joints,
            "xyz": self.xyz,
            "rpy": self.rpy,
            "gripper": self.gripper,
            "img_id": self.image_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Waypoint":
        return cls(
            timestamp=d["t"],
            joints=d["joints"],
            xyz=d["xyz"],
            rpy=d["rpy"],
            gripper=d.get("gripper", 0.0),
            image_id=d.get("img_id"),
        )


@dataclass
class Trajectory:
    """完整示教轨迹"""
    task_id: str
    robot_brand: str
    waypoints: List[Waypoint] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    original_count: int = 0
    smoothed_count: int = 0

    def add(self, wp: Waypoint):
        self.waypoints.append(wp)

    def to_json(self, filepath: str) -> str:
        data = {
            "version": "2.0",
            "task_id": self.task_id,
            "robot_brand": self.robot_brand,
            "original_count": self.original_count,
            "smoothed_count": self.smoothed_count,
            "metadata": self.metadata,
            "waypoints": [wp.to_dict() for wp in self.waypoints],
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        return filepath

    @classmethod
    def from_json(cls, filepath: str) -> "Trajectory":
        with open(filepath, "r") as f:
            data = json.load(f)
        traj = cls(
            task_id=data["task_id"],
            robot_brand=data["robot_brand"],
            metadata=data.get("metadata", {}),
            original_count=data.get("original_count", len(data["waypoints"])),
            smoothed_count=data.get("smoothed_count", len(data["waypoints"])),
        )
        traj.waypoints = [Waypoint.from_dict(wp) for wp in data["waypoints"]]
        return traj


class BSplineSmoother:
    """
    B样条轨迹平滑器
    使用三次B样条(cubic B-spline)对拖拽录制轨迹做平滑滤波，
    消除人工手抖和传感器噪声。

    原理:
    - 将原始轨迹点作为控制点
    - 在控制点之间均匀插值，生成平滑曲线
    - 保持端点位置不变(插值端点)
    """

    def __init__(self,
                 spline_degree: int = 3,
                 interpolation_points: int = 10,
                 smooth_factor: float = 0.5,
                 min_velocity: float = 0.001,
                 max_acceleration: float = 5.0):
        """
        :param spline_degree: B样条阶数 (3 = cubic)
        :param interpolation_points: 每段控制点之间插值点数
        :param smooth_factor: 平滑系数 (0=不平滑, 1=最大平滑)
        :param min_velocity: 最小运动速度 (rad/s or m/s)
        :param max_acceleration: 最大加速度限制
        """
        self.degree = spline_degree
        self.interp_points = interpolation_points
        self.smooth_factor = np.clip(smooth_factor, 0.0, 1.0)
        self.min_velocity = min_velocity
        self.max_acceleration = max_acceleration

    def smooth(self, trajectory: Trajectory) -> Trajectory:
        """
        对完整轨迹做 B 样条平滑
        :return: 新的平滑轨迹
        """
        if len(trajectory.waypoints) < 4:
            logger.warning("轨迹点不足(<4)，无法做B样条平滑，返回原始轨迹")
            return trajectory

        original_count = len(trajectory.waypoints)

        # 1. 提取各维数据
        t_array = np.array([wp.timestamp for wp in trajectory.waypoints])
        joints_array = np.array([wp.joints for wp in trajectory.waypoints])  # Nx6
        xyz_array = np.array([wp.xyz for wp in trajectory.waypoints])         # Nx3
        rpy_array = np.array([wp.rpy for wp in trajectory.waypoints])         # Nx3

        # 归一化时间轴
        t_norm = self._normalize_time(t_array)

        # 2. 对每个维度分别做B样条平滑
        n_joints = joints_array.shape[1]
        smoothed_joints = np.zeros_like(joints_array)
        for j in range(n_joints):
            smoothed_joints[:, j] = self._bspline_smooth(
                t_norm, joints_array[:, j])

        n_dims = xyz_array.shape[1]
        smoothed_xyz = np.zeros_like(xyz_array)
        for d in range(n_dims):
            smoothed_xyz[:, d] = self._bspline_smooth(
                t_norm, xyz_array[:, d])

        smoothed_rpy = np.zeros_like(rpy_array)
        for d in range(n_dims):
            smoothed_rpy[:, d] = self._bspline_smooth(
                t_norm, rpy_array[:, d])

        # 3. 混合原始与平滑 (smooth_factor 控制平滑程度)
        alpha = self.smooth_factor
        joints_array = (1 - alpha) * joints_array + alpha * smoothed_joints
        xyz_array = (1 - alpha) * xyz_array + alpha * smoothed_xyz
        rpy_array = (1 - alpha) * rpy_array + alpha * smoothed_rpy

        # 4. 限速限加速度
        joints_array = self._limit_acceleration(joints_array, t_array)

        # 5. 重建轨迹
        smoothed_traj = Trajectory(
            task_id=trajectory.task_id,
            robot_brand=trajectory.robot_brand,
            metadata=trajectory.metadata,
            original_count=original_count,
            smoothed_count=len(trajectory.waypoints),
        )

        for i, wp in enumerate(trajectory.waypoints):
            smoothed_traj.add(Waypoint(
                timestamp=wp.timestamp,
                joints=joints_array[i].tolist(),
                xyz=xyz_array[i].tolist(),
                rpy=rpy_array[i].tolist(),
                gripper=wp.gripper,
                image_id=wp.image_id,
            ))

        logger.info(f"B样条平滑完成: {original_count} → {smoothed_traj.smoothed_count} 点, "
                     f"平滑系数={alpha:.2f}")
        return smoothed_traj

    # ===== 私有方法 =====

    def _normalize_time(self, t_array: np.ndarray) -> np.ndarray:
        """时间轴归一化到 [0, 1]"""
        t_min, t_max = t_array.min(), t_array.max()
        if t_max - t_min < 1e-9:
            return np.zeros_like(t_array)
        return (t_array - t_min) / (t_max - t_min)

    def _bspline_smooth(self, t: np.ndarray, y: np.ndarray) -> np.ndarray:
        """
        三次 B 样条平滑单维度数据
        使用 scipy BSpline
        """
        from scipy.interpolate import make_interp_spline
        try:
            # 三次B样条拟合
            spl = make_interp_spline(t, y, k=min(self.degree, len(t) - 1))
            y_smooth = spl(t)
        except Exception as e:
            logger.debug(f"B样条拟合异常: {e}, 使用移动平均替代")
            y_smooth = self._moving_average(y, window=5)

        return y_smooth

    def _moving_average(self, data: np.ndarray, window: int = 5) -> np.ndarray:
        """移动平均降级方案"""
        if len(data) < window:
            return data
        kernel = np.ones(window) / window
        smoothed = np.convolve(data, kernel, mode='same')
        # 边界处理：端点保持原始值
        half = window // 2
        smoothed[:half] = data[:half]
        smoothed[-half:] = data[-half:]
        return smoothed

    def _limit_acceleration(self, joints: np.ndarray,
                            t_array: np.ndarray) -> np.ndarray:
        """限加速度，防止机械臂冲击"""
        if len(joints) < 3:
            return joints

        dt = np.diff(t_array).reshape(-1, 1)
        dt = np.clip(dt, 1e-3, None)  # 避免除零

        # 速度
        velocity = np.diff(joints, axis=0) / dt

        # 加速度
        accel = np.diff(velocity, axis=0) / dt[:-1]
        max_accel = np.max(np.abs(accel))

        if max_accel > self.max_acceleration:
            scale = self.max_acceleration / max_accel
            logger.debug(f"加速度超限: {max_accel:.2f} > {self.max_acceleration}, "
                         f"缩放系数={scale:.2f}")
            # 缩放控制点间增量来限加速度
            for i in range(1, len(joints)):
                delta = (joints[i] - joints[i - 1]) * scale
                joints[i] = joints[i - 1] + delta

        return joints

    # ===== 插值方法 =====

    def upsample(self, trajectory: Trajectory,
                 target_points: int = 50) -> Trajectory:
        """
        上采样/插值，将稀疏轨迹点补充到目标数量
        用于视觉帧对齐场景
        """
        if len(trajectory.waypoints) >= target_points:
            return trajectory

        t_min = trajectory.waypoints[0].timestamp
        t_max = trajectory.waypoints[-1].timestamp
        t_new = np.linspace(t_min, t_max, target_points)

        joints = np.array([wp.joints for wp in trajectory.waypoints])
        xyz = np.array([wp.xyz for wp in trajectory.waypoints])
        rpy = np.array([wp.rpy for wp in trajectory.waypoints])
        t_old = np.array([wp.timestamp for wp in trajectory.waypoints])

        # 线性插值
        from scipy.interpolate import interp1d
        kind = 'cubic' if len(t_old) >= 4 else 'linear'

        f_joints = interp1d(t_old, joints, axis=0, kind=kind, fill_value='extrapolate')
        f_xyz = interp1d(t_old, xyz, axis=0, kind=kind, fill_value='extrapolate')
        f_rpy = interp1d(t_old, rpy, axis=0, kind=kind, fill_value='extrapolate')

        new_traj = Trajectory(
            task_id=trajectory.task_id,
            robot_brand=trajectory.robot_brand,
            metadata=trajectory.metadata,
            original_count=len(trajectory.waypoints),
            smoothed_count=target_points,
        )

        for i, t in enumerate(t_new):
            new_traj.add(Waypoint(
                timestamp=float(t),
                joints=f_joints(t).tolist(),
                xyz=f_xyz(t).tolist(),
                rpy=f_rpy(t).tolist(),
                gripper=trajectory.waypoints[min(i, len(trajectory.waypoints) - 1)].gripper,
            ))

        return new_traj
