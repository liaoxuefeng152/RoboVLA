#!/usr/bin/env python3
"""
RoboVLA V2.0 - 主启动脚本

启动方式:
    python main.py                    # 启动 Qt 上位机
    python main.py --headless         # 无界面模式(仅后端服务)
    python main.py --calibrate        # 仅相机标定
"""

import sys
import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("RoboVLA")

def main():
    parser = argparse.ArgumentParser(description="RoboVLA V2.0 工业具身示教智能系统")
    parser.add_argument("--headless", action="store_true", help="无界面模式")
    parser.add_argument("--calibrate", action="store_true", help="仅相机标定")
    parser.add_argument("--robot-ip", default="192.168.1.100", help="机器人IP")
    parser.add_argument("--robot-brand", default="aubo", choices=["aubo", "dobot"])
    args = parser.parse_args()

    logger.info(f"RoboVLA V2.0 启动中...")

    # 1. 初始化组件
    from hardware_plugin.plugins.plugin_factory import RobotPluginFactory
    from visual_engine.vision_engine import VisionEngine
    from qt_ui.local_database import RoboVLADatabase
    from qt_ui.license_manager import LicenseManager

    db = RoboVLADatabase()
    db.init_default_users()

    license_mgr = LicenseManager(db)
    status = license_mgr.check_status()
    logger.info(f"授权状态: {status.activated} ({status.auth_type})")

    factory = RobotPluginFactory()
    vision = VisionEngine()
    vision.init_camera(camera_id=0)

    if args.calibrate:
        logger.info("进入标定模式...")
        vision.calibrator.collect_samples(count=15)
        vision.calibrator.calibrate()
        vision.calibrator.save("test_data/camera_params.json")
        logger.info("标定完成")
        return

    # 2. 连接机器人
    robot = factory.create(args.robot_brand, ip=args.robot_ip)
    if robot:
        robot.connect()
        logger.info(f"机器人已连接: {args.robot_brand} @ {args.robot_ip}")

    # 3. 启动上位机或后台服务
    if args.headless:
        logger.info("无界面模式启动")
        # 启动后台服务循环
        from decision_engine.vla_inference.vla_inference import VLAInferenceEngine
        from decision_engine.llm_agent.llm_agent import LanguageAgent

        vla = VLAInferenceEngine()
        agent = LanguageAgent(robot, vision)
        agent.init()

        logger.info("后台服务就绪，等待指令...")
        # 保持运行
        import time
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("收到退出信号")
    else:
        # 初始化决策引擎
        from decision_engine.imitation_learning.imitation_learning import (
            DragRecorder, TaskTemplateManager, ImitationLearningTrainer
        )
        from decision_engine.vla_inference.vla_inference import VLAInferenceEngine
        from decision_engine.llm_agent.llm_agent import LanguageAgent

        recorder = DragRecorder(robot) if robot else None
        trainer = ImitationLearningTrainer()
        template_mgr = TaskTemplateManager()
        vla = VLAInferenceEngine()
        agent = LanguageAgent(robot, vision)
        agent.init()

        # 启动 Qt 上位机
        from qt_ui.main_window import launch_ui
        logger.info("启动 Qt 上位机...")
        launch_ui()

    # 4. 清理
    vision.close()
    if robot:
        robot.disconnect()
    logger.info("RoboVLA 已安全退出")


if __name__ == "__main__":
    main()
