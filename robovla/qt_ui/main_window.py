#!/usr/bin/env python3
"""
RoboVLA V2.0 - Qt 上位机主窗口

6 页标签:
1. 设备连接 & 授权激活
2. 相机标定 & 工件样本管理
3. 拖拽示教 & AI 训练
4. 实时生产页面
5. 语音指令面板
6. 系统设置 & 数据管理
"""

import sys
import time
import threading
import logging
from typing import Optional, Dict
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStatusBar, QMessageBox, QFrame, QSplitter,
    QGroupBox, QGridLayout, QLineEdit, QComboBox,
    QCheckBox, QSpinBox, QDoubleSpinBox, QTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QProgressBar, QSlider, QListWidget, QFileDialog,
    QDialog, QFormLayout, QDialogButtonBox, QRadioButton,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QFont, QIcon, QPixmap, QImage

logger = logging.getLogger(__name__)


# ============================================================
# 信号通信
# ============================================================

class RoboVLASignals:
    """模块间信号通信"""
    robot_state_changed = pyqtSignal(str)
    vision_offset_updated = pyqtSignal(float, float, float)
    production_updated = pyqtSignal(int, int, int)
    command_received = pyqtSignal(str)
    alert_triggered = pyqtSignal(str, str)


# ============================================================
# 页面0: 设备连接 & 授权激活
# ============================================================

class DevicePage(QWidget):
    signals = RoboVLASignals()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._robot = None
        self._factory = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # === 设备连接组 ===
        conn_group = QGroupBox("设备连接")
        conn_layout = QGridLayout()

        conn_layout.addWidget(QLabel("机器人品牌:"), 0, 0)
        self.brand_combo = QComboBox()
        self.brand_combo.addItems(["Aubo (遨博)", "Dobot (越疆)"])
        conn_layout.addWidget(self.brand_combo, 0, 1)

        conn_layout.addWidget(QLabel("IP 地址:"), 1, 0)
        self.ip_input = QLineEdit("192.168.1.100")
        conn_layout.addWidget(self.ip_input, 1, 1)

        conn_layout.addWidget(QLabel("端口:"), 2, 0)
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(8899)
        conn_layout.addWidget(self.port_input, 2, 1)

        btn_layout = QHBoxLayout()
        self.connect_btn = QPushButton("🔌 连接设备")
        self.connect_btn.setStyleSheet("QPushButton { font-size: 14px; padding: 8px 20px; }")
        self.connect_btn.clicked.connect(self._on_connect)
        btn_layout.addWidget(self.connect_btn)

        self.disconnect_btn = QPushButton("断开连接")
        self.disconnect_btn.setEnabled(False)
        btn_layout.addWidget(self.disconnect_btn)
        conn_layout.addLayout(btn_layout, 3, 0, 1, 2)

        self.status_label = QLabel("⚪ 未连接")
        self.status_label.setStyleSheet("font-size: 14px; color: #888;")
        conn_layout.addWidget(self.status_label, 4, 0, 1, 2)

        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)

        # === 授权激活组 ===
        auth_group = QGroupBox("授权管理")
        auth_layout = QGridLayout()

        auth_layout.addWidget(QLabel("硬件序列号:"), 0, 0)
        self.sn_label = QLabel("----")
        self.sn_label.setStyleSheet("font-family: monospace; font-size: 13px;")
        auth_layout.addWidget(self.sn_label, 0, 1)

        auth_layout.addWidget(QLabel("授权码:"), 1, 0)
        self.license_input = QLineEdit()
        self.license_input.setPlaceholderText("输入8位授权码")
        self.license_input.setMaxLength(8)
        auth_layout.addWidget(self.license_input, 1, 1)

        self.activate_btn = QPushButton("🔑 激活")
        self.activate_btn.clicked.connect(self._on_activate)
        auth_layout.addWidget(self.activate_btn, 2, 0, 1, 2)

        self.license_status = QLabel("未激活")
        auth_layout.addWidget(self.license_status, 3, 0, 1, 2)

        auth_group.setLayout(auth_layout)
        layout.addWidget(auth_group)

        # === 硬件信息 ===
        hw_group = QGroupBox("硬件信息")
        hw_layout = QFormLayout()
        self.model_label = QLabel("-")
        self.fw_label = QLabel("-")
        self.joint_status = QTextEdit()
        self.joint_status.setReadOnly(True)
        self.joint_status.setMaximumHeight(120)
        hw_layout.addRow("型号:", self.model_label)
        hw_layout.addRow("固件:", self.fw_label)
        hw_layout.addRow("关节状态:", self.joint_status)
        hw_group.setLayout(hw_layout)
        layout.addWidget(hw_group)

        layout.addStretch()

    def set_backend(self, robot, factory, license_mgr):
        self._robot = robot
        self._factory = factory
        self._license_mgr = license_mgr

    def _on_connect(self):
        brand_map = {"Aubo (遨博)": "aubo", "Dobot (越疆)": "dobot"}
        brand = brand_map[self.brand_combo.currentText()]
        ip = self.ip_input.text()
        port = self.port_input.value()

        self.status_label.setText("🟡 连接中...")
        self.status_label.setStyleSheet("color: orange;")
        QApplication.processEvents()

        if self._factory and self._factory.create(brand, ip=ip, port=port):
            robot = self._factory.get_active_plugins().get(brand)
            if robot and robot.connect():
                self._robot = robot
                self.status_label.setText(f"🟢 已连接 {brand}")
                self.status_label.setStyleSheet("color: green;")
                self.connect_btn.setEnabled(False)
                self.disconnect_btn.setEnabled(True)

                info = robot.get_model_info()
                self.model_label.setText(info.get("model", "-"))
                self.fw_label.setText(info.get("firmware", "-"))
                self.sn_label.setText(robot.get_serial_number())

                # 启动关节状态刷新
                self._joint_timer = QTimer()
                self._joint_timer.timeout.connect(self._refresh_joints)
                self._joint_timer.start(200)
            else:
                self.status_label.setText("🔴 连接失败")
                self.status_label.setStyleSheet("color: red;")
        else:
            self.status_label.setText("🔴 设备不可达")
            self.status_label.setStyleSheet("color: red;")

    def _on_activate(self):
        code = self.license_input.text().strip()
        if len(code) < 8:
            QMessageBox.warning(self, "错误", "请输入有效的8位授权码")
            return

        if self._license_mgr:
            success, msg = self._license_mgr.activate(code, "trial", 30)
            if success:
                self.license_status.setText(f"✅ 激活成功 - {msg}")
                self.license_status.setStyleSheet("color: green;")
            else:
                self.license_status.setText(f"❌ {msg}")
                self.license_status.setStyleSheet("color: red;")

    def _refresh_joints(self):
        if self._robot and self._robot.is_connected():
            try:
                joint = self._robot.get_joint_state()
                text = "\n".join([
                    f"J{i+1}: {joint.positions[i]:+8.3f} rad  |  "
                    f"⍵{joint.velocities[i]:+7.3f}  |  "
                    f"τ{joint.efforts[i]:+7.2f} Nm"
                    for i in range(6)
                ])
                self.joint_status.setText(text)
            except Exception:
                pass


# ============================================================
# 页面1: 相机标定 & 工件样本管理
# ============================================================

class CalibrationPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._vision = None
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)

        # === 左侧: 相机画面 ===
        left = QVBoxLayout()
        self.camera_label = QLabel("相机画面")
        self.camera_label.setMinimumSize(480, 360)
        self.camera_label.setStyleSheet("background: #222; border: 1px solid #555;")
        self.camera_label.setAlignment(Qt.AlignCenter)
        left.addWidget(self.camera_label)

        cam_ctrl = QHBoxLayout()
        self.start_cam_btn = QPushButton("📷 打开相机")
        self.stop_cam_btn = QPushButton("关闭")
        cam_ctrl.addWidget(self.start_cam_btn)
        cam_ctrl.addWidget(self.stop_cam_btn)
        left.addLayout(cam_ctrl)
        layout.addLayout(left, 2)

        # === 右侧: 控制面板 ===
        right = QVBoxLayout()

        # 标定组
        calib_group = QGroupBox("相机标定")
        calib_layout = QVBoxLayout()
        self.calib_collect_btn = QPushButton("📐 采集标定样本 (20帧)")
        self.calib_run_btn = QPushButton("⚙️ 执行标定")
        self.calib_save_btn = QPushButton("💾 保存标定参数")
        self.calib_load_btn = QPushButton("📂 加载标定参数")
        for btn in [self.calib_collect_btn, self.calib_run_btn,
                     self.calib_save_btn, self.calib_load_btn]:
            calib_layout.addWidget(btn)
        calib_group.setLayout(calib_layout)
        right.addWidget(calib_group)

        # 工件管理组
        sample_group = QGroupBox("工件样本管理")
        sample_layout = QVBoxLayout()
        self.sample_name = QLineEdit()
        self.sample_name.setPlaceholderText("工件名称 (如: 螺丝_M3)")
        sample_layout.addWidget(self.sample_name)
        self.add_sample_btn = QPushButton("➕ 录入当前工件")
        self.batch_sample_btn = QPushButton("📁 批量导入")
        self.delete_sample_btn = QPushButton("🗑️ 删除选中样本")
        sample_layout.addWidget(self.add_sample_btn)
        sample_layout.addWidget(self.batch_sample_btn)
        sample_layout.addWidget(self.delete_sample_btn)

        self.sample_list = QListWidget()
        sample_layout.addWidget(self.sample_list)
        sample_group.setLayout(sample_layout)
        right.addWidget(sample_group)

        # 检测组
        detect_group = QGroupBox("实时检测")
        detect_layout = QVBoxLayout()
        self.detect_btn = QPushButton("🔍 检测工件偏移")
        self.offset_display = QLabel("偏移: ---")
        self.offset_display.setStyleSheet("font-size: 14px;")
        self.detect_btn.clicked.connect(self._on_detect)
        detect_layout.addWidget(self.detect_btn)
        detect_layout.addWidget(self.offset_display)
        detect_group.setLayout(detect_layout)
        right.addWidget(detect_group)

        layout.addLayout(right, 1)

    def set_vision_engine(self, engine):
        self._vision = engine

    def _on_detect(self):
        if self._vision and self.sample_list.currentItem():
            sample_id = int(self.sample_list.currentItem().text().split("]")[0][1:])
            result = self._vision.detect_workpiece(sample_id)
            if result.detected:
                self.offset_display.setText(
                    f"偏移: X={result.delta_x_mm:.1f}mm  "
                    f"Y={result.delta_y_mm:.1f}mm  "
                    f"θ={result.delta_angle_deg:.1f}°  "
                    f"匹配: {result.match_score:.2f}"
                )
            else:
                self.offset_display.setText(f"⚠️ {result.anomaly or '未检测到工件'}")


# ============================================================
# 页面2: 拖拽示教 & AI 训练
# ============================================================

class TeachingPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._recorder = None
        self._trainer = None
        self._template_mgr = None
        self._recording = False
        self._timer = QTimer()
        self._timer.timeout.connect(self._recording_tick)
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)

        # 左侧: 任务模板列表
        left = QVBoxLayout()
        task_group = QGroupBox("任务模板")
        task_layout = QVBoxLayout()
        self.task_list = QListWidget()
        task_layout.addWidget(self.task_list)
        task_btn_layout = QHBoxLayout()
        self.new_task_btn = QPushButton("新建")
        self.dup_task_btn = QPushButton("复制")
        self.del_task_btn = QPushButton("删除")
        self.export_btn = QPushButton("导出")
        self.import_btn = QPushButton("导入")
        for btn in [self.new_task_btn, self.dup_task_btn, self.del_task_btn,
                     self.export_btn, self.import_btn]:
            task_btn_layout.addWidget(btn)
        task_layout.addLayout(task_btn_layout)
        task_group.setLayout(task_layout)
        left.addWidget(task_group)

        # 段列表
        seg_group = QGroupBox("工序段")
        seg_layout = QVBoxLayout()
        self.segment_list = QListWidget()
        seg_layout.addWidget(self.segment_list)
        seg_btn = QHBoxLayout()
        self.move_up_btn = QPushButton("↑")
        self.move_down_btn = QPushButton("↓")
        self.delete_seg_btn = QPushButton("删除段")
        for btn in [self.move_up_btn, self.move_down_btn, self.delete_seg_btn]:
            seg_btn.addWidget(btn)
        seg_layout.addLayout(seg_btn)
        seg_group.setLayout(seg_layout)
        left.addWidget(seg_group)
        layout.addLayout(left, 1)

        # 右侧: 示教控制
        right = QVBoxLayout()

        # 录制控制
        rec_group = QGroupBox("示教录制")
        rec_layout = QVBoxLayout()

        self.seg_name_combo = QComboBox()
        self.seg_name_combo.addItems(["取料", "装配", "检测", "下料", "自定义"])
        rec_layout.addWidget(QLabel("段名称:"))
        rec_layout.addWidget(self.seg_name_combo)

        self.rec_start_btn = QPushButton("🔴 开始录制")
        self.rec_start_btn.setStyleSheet(
            "QPushButton { background: #c0392b; color: white; font-size: 16px; padding: 12px; }"
        )
        self.rec_start_btn.clicked.connect(self._on_start_recording)
        rec_layout.addWidget(self.rec_start_btn)

        self.rec_stop_btn = QPushButton("⏹️ 停止录制")
        self.rec_stop_btn.setEnabled(False)
        self.rec_stop_btn.clicked.connect(self._on_stop_recording)
        rec_layout.addWidget(self.rec_stop_btn)

        self.rec_status = QLabel("就绪")
        self.rec_status.setStyleSheet("font-size: 14px;")
        rec_layout.addWidget(self.rec_status)

        self.rec_progress = QProgressBar()
        rec_layout.addWidget(self.rec_progress)

        rec_group.setLayout(rec_layout)
        right.addWidget(rec_group)

        # AI 训练
        train_group = QGroupBox("AI 训练")
        train_layout = QVBoxLayout()
        self.train_btn = QPushButton("🧠 开始训练 (预计5分钟)")
        self.train_btn.setStyleSheet(
            "QPushButton { background: #2980b9; color: white; font-size: 14px; padding: 10px; }"
        )
        self.train_btn.clicked.connect(self._on_train)
        train_layout.addWidget(self.train_btn)

        self.train_status = QLabel("等待训练...")
        self.train_progress = QProgressBar()
        train_layout.addWidget(self.train_status)
        train_layout.addWidget(self.train_progress)
        train_group.setLayout(train_layout)
        right.addWidget(train_group)

        # 任务预览
        preview_group = QGroupBox("任务预览")
        preview_layout = QVBoxLayout()
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(150)
        preview_layout.addWidget(self.preview_text)
        preview_group.setLayout(preview_layout)
        right.addWidget(preview_group)

        layout.addLayout(right, 1)

    def set_backend(self, recorder, trainer, template_mgr):
        self._recorder = recorder
        self._trainer = trainer
        self._template_mgr = template_mgr

    def _on_start_recording(self):
        if self._recorder:
            name = self.seg_name_combo.currentText()
            if self._recorder.start_recording(name):
                self._recording = True
                self.rec_start_btn.setEnabled(False)
                self.rec_stop_btn.setEnabled(True)
                self.rec_status.setText(f"🔴 录制中: {name}")
                self._timer.start(20)  # 50Hz

    def _on_stop_recording(self):
        self._timer.stop()
        self._recording = False
        if self._recorder:
            seg = self._recorder.stop_recording()
            if seg:
                self.rec_status.setText(f"✅ 录制完成: {seg.name} ({len(seg.trajectory)}点)")
                self.segment_list.addItem(f"[{seg.id}] {seg.name} - {len(seg.trajectory)}点")
                self.rec_start_btn.setEnabled(True)
                self.rec_stop_btn.setEnabled(False)

    def _recording_tick(self):
        if self._recorder and self._recording:
            self._recorder.tick()

    def _on_train(self):
        if self._trainer and self._recorder:
            segments = self._recorder.get_segments()
            if not segments:
                QMessageBox.warning(self, "警告", "请先录制至少一段示教")
                return
            self.train_status.setText("🟡 训练中...")
            self.train_progress.setRange(0, 0)
            QApplication.processEvents()

            model_path = self._trainer.train(
                self._recorder._segments, "trained_task"
            )
            self.train_status.setText(f"✅ 训练完成")
            self.train_progress.setRange(0, 100)
            self.train_progress.setValue(100)
            QMessageBox.information(self, "完成", f"模型已保存:\n{model_path}")


# ============================================================
# 页面3: 实时生产监控
# ============================================================

class ProductionPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._robot = None
        self._vision = None
        self._running = False
        self._good_count = 0
        self._bad_count = 0
        self._cycle = 0
        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._refresh_display)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 顶部: 运行模式
        top_layout = QHBoxLayout()
        self.mode_single = QPushButton("单次执行")
        self.mode_count = QPushButton("定量循环")
        self.mode_infinite = QPushButton("无限循环")
        self.mode_step = QPushButton("单步调试")
        for btn in [self.mode_single, self.mode_count, self.mode_infinite, self.mode_step]:
            btn.setCheckable(True)
            top_layout.addWidget(btn)

        self.cycle_spin = QSpinBox()
        self.cycle_spin.setRange(1, 99999)
        self.cycle_spin.setValue(100)
        top_layout.addWidget(QLabel("数量:"))
        top_layout.addWidget(self.cycle_spin)
        layout.addLayout(top_layout)

        # 中间: 分屏监控
        split = QHBoxLayout()

        # 相机画面
        self.camera_view = QLabel("📷 相机实时画面")
        self.camera_view.setMinimumSize(400, 300)
        self.camera_view.setStyleSheet("background: #1a1a1a; border: 2px solid #333;")
        self.camera_view.setAlignment(Qt.AlignCenter)
        split.addWidget(self.camera_view, 3)

        # 3D 仿真(简化版)
        self.sim_view = QLabel("🤖 机器人3D仿真")
        self.sim_view.setMinimumSize(300, 300)
        self.sim_view.setStyleSheet("background: #1a2a1a; border: 2px solid #333;")
        self.sim_view.setAlignment(Qt.AlignCenter)
        split.addWidget(self.sim_view, 2)

        layout.addLayout(split)

        # 底部: 产量 + 运行信息
        info_layout = QHBoxLayout()

        stats_group = QGroupBox("生产统计")
        stats_layout = QGridLayout()
        self.good_label = QLabel("0")
        self.good_label.setStyleSheet("font-size: 28px; color: #2ecc71; font-weight: bold;")
        self.bad_label = QLabel("0")
        self.bad_label.setStyleSheet("font-size: 28px; color: #e74c3c; font-weight: bold;")
        self.cycle_label = QLabel("0")
        self.cycle_label.setStyleSheet("font-size: 28px; color: #3498db; font-weight: bold;")

        stats_layout.addWidget(QLabel("👍 良品:"), 0, 0)
        stats_layout.addWidget(self.good_label, 0, 1)
        stats_layout.addWidget(QLabel("👎 不良:"), 1, 0)
        stats_layout.addWidget(self.bad_label, 1, 1)
        stats_layout.addWidget(QLabel("🔄 循环:"), 2, 0)
        stats_layout.addWidget(self.cycle_label, 2, 1)
        stats_group.setLayout(stats_layout)
        info_layout.addWidget(stats_group)

        # 运行日志
        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        info_layout.addWidget(log_group, 2)

        layout.addLayout(info_layout)

        # 控制按钮
        ctrl_layout = QHBoxLayout()
        self.start_btn = QPushButton("▶️ 开始生产")
        self.start_btn.setStyleSheet(
            "QPushButton { background: #27ae60; color: white; font-size: 16px; padding: 10px 30px; }"
        )
        self.pause_btn = QPushButton("⏸️ 暂停")
        self.stop_btn = QPushButton("⏹️ 停止")
        self.emergency_btn = QPushButton("🛑 急停")
        self.emergency_btn.setStyleSheet(
            "QPushButton { background: #c0392b; color: white; font-size: 16px; padding: 10px 30px; }"
        )
        ctrl_layout.addWidget(self.start_btn)
        ctrl_layout.addWidget(self.pause_btn)
        ctrl_layout.addWidget(self.stop_btn)
        ctrl_layout.addWidget(self.emergency_btn)
        layout.addLayout(ctrl_layout)

    def set_backend(self, robot, vision):
        self._robot = robot
        self._vision = vision

    def _refresh_display(self):
        # 刷新相机画面
        if self._vision:
            frame = self._vision.capture_frame()
            if frame is not None:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame.shape
                bytes_per_line = ch * w
                qimg = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
                self.camera_view.setPixmap(QPixmap.fromImage(qimg).scaled(
                    self.camera_view.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                ))

        # 刷新3D仿真(带AI识别框)
        self.sim_view.setText(f"循环 #{self._cycle}\n"
                              f"关节: {'✓' if self._robot and self._robot.is_connected() else '✗'}")

    def _log(self, msg: str):
        t = time.strftime("%H:%M:%S")
        self.log_text.append(f"[{t}] {msg}")


# ============================================================
# 页面4: 语音指令面板
# ============================================================

class VoiceCommandPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._agent = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 文字输入
        text_group = QGroupBox("文字指令")
        text_layout = QHBoxLayout()
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("输入中文指令: 做500个 / 慢一点 / 暂停 / 还剩多少...")
        self.command_input.returnPressed.connect(self._on_text_command)
        text_layout.addWidget(self.command_input)

        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self._on_text_command)
        text_layout.addWidget(self.send_btn)
        text_group.setLayout(text_layout)
        layout.addWidget(text_group)

        # 语音监听
        voice_group = QGroupBox("语音指令")
        voice_layout = QVBoxLayout()
        self.voice_btn = QPushButton("🎤 开始语音监听 (5秒)")
        self.voice_btn.clicked.connect(self._on_voice)
        voice_layout.addWidget(self.voice_btn)

        self.voice_status = QLabel("等待语音输入...")
        voice_layout.addWidget(self.voice_status)
        voice_group.setLayout(voice_layout)
        layout.addWidget(voice_group)

        # 快捷指令
        quick_group = QGroupBox("快捷指令")
        quick_layout = QGridLayout()
        quick_commands = [
            ("⏸️ 暂停", "暂停"), ("▶️ 继续", "继续"),
            ("🐌 慢一点", "慢一点"), ("🚀 全速", "全速"),
            ("📊 还剩多少", "还剩多少"), ("📦 做了多少个", "做了多少个"),
            ("🔄 重试3次", "重试3次"), ("⏭️ 跳过当前", "跳过当前"),
            ("🆘 急停", "急停"), ("🔧 做完当前停", "做完当前停"),
        ]
        for i, (label, cmd) in enumerate(quick_commands):
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked, c=cmd: self._on_text_command_text(c))
            quick_layout.addWidget(btn, i // 2, i % 2)
        quick_group.setLayout(quick_layout)
        layout.addWidget(quick_group)

        # 交互日志
        log_group = QGroupBox("交互日志")
        log_layout = QVBoxLayout()
        self.history_log = QTextEdit()
        self.history_log.setReadOnly(True)
        log_layout.addWidget(self.history_log)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

    def set_agent(self, agent):
        self._agent = agent

    def _on_text_command(self):
        text = self.command_input.text().strip()
        if text:
            self._on_text_command_text(text)

    def _on_text_command_text(self, text: str):
        self.command_input.clear()
        self._log(f"📝 指令: {text}")

        if self._agent:
            result = self._agent.process_text(text)
            if result.get("success"):
                msg = result.get("message", "")
                self._log(f"  ✅ {msg}")
            else:
                self._log(f"  ❌ {result.get('message', '执行失败')}")

    def _on_voice(self):
        self.voice_status.setText("🔴 监听中... (请说话)")
        QApplication.processEvents()

        if self._agent:
            result = self._agent.listen_and_execute()
            if result:
                self.voice_status.setText(f"✅ 识别: {result.get('parsed', {}).get('original_text', '')}")
            else:
                self.voice_status.setText("未检测到语音")

    def _log(self, msg: str):
        t = time.strftime("%H:%M:%S")
        self.history_log.append(f"[{t}] {msg}")


# ============================================================
# 页面5: 系统设置 & 数据管理
# ============================================================

class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._db = None
        self._robot = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 数据管理
        data_group = QGroupBox("数据管理")
        data_layout = QVBoxLayout()

        self.backup_btn = QPushButton("💾 一键备份所有数据")
        self.restore_btn = QPushButton("📂 从备份恢复")
        self.clear_btn = QPushButton("🗑️ 一键清零所有数据")
        self.clear_btn.setStyleSheet("QPushButton { color: #e74c3c; font-weight: bold; }")
        self.clear_btn.clicked.connect(self._on_clear)
        self.export_report_btn = QPushButton("📊 导出生产报表(Excel)")

        for btn in [self.backup_btn, self.restore_btn,
                     self.clear_btn, self.export_report_btn]:
            data_layout.addWidget(btn)

        self.data_status = QLabel("数据库状态: 正常")
        data_layout.addWidget(self.data_status)
        data_group.setLayout(data_layout)
        layout.addWidget(data_group)

        # 系统参数
        param_group = QGroupBox("系统参数")
        param_layout = QFormLayout()

        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(10, 100)
        self.speed_slider.setValue(80)
        self.speed_slider.setTickInterval(10)
        param_layout.addRow("速度上限:", self.speed_slider)

        self.force_spin = QDoubleSpinBox()
        self.force_spin.setRange(10, 200)
        self.force_spin.setValue(100)
        self.force_spin.setSuffix(" N")
        param_layout.addRow("力矩上限:", self.force_spin)

        self.accel_spin = QDoubleSpinBox()
        self.accel_spin.setRange(0.1, 1.0)
        self.accel_spin.setValue(0.6)
        self.accel_spin.setSingleStep(0.1)
        param_layout.addRow("加速度比例:", self.accel_spin)

        self.apply_params_btn = QPushButton("应用参数")
        param_layout.addRow("", self.apply_params_btn)
        param_group.setLayout(param_layout)
        layout.addWidget(param_group)

        # 用户管理
        user_group = QGroupBox("用户管理")
        user_layout = QVBoxLayout()
        self.user_table = QTableWidget()
        self.user_table.setColumnCount(4)
        self.user_table.setHorizontalHeaderLabels(["用户名", "角色", "状态", "最后登录"])
        self.user_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.user_table.setMaximumHeight(150)
        user_layout.addWidget(self.user_table)
        user_group.setLayout(user_layout)
        layout.addWidget(user_group)

        # 关于
        about_group = QGroupBox("关于 RoboVLA")
        about_layout = QVBoxLayout()
        about_layout.addWidget(QLabel("RoboVLA 工业轻量化具身示教智能系统 V2.0"))
        about_layout.addWidget(QLabel("© 2025 RoboVLA - 中小企业具身智能解决方案"))
        about_group.setLayout(about_layout)
        layout.addWidget(about_group)

        layout.addStretch()

    def set_backend(self, db, robot):
        self._db = db
        self._robot = robot

    def _on_clear(self):
        reply = QMessageBox.warning(
            self, "确认清零",
            "⚠️ 此操作将不可逆删除所有训练数据、生产日志和工件样本!\n\n"
            "确定要继续吗?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes and self._db:
            self._db.clear_all_data()
            self.data_status.setText("数据库状态: 已清零 ✅")


# ============================================================
# 主窗口
# ============================================================

class MainWindow(QMainWindow):
    """RoboVLA V2.0 主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("RoboVLA V2.0 - 工业轻量化具身示教智能系统")
        self.resize(1400, 900)

        # 后端引用(由外部设置)
        self._robot = None
        self._factory = None
        self._vision = None
        self._recorder = None
        self._trainer = None
        self._template_mgr = None
        self._agent = None
        self._db = None
        self._license_mgr = None

        self.init_ui()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # 标题栏
        title = QLabel("RoboVLA 工业轻量化具身示教智能系统 V2.0")
        title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #2c3e50; padding: 8px;"
        )
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        # 分页标签
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #ccc; }
            QTabBar::tab { padding: 8px 16px; font-size: 13px; }
            QTabBar::tab:selected { background: #3498db; color: white; }
        """)

        # 创建6个页面
        self.device_page = DevicePage()
        self.calibration_page = CalibrationPage()
        self.teaching_page = TeachingPage()
        self.production_page = ProductionPage()
        self.voice_page = VoiceCommandPage()
        self.settings_page = SettingsPage()

        self.tabs.addTab(self.device_page, "🔌 设备连接")
        self.tabs.addTab(self.calibration_page, "📷 视觉标定")
        self.tabs.addTab(self.teaching_page, "🧠 示教训练")
        self.tabs.addTab(self.production_page, "⚙️ 生产运行")
        self.tabs.addTab(self.voice_page, "🗣️ 语音指令")
        self.tabs.addTab(self.settings_page, "⚙️ 系统设置")

        main_layout.addWidget(self.tabs)

        # 底部状态栏
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("就绪 | 设备未连接 | 授权未激活")
        self.setStatusBar(self.status_bar)

    def wire_backend(self, robot, factory, vision, recorder,
                     trainer, template_mgr, agent, db, license_mgr):
        """连接所有后端到前端页面"""
        self._robot = robot
        self._factory = factory
        self._vision = vision
        self._recorder = recorder
        self._trainer = trainer
        self._template_mgr = template_mgr
        self._agent = agent
        self._db = db
        self._license_mgr = license_mgr

        self.device_page.set_backend(robot, factory, license_mgr)
        self.calibration_page.set_vision_engine(vision)
        self.teaching_page.set_backend(recorder, trainer, template_mgr)
        self.production_page.set_backend(robot, vision)
        self.voice_page.set_agent(agent)
        self.settings_page.set_backend(db, robot)

    def closeEvent(self, event):
        """关闭时安全释放资源"""
        if self._vision:
            self._vision.close()
        if self._robot:
            self._robot.disconnect()
        event.accept()


# ============================================================
# 启动入口
# ============================================================

def launch_ui():
    """启动 Qt 上位机"""
    import cv2
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 深色主题
    app.setStyleSheet("""
        QMainWindow { background: #f5f6fa; }
        QGroupBox { font-size: 13px; font-weight: bold; border: 1px solid #ddd; border-radius: 4px; margin-top: 8px; padding-top: 16px; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
        QPushButton { padding: 6px 12px; border: 1px solid #bbb; border-radius: 4px; background: #ecf0f1; }
        QPushButton:hover { background: #d5dbdb; }
        QPushButton:pressed { background: #bdc3c7; }
        QPushButton:disabled { color: #999; }
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { padding: 4px 8px; border: 1px solid #bbb; border-radius: 3px; }
        QTextEdit { border: 1px solid #bbb; border-radius: 3px; }
        QTableWidget { gridline-color: #ddd; }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    launch_ui()
