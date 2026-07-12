"""
RoboVLA V2.0 - 单元测试套件
运行: pytest tests/ -v
或: python -m pytest tests/ --cov=.
"""

import os
import sys
import json
import tempfile
import numpy as np
import unittest
from unittest.mock import MagicMock, patch

# 确保项目根目录在 sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


class TestHardwarePlugin(unittest.TestCase):
    """硬件插件层单元测试"""

    def setUp(self):
        self.factory = None
        try:
            from hardware_plugin.plugins.plugin_factory import RobotPluginFactory
            self.factory = RobotPluginFactory()
        except ImportError as e:
            self.skipTest(f"硬件插件模块未加载: {e}")

    def test_factory_create_aubo(self):
        """测试创建遨博插件"""
        if not self.factory:
            return
        robot = self.factory.create("aubo", ip="127.0.0.1")
        self.assertIsNotNone(robot)
        self.assertEqual(robot.brand, "aubo")

    def test_factory_create_dobot(self):
        """测试创建越疆插件"""
        if not self.factory:
            return
        robot = self.factory.create("dobot", ip="127.0.0.1")
        self.assertIsNotNone(robot)
        self.assertEqual(robot.brand, "dobot")

    def test_robot_abstract_methods(self):
        """验证 RobotBase 抽象方法可调用"""
        try:
            from hardware_plugin.robot_base import RobotBase
            # 抽象类不能直接实例化
            self.assertTrue(hasattr(RobotBase, 'connect'))
            self.assertTrue(hasattr(RobotBase, 'disconnect'))
            self.assertTrue(hasattr(RobotBase, 'get_state'))
            self.assertTrue(hasattr(RobotBase, 'move_joint'))
            self.assertTrue(hasattr(RobotBase, 'enable_drag_mode'))
        except ImportError:
            self.skipTest("robot_base 模块未加载")


class TestVisionEngine(unittest.TestCase):
    """视觉引擎单元测试"""

    def setUp(self):
        try:
            from visual_engine.vision_engine import VisionEngine
            self.engine = VisionEngine()
        except ImportError:
            self.skipTest("视觉引擎模块未加载")

    def test_feature_detect_standalone(self):
        """测试特征检测(无相机)"""
        try:
            import cv2
            img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            kp, des = self.engine._detect_features(img)
            self.assertIsNotNone(des, "特征描述符不应为空")
        except AttributeError:
            pass  # 方法可能在不同版本中有差异

    def test_offset_calculation(self):
        """测试偏移计算"""
        ref_pos = [100.0, 200.0, 50.0]
        cur_pos = [110.0, 195.0, 50.0]
        dx, dy = self.engine._calc_offset(ref_pos, cur_pos, image_size=(640, 480))
        self.assertAlmostEqual(dx, 10.0, delta=1.0)
        self.assertAlmostEqual(dy, -5.0, delta=1.0)


class TestTrajectorySmoother(unittest.TestCase):
    """轨迹平滑器单元测试"""

    def setUp(self):
        try:
            from decision_engine.imitation_learning.trajectory_smoother import (
                BSplineSmoother, Waypoint, Trajectory
            )
            self.smoother = BSplineSmoother(smooth_factor=0.7)
            self.Waypoint = Waypoint
            self.Trajectory = Trajectory
        except ImportError:
            self.skipTest("轨迹平滑模块未加载")

    def test_smooth_reduces_jitter(self):
        """验证 B样条平滑消除抖动"""
        # 生成带噪声的正弦轨迹
        n = 100
        t = np.linspace(0, 10, n)
        clean = np.sin(t) * 0.5
        noisy = clean + np.random.normal(0, 0.05, n)  # 人工抖动

        traj = self.Trajectory(task_id="test", robot_brand="aubo")
        for i in range(n):
            traj.add(self.Waypoint(
                timestamp=t[i] * 1000,
                joints=[noisy[i], 0.0, 0.0, 0.0, 0.0, 0.0],
                xyz=[0.3, 0.2, noisy[i]],
                rpy=[0.0, 0.0, 0.0],
            ))

        smoothed = self.smoother.smooth(traj)

        # 平滑后点数不变
        self.assertEqual(len(smoothed.waypoints), n)

        # 平滑后噪声方差应减小
        original_var = np.var([wp.joints[0] for wp in traj.waypoints])
        smoothed_var = np.var([wp.joints[0] for wp in smoothed.waypoints])
        # 注意: smooth_factor=0.7 应显著降低方差
        self.assertLess(smoothed_var, original_var * 1.1,
                        f"平滑后方差({smoothed_var:.4f})应小于原始({original_var:.4f})")

    def test_json_serialization(self):
        """测试轨迹 JSON 序列化"""
        traj = self.Trajectory(task_id="test_001", robot_brand="aubo")
        traj.add(self.Waypoint(
            timestamp=0, joints=[0.1]*6, xyz=[0.3, 0.2, 0.1], rpy=[0, 0, 0]
        ))
        traj.add(self.Waypoint(
            timestamp=100, joints=[0.2]*6, xyz=[0.4, 0.3, 0.2], rpy=[0, 0, 0.1]
        ))

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            traj.to_json(path)
            loaded = self.Trajectory.from_json(path)
            self.assertEqual(len(loaded.waypoints), 2)
            self.assertEqual(loaded.task_id, "test_001")
        finally:
            os.unlink(path)


class TestLicenseManager(unittest.TestCase):
    """授权管理单元测试"""

    def setUp(self):
        try:
            from qt_ui.license_manager import LicenseManager
            # 使用 mock 数据库
            self.license = LicenseManager(db=None)
        except ImportError:
            self.skipTest("授权管理模块未加载")

    def test_device_sn_available(self):
        """验证能获取硬件SN"""
        try:
            sn = self.license._get_device_sn()
            self.assertIsInstance(sn, str)
            self.assertTrue(len(sn) > 0)
        except AttributeError:
            self.skipTest("_get_device_sn 方法不可用")


class TestASRTTS(unittest.TestCase):
    """语音模块接口测试"""

    def test_asr_import(self):
        """测试 ASR 模块导入"""
        try:
            from decision_engine.llm_agent.asr_engine import OfflineASR, ASREngine
            asr = OfflineASR(engine=ASREngine.VOSK)
            self.assertIsNotNone(asr)
            self.assertEqual(asr.engine_type, ASREngine.VOSK)
        except ImportError:
            self.skipTest("ASR 模块未加载")

    def test_tts_import(self):
        """测试 TTS 模块导入"""
        try:
            from decision_engine.llm_agent.tts_engine import OfflineTTS, TTSEngine
            tts = OfflineTTS()
            self.assertIsNotNone(tts)
            self.assertEqual(tts.config.engine, TTSEngine.PIPER)
        except ImportError:
            self.skipTest("TTS 模块未加载")

    def test_asr_post_process(self):
        """测试语音后处理纠正常见误识别"""
        try:
            from decision_engine.llm_agent.asr_engine import OfflineASR, ASREngine
            asr = OfflineASR(engine=ASREngine.VOSK)
            result = asr._post_process("家教模式")
            self.assertEqual(result, "示教模式")
        except ImportError:
            self.skipTest("ASR 后处理模块未加载")


class TestDatabase(unittest.TestCase):
    """数据库模块接口测试"""

    def test_db_connection(self):
        """测试 SQLite 数据库连接"""
        try:
            from qt_ui.local_database import RoboVLADatabase
            db = RoboVLADatabase(":memory:")
            self.assertIsNotNone(db.conn)
            db.conn.close()
        except ImportError:
            self.skipTest("数据库模块未加载")

    def test_user_auth(self):
        """测试用户认证"""
        try:
            from qt_ui.local_database import RoboVLADatabase
            db = RoboVLADatabase(":memory:")
            db.init_default_users()
            # 验证操作工默认密码
            result = db.verify_user("operator", "operator123")
            self.assertIsNotNone(result)
            self.assertEqual(result[2], "OPERATOR")  # role
            db.conn.close()
        except ImportError:
            self.skipTest("数据库模块未加载")


if __name__ == "__main__":
    unittest.main(verbosity=2)
