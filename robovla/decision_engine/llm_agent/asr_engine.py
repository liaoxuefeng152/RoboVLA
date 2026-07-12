"""
RoboVLA V2.0 - 离线语音识别模块 (ASR)
本地运行，完全断网可用。支持 Whisper/FasterWhisper/Sherpa 三种引擎。
"""

import logging
import threading
import queue
import time
import json
from dataclasses import dataclass
from typing import Optional, Callable
from enum import Enum

logger = logging.getLogger("RoboVLA.ASR")


class ASREngine(Enum):
    """语音识别引擎类型"""
    WHISPER = "whisper"               # OpenAI Whisper (需下载模型)
    FASTER_WHISPER = "faster_whisper" # CTranslate2 加速版 (推荐Jetson)
    SHERPA_ONNX = "sherpa_onnx"       # Sherpa-ONNX 流式 (最低延迟)
    VOSK = "vosk"                     # Vosk 离线 (最轻量，中文需模型)


@dataclass
class ASRResult:
    text: str
    confidence: float
    is_final: bool = True
    timestamp: float = 0.0


class OfflineASR:
    """
    离线语音识别引擎
    支持多种后端切换，自动降级
    """

    # 工业产线常用指令词典 (提高识别准确率)
    INDUSTRY_COMMANDS = [
        "开始生产", "停止生产", "暂停", "继续",
        "加速", "减速", "速度快一点", "速度慢一点",
        "更换工件", "示教模式", "自动模式",
        "急停", "复位", "回原点",
        "产量多少", "故障报告", "状态查询",
        "上一工序", "下一工序", "确认", "取消",
    ]

    def __init__(self,
                 engine: ASREngine = ASREngine.FASTER_WHISPER,
                 model_size: str = "small",
                 language: str = "zh",
                 device: str = "cuda"):
        self.engine_type = engine
        self.model_size = model_size
        self.language = language
        self.device = device
        self._model = None
        self._running = False
        self._audio_queue = queue.Queue()
        self._result_queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._on_result: Optional[Callable[[ASRResult], None]] = None

    def init(self) -> bool:
        """初始化语音识别模型"""
        try:
            if self.engine_type == ASREngine.FASTER_WHISPER:
                self._init_faster_whisper()
            elif self.engine_type == ASREngine.SHERPA_ONNX:
                self._init_sherpa_onnx()
            elif self.engine_type == ASREngine.VOSK:
                self._init_vosk()
            else:
                self._init_whisper()
            logger.info(f"ASR 引擎初始化成功: {self.engine_type.value}")
            return True
        except Exception as e:
            logger.error(f"ASR 初始化失败: {e}")
            # 尝试降级到 Vosk
            if self.engine_type != ASREngine.VOSK:
                logger.warning("尝试降级到 Vosk 引擎...")
                self.engine_type = ASREngine.VOSK
                return self._init_vosk()
            return False

    def _init_faster_whisper(self):
        """FasterWhisper (CTranslate2) - Jetson Orin 推荐"""
        from faster_whisper import WhisperModel
        compute_type = "int8_float16" if self.device == "cuda" else "int8"
        self._model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=compute_type,
            num_workers=2,
        )
        logger.info(f"FasterWhisper 加载完成: {self.model_size} on {self.device}")

    def _init_sherpa_onnx(self):
        """Sherpa-ONNX 流式引擎 - 最低延迟"""
        try:
            import sherpa_onnx
            self._model = sherpa_onnx.OfflineRecognizer(
                sherpa_onnx.OfflineRecognizerConfig(
                    model=sherpa_onnx.OfflineModelConfig(
                        paraformer=sherpa_onnx.OfflineParaformerModelConfig(
                            model="./models/sherpa/paraformer-model.onnx"
                        ),
                        tokens="./models/sherpa/tokens.txt",
                    )
                )
            )
        except ImportError:
            raise RuntimeError("Sherpa-ONNX 未安装, 请 pip install sherpa-onnx")

    def _init_vosk(self):
        """Vosk 离线引擎 - 最轻量"""
        try:
            import vosk
            self._model = vosk.Model(f"./models/vosk-model-cn-0.22")
            logger.info("Vosk 模型加载完成")
        except ImportError:
            raise RuntimeError("Vosk 未安装, 请 pip install vosk")
        except Exception:
            raise RuntimeError("Vosk 模型未下载, 请放到 ./models/vosk-model-cn-0.22/")

    def _init_whisper(self):
        """OpenAI Whisper 原始版"""
        import whisper
        self._model = whisper.load_model(self.model_size, device=self.device)
        logger.info(f"Whisper {self.model_size} 加载完成")

    def set_callback(self, callback: Callable[[ASRResult], None]):
        """设置识别结果回调"""
        self._on_result = callback

    # --- 流式处理 (从麦克风/音频流) ---

    def start_streaming(self, sample_rate: int = 16000):
        """启动持续监听线程"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._stream_loop,
                                        args=(sample_rate,), daemon=True)
        self._thread.start()
        logger.info(f"ASR 流式监听已启动 (采样率: {sample_rate}Hz)")

    def stop_streaming(self):
        """停止监听"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("ASR 流式监听已停止")

    def _stream_loop(self, sample_rate: int):
        """流式音频采集循环"""
        # 使用 PyAudio 或系统声卡采集
        try:
            import pyaudio
            import numpy as np

            chunk_size = int(sample_rate * 0.5)  # 500ms 片段
            p = pyaudio.PyAudio()
            stream = p.open(format=pyaudio.paInt16,
                            channels=1,
                            rate=sample_rate,
                            input=True,
                            frames_per_buffer=chunk_size)

            audio_buffer = np.array([], dtype=np.int16)
            last_transcribe = time.time()

            while self._running:
                data = stream.read(chunk_size, exception_on_overflow=False)
                audio_chunk = np.frombuffer(data, dtype=np.int16)
                audio_buffer = np.concatenate([audio_buffer, audio_chunk])

                # 每 2 秒或检测到停顿后转写
                if time.time() - last_transcribe > 2.0 and len(audio_buffer) > sample_rate * 1.0:
                    self._audio_queue.put(audio_buffer.copy())
                    audio_buffer = np.array([], dtype=np.int16)
                    last_transcribe = time.time()

            stream.stop_stream()
            stream.close()
            p.terminate()

        except ImportError:
            logger.warning("PyAudio 未安装，流式采集不可用，请使用 transcribe_file()")

    def transcribe_file(self, audio_path: str) -> ASRResult:
        """离线文件转写"""
        return self.transcribe(audio_path)

    # --- 核心转写 ---

    def transcribe(self, audio_input, initial_prompt: str = "") -> ASRResult:
        """
        转写音频到文本
        :param audio_input: 文件路径(str) 或 numpy 音频数组
        :param initial_prompt: 上下文提示(提高工业术语准确率)
        """
        if self._model is None:
            return ASRResult(text="", confidence=0.0)

        try:
            if self.engine_type == ASREngine.FASTER_WHISPER:
                return self._transcribe_faster_whisper(audio_input, initial_prompt)
            elif self.engine_type == ASREngine.SHERPA_ONNX:
                return self._transcribe_sherpa(audio_input)
            elif self.engine_type == ASREngine.VOSK:
                return self._transcribe_vosk(audio_input)
            else:
                return self._transcribe_whisper(audio_input)
        except Exception as e:
            logger.error(f"转写失败: {e}")
            return ASRResult(text="", confidence=0.0)

    def _transcribe_faster_whisper(self, audio_input, prompt: str) -> ASRResult:
        segments, info = self._model.transcribe(
            audio_input,
            language=self.language,
            beam_size=5,
            vad_filter=True,
            initial_prompt=prompt or "这是一条工业机器人产线语音指令",
        )
        texts = []
        total_conf = 0.0
        count = 0
        for seg in segments:
            texts.append(seg.text.strip())
            total_conf += seg.avg_log_prob
            count += 1

        text = "".join(texts)
        confidence = min(1.0, max(0.0, (total_conf / count + 2.0) / 4.0)) if count > 0 else 0.0

        # 后处理：匹配工业指令词典
        text = self._post_process(text)

        result = ASRResult(text=text, confidence=confidence, is_final=True,
                           timestamp=time.time())
        if self._on_result:
            self._on_result(result)
        return result

    def _transcribe_whisper(self, audio_input) -> ASRResult:
        import whisper
        result = self._model.transcribe(
            audio_input,
            language=self.language,
            fp16=(self.device == "cuda"),
        )
        text = result["text"].strip()
        text = self._post_process(text)
        return ASRResult(text=text, confidence=0.85, is_final=True,
                         timestamp=time.time())

    def _transcribe_vosk(self, audio_input) -> ASRResult:
        import vosk
        import json
        rec = vosk.KaldiRecognizer(self._model, 16000)
        rec.SetWords(True)

        if isinstance(audio_input, str):
            import wave
            wf = wave.open(audio_input, "rb")
            text = ""
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                if rec.AcceptWaveform(data):
                    res = json.loads(rec.Result())
                    text += res.get("text", "")
        else:
            # numpy array
            rec.AcceptWaveform(audio_input.tobytes())
            text = json.loads(rec.FinalResult()).get("text", "")

        text = self._post_process(text)
        return ASRResult(text=text, confidence=0.75, is_final=True,
                         timestamp=time.time())

    def _transcribe_sherpa(self, audio_input) -> ASRResult:
        result = self._model.transcribe(audio_input)
        text = result.text.strip() if hasattr(result, 'text') else str(result)
        return ASRResult(text=text, confidence=0.80, is_final=True,
                         timestamp=time.time())

    def _post_process(self, text: str) -> str:
        """工业指令后处理：纠正常见误识别、匹配指令词典"""
        # 常见误识别纠正映射
        corrections = {
            "开市生产": "开始生产",
            "停止生成": "停止生产",
            "继续生产": "继续",
            "家教模式": "示教模式",
            "叫醒": "急停",
            "快递一点": "速度快一点",
            "买一点": "慢一点",
            "故障报警": "故障报告",
            "产量多少": "产量多少",
        }
        for wrong, correct in corrections.items():
            if wrong in text:
                text = text.replace(wrong, correct)

        # 模糊匹配工业指令词典
        if text:
            for cmd in self.INDUSTRY_COMMANDS:
                # 子串匹配
                if len(cmd) >= 3 and cmd[:3] in text:
                    return cmd

        return text

    def close(self):
        """释放资源"""
        self.stop_streaming()
        self._model = None
        logger.info("ASR 已释放")
