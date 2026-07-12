"""
RoboVLA V2.0 - 离线语音合成模块 (TTS)
本地运行，用于故障告警播报、操作提示反馈
"""

import logging
import threading
import queue
import os
import tempfile
from dataclasses import dataclass
from typing import Optional, Callable
from enum import Enum

logger = logging.getLogger("RoboVLA.TTS")


class TTSEngine(Enum):
    EDGE_TTS = "edge-tts"         # Edge TTS 离线方案 (需预下载语音包)
    PIPER = "piper"               # Piper TTS (最轻量，推荐 Jetson)
    COQUI = "coqui"              # Coqui TTS (质量最好，较慢)


@dataclass
class TTSConfig:
    engine: TTSEngine = TTSEngine.PIPER
    voice: str = "zh-CN"           # 中文普通话
    speed: float = 1.0             # 语速倍率
    volume: float = 1.0            # 音量倍率
    sample_rate: int = 22050       # 采样率


class OfflineTTS:
    """
    离线语音合成引擎
    支持故障告警播报、操作提示反馈
    """

    # 预定义告警/提示模板
    ALERTS = {
        "robot_connected": "机器人已连接",
        "robot_disconnected": "机器人连接断开",
        "task_started": "任务开始执行",
        "task_completed": "任务执行完成",
        "task_failed": "任务执行失败，请检查",
        "emergency_stop": "急停已触发",
        "camera_error": "相机异常，请检查连接",
        "motor_overheat": "电机过热警告",
        "gripper_error": "夹爪异常",
        "calibration_done": "标定完成",
        "train_complete": "训练完成，可以开始生产",
        "cycle_complete": "当前工件加工完成",
        "auth_expiring": "授权即将到期，请续期",
        "production_report": "当前产量",
    }

    def __init__(self, config: TTSConfig = None):
        self.config = config or TTSConfig()
        self._model = None
        self._running = False
        self._queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._on_speak_start: Optional[Callable[[str], None]] = None
        self._on_speak_end: Optional[Callable[[str], None]] = None
        self._audio_device = None

    def init(self) -> bool:
        """初始化 TTS 引擎"""
        try:
            if self.config.engine == TTSEngine.PIPER:
                self._init_piper()
            elif self.config.engine == TTSEngine.EDGE_TTS:
                self._init_edge_tts()
            elif self.config.engine == TTSEngine.COQUI:
                self._init_coqui()
            logger.info(f"TTS 引擎初始化成功: {self.config.engine.value}")
            return True
        except Exception as e:
            logger.error(f"TTS 初始化失败: {e}")
            # 降级尝试 Piper
            if self.config.engine != TTSEngine.PIPER:
                logger.warning("降级到 Piper TTS...")
                self.config.engine = TTSEngine.PIPER
                try:
                    self._init_piper()
                    return True
                except Exception:
                    pass
            return False

    def _init_piper(self):
        """Piper TTS - 最轻量,适合 Jetson"""
        try:
            import piper_tts
            model_path = f"./models/piper/zh_CN-{self.config.voice.lower()}.onnx"
            config_path = f"./models/piper/zh_CN-{self.config.voice.lower()}.json"
            if not os.path.exists(model_path):
                raise FileNotFoundError(
                    f"Piper 中文模型未找到: {model_path}\n"
                    f"下载命令: wget https://huggingface.co/rhasspy/piper-voices/resolve/main/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx"
                )
            self._model = piper_tts.PiperVoice.load(model_path, config_path)
        except ImportError:
            raise RuntimeError("piper-tts 未安装, pip install piper-tts")

    def _init_edge_tts(self):
        """Edge TTS (基于 edge-tts Python 库)"""
        try:
            import edge_tts
            self._model = edge_tts  # 不需要加载模型
        except ImportError:
            raise RuntimeError("edge-tts 未安装, pip install edge-tts")

    def _init_coqui(self):
        """Coqui TTS - XTTS v2"""
        from TTS.api import TTS
        self._model = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2",
                          progress_bar=False)

    def set_callbacks(self, on_start: Callable[[str], None] = None,
                      on_end: Callable[[str], None] = None):
        """设置播报回调"""
        self._on_speak_start = on_start
        self._on_speak_end = on_end

    # --- 同步播报 ---

    def speak(self, text: str, block: bool = True) -> Optional[str]:
        """
        语音播报
        :param text: 播报文本
        :param block: 是否阻塞等待完成
        :return: 音频文件路径(同步模式下)
        """
        logger.info(f"TTS 播报: {text}")
        if self._on_speak_start:
            self._on_speak_start(text)

        audio_path = None
        try:
            if self.config.engine == TTSEngine.PIPER:
                audio_path = self._speak_piper(text)
            elif self.config.engine == TTSEngine.EDGE_TTS:
                audio_path = self._speak_edge_tts(text)
            elif self.config.engine == TTSEngine.COQUI:
                audio_path = self._speak_coqui(text)

            if audio_path and os.path.exists(audio_path):
                self._play_audio(audio_path)

        except Exception as e:
            logger.error(f"TTS 播报失败: {e}")

        if self._on_speak_end:
            self._on_speak_end(text)

        return audio_path

    def _speak_piper(self, text: str) -> str:
        """Piper TTS 合成"""
        import wave
        import numpy as np

        audio = b""
        for audio_bytes in self._model.synthesize_stream_raw(text):
            audio += audio_bytes

        # 写入临时文件
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)

        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.config.sample_rate)
            wf.writeframes(audio)

        return path

    def _speak_edge_tts(self, text: str) -> str:
        """Edge TTS 合成"""
        import edge_tts
        import asyncio

        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)

        voice = "zh-CN-XiaoxiaoNeural" if self.config.voice == "zh-CN" else self.config.voice
        rate = f"{int((self.config.speed - 1.0) * 100):+d}%"

        async def _synthesize():
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            await communicate.save(path)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_synthesize())
        loop.close()

        return path

    def _speak_coqui(self, text: str) -> str:
        """Coqui TTS 合成"""
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        self._model.tts_to_file(text=text,
                                speaker_wav=None,
                                language=self.config.voice,
                                file_path=path)
        return path

    def _play_audio(self, audio_path: str):
        """播放音频文件"""
        try:
            import sounddevice as sd
            import soundfile as sf
            data, sr = sf.read(audio_path)
            sd.play(data, sr)
            sd.wait()
        except ImportError:
            # Fallback: 使用系统命令
            import platform
            system = platform.system()
            if system == "Darwin":
                os.system(f'afplay "{audio_path}"')
            elif system == "Linux":
                os.system(f'aplay "{audio_path}" 2>/dev/null || paplay "{audio_path}" 2>/dev/null')

    # --- 异步队列播报 ---

    def speak_async(self, text: str):
        """异步播报(不阻塞)"""
        self._queue.put(text)

    def start_async_worker(self):
        """启动异步播报线程"""
        self._running = True
        self._thread = threading.Thread(target=self._async_loop, daemon=True)
        self._thread.start()

    def stop_async_worker(self):
        """停止异步播报"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)

    def _async_loop(self):
        while self._running:
            try:
                text = self._queue.get(timeout=1)
                self.speak(text, block=True)
            except queue.Empty:
                continue

    # --- 快捷播报方法 ---

    def alert(self, alert_type: str, extra: str = ""):
        """播报告警"""
        text = self.ALERTS.get(alert_type, alert_type)
        if extra:
            text += f"，{extra}"
        self.speak(text, block=False)

    def speak_report(self, cycle_count: int, success: int, fail: int):
        """播报生产报告"""
        text = f"当前产量 {cycle_count}，成功 {success}，失败 {fail}"
        self.speak(text, block=False)

    def speak_fault(self, code: str, msg: str):
        """播报故障"""
        text = f"故障{code}：{msg}"
        self.speak(text, block=False)

    def close(self):
        """释放资源"""
        self.stop_async_worker()
        self._model = None
        logger.info("TTS 已释放")
