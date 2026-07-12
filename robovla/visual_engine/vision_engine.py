"""
RoboVLA V2.0 - 视觉感知引擎

核心功能:
1. 相机自动标定与畸变矫正
2. 工业图像预处理(暗光/逆光增强)
3. 工件特征库管理与特征提取
4. 实时偏移计算(X/Y/角度)
5. 物料异常判别(缺料/堆叠/错位)
"""

import cv2
import numpy as np
import json
import sqlite3
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
import time

logger = logging.getLogger(__name__)


# ============================================================
# 数据类型
# ============================================================

@dataclass
class CalibrationParams:
    """相机标定参数"""
    camera_matrix: np.ndarray = None     # 3x3 内参矩阵
    dist_coeffs: np.ndarray = None       # 畸变系数 [k1,k2,p1,p2,k3]
    resolution: Tuple[int, int] = (1920, 1080)
    fx: float = 0.0
    fy: float = 0.0
    cx: float = 0.0
    cy: float = 0.0

    def __post_init__(self):
        if self.camera_matrix is not None and self.camera_matrix.size == 9:
            self.fx = self.camera_matrix[0, 0]
            self.fy = self.camera_matrix[1, 1]
            self.cx = self.camera_matrix[0, 2]
            self.cy = self.camera_matrix[1, 2]

    def to_dict(self) -> Dict:
        return {
            "camera_matrix": self.camera_matrix.tolist() if self.camera_matrix is not None else None,
            "dist_coeffs": self.dist_coeffs.tolist() if self.dist_coeffs is not None else None,
            "resolution": list(self.resolution),
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "CalibrationParams":
        inst = cls()
        if d.get("camera_matrix"):
            inst.camera_matrix = np.array(d["camera_matrix"], dtype=np.float32)
            inst.fx, inst.fy = inst.camera_matrix[0, 0], inst.camera_matrix[1, 1]
            inst.cx, inst.cy = inst.camera_matrix[0, 2], inst.camera_matrix[1, 2]
        if d.get("dist_coeffs"):
            inst.dist_coeffs = np.array(d["dist_coeffs"], dtype=np.float32)
        if d.get("resolution"):
            inst.resolution = tuple(d["resolution"])
        return inst


@dataclass
class OffsetResult:
    """偏移计算结果"""
    delta_x_mm: float = 0.0       # X方向偏移(mm)
    delta_y_mm: float = 0.0       # Y方向偏移(mm)
    delta_angle_deg: float = 0.0  # 旋转角度偏移(度)
    match_score: float = 0.0      # 匹配分数(0~1)
    detected: bool = False        # 是否检测到工件
    anomaly: Optional[str] = None # 异常类型: missing/stacked/misaligned/defective
    timestamp: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "dx_mm": round(self.delta_x_mm, 3),
            "dy_mm": round(self.delta_y_mm, 3),
            "da_deg": round(self.delta_angle_deg, 2),
            "score": round(self.match_score, 3),
            "detected": self.detected,
            "anomaly": self.anomaly,
        }

    def is_valid(self, max_offset_mm: float = 15.0) -> bool:
        """偏移是否在可补偿范围内"""
        if not self.detected:
            return False
        dist = np.hypot(self.delta_x_mm, self.delta_y_mm)
        return dist <= max_offset_mm and self.match_score >= 0.8


@dataclass
class WorkpieceSample:
    """工件样本数据"""
    id: int
    name: str
    image: np.ndarray              # 标准化模板图像
    keypoints: np.ndarray          # SIFT/ORB 关键点
    descriptors: np.ndarray        # 特征描述子
    contour: np.ndarray            # 工件轮廓
    reference_pose: np.ndarray     # 标准位姿 [x,y,z,rx,ry,rz]
    pixel_scale: float = 1.0       # mm/pixel 像素物理比例
    created_at: float = 0.0


# ============================================================
# 相机标定模块
# ============================================================

class CameraCalibrator:
    """
    一键相机标定模块

    使用棋盘格标准方法完成畸变矫正。
    支持 USB 2.0 工业相机，适配不同安装角度和高度。

    使用方式:
        calib = CameraCalibrator()
        calib.collect_samples(camera_id=0, count=20)
        params = calib.calibrate(checkerboard_size=(9, 6), square_size=25.0)
        calib.save("camera_params.json")
    """

    def __init__(self):
        self._calib_params: Optional[CalibrationParams] = None
        self._samples: List[np.ndarray] = []  # 标定采样帧

    def collect_samples(self, camera_id: int = 0,
                        count: int = 20, delay: float = 0.5) -> int:
        """
        自动采集标定棋盘格样本

        Args:
            camera_id: 相机设备ID
            count: 采集帧数
            delay: 帧间延迟(秒)
        Returns:
            成功采集的帧数
        """
        cap = cv2.VideoCapture(camera_id)
        if not cap.isOpened():
            raise RuntimeError(f"无法打开相机 {camera_id}")

        collected = 0
        logger.info(f"开始采集标定样本，目标 {count} 帧...")

        while collected < count:
            ret, frame = cap.read()
            if not ret:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # 自动检测棋盘格
            found, corners = cv2.findChessboardCorners(
                gray, (9, 6), None
            )
            if found:
                corners_refined = cv2.cornerSubPix(
                    gray, corners, (11, 11), (-1, -1),
                    (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
                )
                cv2.drawChessboardCorners(frame, (9, 6), corners_refined, found)
                self._samples.append(gray.copy())
                collected += 1
                logger.info(f"  采样 {collected}/{count}")

            cv2.imshow("Calibration Sample - Press ESC to skip", frame)
            if cv2.waitKey(int(delay * 1000)) == 27:
                break

        cap.release()
        cv2.destroyAllWindows()
        logger.info(f"标定样本采集完成: {len(self._samples)} 帧")
        return len(self._samples)

    def calibrate(self, checkerboard_size: Tuple[int, int] = (9, 6),
                  square_size: float = 25.0,
                  resolution: Tuple[int, int] = (1920, 1080)) -> CalibrationParams:
        """
        执行相机标定计算

        Args:
            checkerboard_size: 棋盘格内角点数 (列, 行)
            square_size: 棋盘格方格物理尺寸(mm)
            resolution: 相机分辨率
        Returns:
            CalibrationParams 标定结果
        """
        if len(self._samples) < 10:
            raise ValueError(f"需要至少10帧样本，当前: {len(self._samples)}")

        logger.info("开始相机标定计算...")

        # 准备物点(物理棋盘格角点)
        objp = np.zeros((checkerboard_size[0] * checkerboard_size[1], 3), np.float32)
        objp[:, :2] = np.mgrid[0:checkerboard_size[0], 0:checkerboard_size[1]].T.reshape(-1, 2)
        objp *= square_size

        obj_points = []
        img_points = []

        for gray in self._samples:
            ret, corners = cv2.findChessboardCorners(gray, checkerboard_size, None)
            if ret:
                obj_points.append(objp)
                corners_refined = cv2.cornerSubPix(
                    gray, corners, (11, 11), (-1, -1),
                    (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
                )
                img_points.append(corners_refined)

        # 标定计算
        ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(
            obj_points, img_points, gray.shape[::-1], None, None
        )

        if not ret:
            raise RuntimeError("标定失败，请检查棋盘格质量和采样数量")

        # 评估重投影误差
        total_error = 0
        for i in range(len(obj_points)):
            projected, _ = cv2.projectPoints(obj_points[i], rvecs[i], tvecs[i], mtx, dist)
            error = cv2.norm(img_points[i], projected, cv2.NORM_L2) / len(projected)
            total_error += error
        mean_error = total_error / len(obj_points)

        self._calib_params = CalibrationParams(
            camera_matrix=mtx,
            dist_coeffs=dist,
            resolution=resolution,
        )
        logger.info(f"✅ 标定完成 | 重投影误差: {mean_error:.3f} px")
        return self._calib_params

    def undistort(self, image: np.ndarray) -> np.ndarray:
        """畸变矫正"""
        if self._calib_params is None:
            logger.warning("未标定，返回原始图像")
            return image

        return cv2.undistort(
            image,
            self._calib_params.camera_matrix,
            self._calib_params.dist_coeffs
        )

    def pixel_to_world(self, pixel_xy: np.ndarray,
                       z_mm: float = 300.0) -> np.ndarray:
        """
        像素坐标转世界坐标(需已知目标高度 Z)

        Args:
            pixel_xy: [px, py] 像素坐标
            z_mm: 工件平面高度(mm)
        Returns:
            [wx, wy] 世界坐标(mm)
        """
        if self._calib_params is None:
            return pixel_xy

        cp = self._calib_params
        # 针孔相机反投影
        xc = (pixel_xy[0] - cp.cx) * z_mm / cp.fx
        yc = (pixel_xy[1] - cp.cy) * z_mm / cp.fy
        return np.array([xc, yc])

    def save(self, path: str):
        """保存标定参数到文件"""
        if self._calib_params is None:
            raise ValueError("尚无标定参数")
        with open(path, 'w') as f:
            json.dump(self._calib_params.to_dict(), f, indent=2)
        logger.info(f"标定参数已保存: {path}")

    def load(self, path: str):
        """从文件加载标定参数"""
        with open(path, 'r') as f:
            d = json.load(f)
        self._calib_params = CalibrationParams.from_dict(d)
        logger.info(f"标定参数已加载: {path}")


# ============================================================
# 图像预处理模块
# ============================================================

class ImagePreprocessor:
    """
    工业图像预处理流水线

    针对工厂车间典型光照问题优化:
    - 逆光: 自适应亮度均衡
    - 暗光: CLAHE 局部直方图均衡
    - 反光: 高光抑制
    - 噪声: 双边滤波
    """

    @staticmethod
    def auto_brightness(image: np.ndarray) -> np.ndarray:
        """自动亮度校正(基于灰度均值自适应)"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        mean_brightness = np.mean(gray)

        # 亮度目标区间: [90, 160]
        if mean_brightness < 80:  # 过暗
            gamma = np.log(128 / 255) / np.log(mean_brightness / 255)
            gamma = np.clip(gamma, 0.5, 2.5)
            lut = np.array([((i / 255.0) ** gamma) * 255 for i in range(256)]).astype(np.uint8)
            return cv2.LUT(image, lut)

        elif mean_brightness > 180:  # 过亮/逆光
            alpha = 128.0 / mean_brightness
            return cv2.convertScaleAbs(image, alpha=alpha, beta=0)

        return image

    @staticmethod
    def enhance_local_contrast(image: np.ndarray,
                               clip_limit: float = 2.0,
                               grid_size: int = 8) -> np.ndarray:
        """CLAHE 自适应局部对比度增强"""
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=clip_limit,
                                tileGridSize=(grid_size, grid_size))
        l_enhanced = clahe.apply(l)
        enhanced = cv2.merge([l_enhanced, a, b])
        return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

    @staticmethod
    def denoise_bilateral(image: np.ndarray,
                          d: int = 5,
                          sigma_color: float = 50,
                          sigma_space: float = 50) -> np.ndarray:
        """保边去噪(保留工件边缘细节的同时去除传感器噪声)"""
        return cv2.bilateralFilter(image, d, sigma_color, sigma_space)

    @staticmethod
    def sharpen(image: np.ndarray, strength: float = 1.0) -> np.ndarray:
        """USM锐化增强工作边缘"""
        blurred = cv2.GaussianBlur(image, (0, 0), 3)
        return cv2.addWeighted(image, 1.0 + strength, blurred, -strength, 0)

    @classmethod
    def full_pipeline(cls, image: np.ndarray,
                      denoise: bool = True,
                      enhance: bool = True,
                      sharpen: bool = True) -> np.ndarray:
        """
        完整预处理流水线

        顺序: 亮度均衡 → 去噪 → 对比度增强 → 锐化
        """
        img = image.copy()
        img = cls.auto_brightness(img)
        if denoise:
            img = cls.denoise_bilateral(img)
        if enhance:
            img = cls.enhance_local_contrast(img)
        if sharpen:
            img = cls.sharpen(img, strength=0.5)
        return img


# ============================================================
# 工件特征库
# ============================================================

class WorkpieceFeatureLibrary:
    """
    工件特征库管理

    支持:
    - 单张/批量样本录入
    - SIFT特征提取与匹配
    - 轮廓特征提取
    - SQLite持久化

    使用方式:
        lib = WorkpieceFeatureLibrary("workpiece_features.db")
        sample_id = lib.add_sample("螺丝_M3", image, pose)
        offset = lib.compute_offset(sample_id, live_frame)
    """

    def __init__(self, db_path: str = "workpiece_features.db"):
        self.db_path = db_path
        self._feature_extractor = cv2.SIFT_create(
            nfeatures=800,
            nOctaveLayers=4,
            contrastThreshold=0.04,
            edgeThreshold=12,
            sigma=1.6
        )
        self._matcher = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
        self._samples: Dict[int, WorkpieceSample] = {}
        self._init_db()
        self._load_all()

    def _init_db(self):
        """初始化 SQLite 数据库"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS workpiece_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            image_path TEXT,
            contour BLOB,
            reference_pose TEXT,
            pixel_scale REAL DEFAULT 1.0,
            created_at REAL
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS feature_descriptors (
            sample_id INTEGER PRIMARY KEY,
            descriptors BLOB,
            keypoints BLOB,
            FOREIGN KEY(sample_id) REFERENCES workpiece_samples(id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS match_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_id INTEGER,
            score REAL,
            dx REAL, dy REAL, da REAL,
            anomaly TEXT,
            timestamp REAL
        )''')
        conn.commit()
        conn.close()

    def _load_all(self):
        """启动时从数据库加载所有样本"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT id, name, image_path, pixel_scale FROM workpiece_samples")
        for row in c.fetchall():
            sample_id, name, img_path, scale = row
            if img_path and Path(img_path).exists():
                image = cv2.imread(img_path)
                kp, desc = self._extract_features(image)
                contour = self._extract_contour(image)
                self._samples[sample_id] = WorkpieceSample(
                    id=sample_id, name=name, image=image,
                    keypoints=np.array([(p.pt[0], p.pt[1], p.size, p.angle) for p in kp]),
                    descriptors=desc,
                    contour=contour if contour is not None else np.array([]),
                    reference_pose=np.zeros(6),
                    pixel_scale=scale,
                )
        conn.close()
        logger.info(f"已加载 {len(self._samples)} 个工件样本")

    def _extract_features(self, image: np.ndarray) -> Tuple[Tuple, np.ndarray]:
        """SIFT 特征提取"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return self._feature_extractor.detectAndCompute(gray, None)

    def _extract_contour(self, image: np.ndarray) -> Optional[np.ndarray]:
        """工件轮廓提取"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # 自适应阈值二值化
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 31, 5
        )
        # 形态学闭运算填充孔洞
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            # 取最大轮廓(假定为工件)
            return max(contours, key=cv2.contourArea)
        return None

    def add_sample(self, name: str, image: np.ndarray,
                   reference_pose: np.ndarray = None,
                   pixel_scale: float = 1.0) -> int:
        """
        录入工件样本

        Args:
            name: 工件名称
            image: 工件模板图像
            reference_pose: 标准位姿(6维)
            pixel_scale: mm/pixel 比例
        Returns:
            sample_id
        """
        preprocessed = ImagePreprocessor.full_pipeline(image)
        kp, desc = self._extract_features(preprocessed)
        contour = self._extract_contour(preprocessed)

        # 保存到 SQLite
        img_path = f"test_data/samples/{name}_{int(time.time())}.jpg"
        Path(img_path).parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(img_path, preprocessed)

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO workpiece_samples (name, image_path, contour, reference_pose, pixel_scale, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            name, img_path,
            contour.tobytes() if contour is not None else None,
            json.dumps(reference_pose.tolist()) if reference_pose is not None else "[0,0,0,0,0,0]",
            pixel_scale,
            time.time()
        ))
        sample_id = c.lastrowid

        c.execute("INSERT INTO feature_descriptors (sample_id, descriptors, keypoints) VALUES (?, ?, ?)",
                  (sample_id,
                   desc.tobytes() if desc is not None else None,
                   np.array([(p.pt[0], p.pt[1], p.size, p.angle) for p in kp]).tobytes()))
        conn.commit()
        conn.close()

        # 加入内存缓存
        self._samples[sample_id] = WorkpieceSample(
            id=sample_id, name=name, image=preprocessed,
            keypoints=np.array([(p.pt[0], p.pt[1], p.size, p.angle) for p in kp]),
            descriptors=desc,
            contour=contour if contour is not None else np.array([]),
            reference_pose=reference_pose if reference_pose is not None else np.zeros(6),
            pixel_scale=pixel_scale,
            created_at=time.time()
        )
        logger.info(f"✅ 新增工件样本: [{sample_id}] {name} | {len(kp)} 特征点")
        return sample_id

    def delete_sample(self, sample_id: int):
        """删除工件样本"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("DELETE FROM feature_descriptors WHERE sample_id=?", (sample_id,))
        c.execute("DELETE FROM workpiece_samples WHERE id=?", (sample_id,))
        conn.commit()
        conn.close()
        self._samples.pop(sample_id, None)
        logger.info(f"已删除工件样本: {sample_id}")

    def list_samples(self) -> List[Dict]:
        """列出所有样本概要信息"""
        result = []
        for sid, s in self._samples.items():
            result.append({
                "id": sid, "name": s.name,
                "keypoints": len(s.keypoints) if s.keypoints is not None else 0,
                "created_at": s.created_at,
            })
        return result

    def compute_offset(self, sample_id: int,
                       live_image: np.ndarray) -> OffsetResult:
        """
        计算实时图像与模板之间的偏移量

        Args:
            sample_id: 工件样本ID
            live_image: 实时相机帧
        Returns:
            OffsetResult 偏移量 + 异常判定
        """
        sample = self._samples.get(sample_id)
        if sample is None:
            return OffsetResult(anomaly="unknown_sample")

        # 预处理
        preprocessed = ImagePreprocessor.full_pipeline(live_image)
        gray = cv2.cvtColor(preprocessed, cv2.COLOR_BGR2GRAY)

        # === 1. 特征点匹配 (SIFT) ===
        live_kp, live_desc = self._feature_extractor.detectAndCompute(gray, None)
        if live_desc is None or len(live_desc) < 5:
            return OffsetResult(anomaly="low_features")

        matches = self._matcher.knnMatch(sample.descriptors, live_desc, k=2)
        good_matches = []
        for m_n in matches:
            if len(m_n) == 2:
                m, n = m_n
                if m.distance < 0.7 * n.distance:  # Lowe's ratio test
                    good_matches.append(m)

        match_score = len(good_matches) / max(len(live_kp), 1)

        # === 2. 异常判别 ===
        anomaly = self._detect_anomaly(preprocessed, sample, match_score)

        # === 3. 偏移计算 ===
        if len(good_matches) < 4:
            return OffsetResult(detected=False, anomaly=anomaly or "low_match")

        src_pts = np.float32([list(sample.descriptors[m.queryIdx].shape)
                              for m in good_matches]).reshape(-1, 1, 2)

        # 从 keypoints 提取匹配点坐标
        sample_kp_pts = np.float32([
            sample.keypoints[m.queryIdx][:2] for m in good_matches
        ])
        live_kp_pts = np.float32([
            (live_kp[m.trainIdx].pt[0], live_kp[m.trainIdx].pt[1])
            for m in good_matches
        ])

        # 相似变换(平移+旋转+缩放)
        transform, inliers = cv2.estimateAffinePartial2D(
            live_kp_pts.reshape(-1, 1, 2),
            sample_kp_pts.reshape(-1, 1, 2),
            method=cv2.RANSAC, ransacReprojThreshold=3.0
        )

        if transform is None:
            return OffsetResult(detected=False, anomaly="transform_failed")

        # 提取平移和旋转
        dx_px = transform[0, 2]
        dy_px = transform[1, 2]
        angle_rad = np.arctan2(transform[1, 0], transform[0, 0])
        angle_deg = np.degrees(angle_rad)

        # 像素 → 毫米
        dx_mm = dx_px * sample.pixel_scale
        dy_mm = dy_px * sample.pixel_scale

        # === 4. 记录匹配历史 ===
        self._log_match(sample_id, match_score, dx_mm, dy_mm, angle_deg, anomaly)

        return OffsetResult(
            delta_x_mm=dx_mm,
            delta_y_mm=dy_mm,
            delta_angle_deg=angle_deg,
            match_score=match_score,
            detected=True,
            anomaly=anomaly,
            timestamp=time.time(),
        )

    def _detect_anomaly(self, image: np.ndarray,
                        sample: WorkpieceSample,
                        match_score: float) -> Optional[str]:
        """工件异常检测"""
        # 缺料检测 → 匹配分数极低
        if match_score < 0.15:
            return "missing"

        # 轮廓面积对比 → 堆叠/错位
        live_contour = self._extract_contour(image)
        if live_contour is not None and sample.contour is not None:
            area_ratio = cv2.contourArea(live_contour) / max(cv2.contourArea(sample.contour), 1)
            if area_ratio > 1.6:
                return "stacked"  # 面积过大 → 堆叠
            elif area_ratio < 0.3:
                return "misaligned"  # 面积过小 → 严重错位

        return None

    def _log_match(self, sample_id: int, score: float,
                   dx: float, dy: float, da: float,
                   anomaly: Optional[str]):
        """记录匹配日志"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                INSERT INTO match_history (sample_id, score, dx, dy, da, anomaly, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (sample_id, round(score, 4),
                  round(dx, 3), round(dy, 3), round(da, 2),
                  anomaly, time.time()))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def batch_add_samples(self, sample_dir: str,
                          name_prefix: str = "workpiece") -> List[int]:
        """
        批量录入目录中的工件图片

        Args:
            sample_dir: 图片目录路径
            name_prefix: 命名前缀
        Returns:
            sample_id 列表
        """
        ids = []
        d = Path(sample_dir)
        for i, img_file in enumerate(sorted(d.glob("*.jpg")) + sorted(d.glob("*.png"))):
            image = cv2.imread(str(img_file))
            if image is not None:
                sid = self.add_sample(f"{name_prefix}_{i:03d}", image)
                ids.append(sid)
        logger.info(f"批量录入完成: {len(ids)} 个工件样本")
        return ids


# ============================================================
# 视觉引擎统一入口
# ============================================================

class VisionEngine:
    """
    视觉感知引擎 - 统一入口

    整合标定、预处理、特征库、偏移计算四大子系统，
    对外提供简洁的视觉服务接口。

    使用方式:
        engine = VisionEngine()
        engine.init_camera(camera_id=0, calib_file="camera_params.json")
        offset = engine.detect_workpiece(sample_id=1)
    """

    def __init__(self, db_path: str = "test_data/workpiece_features.db"):
        self.calibrator = CameraCalibrator()
        self.preprocessor = ImagePreprocessor()
        self.feature_lib = WorkpieceFeatureLibrary(db_path)
        self._cap: Optional[cv2.VideoCapture] = None
        self._camera_id = 0
        self._executor = ThreadPoolExecutor(max_workers=2)

    def init_camera(self, camera_id: int = 0,
                    calib_file: Optional[str] = None) -> bool:
        """初始化相机并加载标定参数"""
        self._camera_id = camera_id
        self._cap = cv2.VideoCapture(camera_id)
        if not self._cap.isOpened():
            logger.error(f"无法打开相机 {camera_id}")
            return False

        # 设置分辨率
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        self._cap.set(cv2.CAP_PROP_FPS, 30)

        # 加载标定参数
        if calib_file and Path(calib_file).exists():
            self.calibrator.load(calib_file)
            logger.info(f"已加载标定参数: {calib_file}")

        return True

    def capture_frame(self) -> Optional[np.ndarray]:
        """采集一帧图像"""
        if self._cap is None:
            logger.error("相机未初始化")
            return None
        ret, frame = self._cap.read()
        if not ret:
            logger.warning("采集帧失败")
            return None

        # 畸变矫正
        frame = self.calibrator.undistort(frame)
        return frame

    def detect_workpiece(self, sample_id: int) -> OffsetResult:
        """
        单帧检测: 采集 → 预处理 → 偏移计算 → 异常判别
        """
        frame = self.capture_frame()
        if frame is None:
            return OffsetResult(anomaly="capture_failed")

        preprocessed = self.preprocessor.full_pipeline(frame)
        return self.feature_lib.compute_offset(sample_id, preprocessed)

    def add_workpiece(self, name: str, reference_pose: np.ndarray = None,
                      pixel_scale: float = 0.05) -> int:
        """录入新工件"""
        frame = self.capture_frame()
        if frame is None:
            raise RuntimeError("无法采集工件图像")
        return self.feature_lib.add_sample(name, frame, reference_pose, pixel_scale)

    def close(self):
        """释放资源"""
        if self._cap:
            self._cap.release()
            cv2.destroyAllWindows()
        self._executor.shutdown(wait=False)
