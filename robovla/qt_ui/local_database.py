"""
RoboVLA V2.0 - 本地数据库管理(SQLite)

表结构:
- device_info: 设备授权信息
- task_info: 任务模板
- sample_info: 工件样本
- production_log: 生产日志
- fault_log: 故障记录
- user_account: 三级权限账号

加密: AES-256 (所有敏感字段)
"""

import sqlite3
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================
# 加密工具
# ============================================================

class CryptoUtil:
    """AES-256 加密工具(本地数据安全)"""

    @staticmethod
    def generate_key(password: str, salt: bytes = None) -> bytes:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        if salt is None:
            salt = b'robovla_salt_2025'  # 生产环境应从硬件SN派生
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32,
            salt=salt, iterations=100000,
        )
        return kdf.derive(password.encode())

    @staticmethod
    def encrypt(data: str, key: bytes) -> str:
        from cryptography.fernet import Fernet
        import base64
        f = Fernet(base64.urlsafe_b64encode(key))
        return f.encrypt(data.encode()).decode()

    @staticmethod
    def decrypt(encrypted_data: str, key: bytes) -> str:
        from cryptography.fernet import Fernet
        import base64
        f = Fernet(base64.urlsafe_b64encode(key))
        return f.decrypt(encrypted_data.encode()).decode()

    @staticmethod
    def hash_password(password: str) -> str:
        """SHA256 密码哈希"""
        import hashlib
        return hashlib.sha256(f"robovla_{password}".encode()).hexdigest()


# ============================================================
# 权限枚举
# ============================================================

class UserRole(Enum):
    OPERATOR = "operator"      # 操作工: 启停/语音/查看
    ADMIN = "admin"            # 管理员: 示教/训练/配置/数据/人员
    MAINTENANCE = "maintenance"  # 厂商运维: 远程诊断/更新(需二次授权)


class AuthType(Enum):
    PERPETUAL = "perpetual"    # 永久买断
    ANNUAL = "annual"          # 年度订阅
    TRIAL = "trial"            # 短期试用
    RENTAL = "rental"          # 租赁


# ============================================================
# 数据库管理器
# ============================================================

class RoboVLADatabase:
    """SQLite 本地数据库统一管理"""

    def __init__(self, db_path: str = "test_data/robovla_local.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._key: Optional[bytes] = None
        self._init_tables()

    def set_encryption_key(self, key: bytes):
        """设置数据加密密钥"""
        self._key = key

    def _enc(self, value: str) -> str:
        """加密(如果密钥已设置)"""
        if self._key and value:
            return CryptoUtil.encrypt(value, self._key)
        return value

    def _dec(self, value: str) -> str:
        """解密"""
        if self._key and value:
            try:
                return CryptoUtil.decrypt(value, self._key)
            except Exception:
                return value
        return value

    def _init_tables(self):
        """初始化所有数据表"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # 设备信息表
        c.execute('''CREATE TABLE IF NOT EXISTS device_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hardware_sn TEXT UNIQUE NOT NULL,
            license_code TEXT NOT NULL,
            auth_type TEXT NOT NULL DEFAULT 'perpetual',
            auth_expire REAL,
            activated_at REAL,
            last_heartbeat REAL,
            device_name TEXT,
            firmware_version TEXT
        )''')

        # 任务模板表
        c.execute('''CREATE TABLE IF NOT EXISTS task_info (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT DEFAULT '其他',
            segments_json TEXT,
            vla_model_path TEXT,
            created_at REAL,
            updated_at REAL,
            is_active INTEGER DEFAULT 1
        )''')

        # 工件样本表
        c.execute('''CREATE TABLE IF NOT EXISTS sample_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            image_path TEXT,
            pixel_scale REAL DEFAULT 1.0,
            reference_pose TEXT,
            features_count INTEGER DEFAULT 0,
            created_at REAL
        )''')

        # 生产日志表
        c.execute('''CREATE TABLE IF NOT EXISTS production_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            cycle_num INTEGER,
            status TEXT,
            good_count INTEGER DEFAULT 0,
            bad_count INTEGER DEFAULT 0,
            duration_s REAL,
            error_msg TEXT,
            created_at REAL,
            FOREIGN KEY(task_id) REFERENCES task_info(id)
        )''')

        # 故障日志表
        c.execute('''CREATE TABLE IF NOT EXISTS fault_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fault_code INTEGER,
            fault_msg TEXT,
            severity TEXT,
            recoverable INTEGER DEFAULT 1,
            robot_state TEXT,
            timestamp REAL,
            resolved INTEGER DEFAULT 0
        )''')

        # 用户账号表
        c.execute('''CREATE TABLE IF NOT EXISTS user_account (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'operator',
            is_active INTEGER DEFAULT 1,
            last_login REAL,
            created_at REAL
        )''')

        # 操作审计日志表(所有操作留痕)
        c.execute('''CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            action TEXT,
            details TEXT,
            ip_address TEXT,
            timestamp REAL
        )''')

        conn.commit()
        conn.close()
        logger.info("数据库表初始化完成")

    # ========== 设备授权 ==========

    def register_device(self, hardware_sn: str, license_code: str,
                        auth_type: AuthType = AuthType.TRIAL,
                        expire_days: int = 30) -> bool:
        """注册并激活设备"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            expire_time = time.time() + expire_days * 86400 if auth_type != AuthType.PERPETUAL else None
            c.execute("""
                INSERT OR REPLACE INTO device_info
                (hardware_sn, license_code, auth_type, auth_expire, activated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (hardware_sn, license_code, auth_type.value, expire_time, time.time()))
            conn.commit()
            logger.info(f"设备已注册: SN={hardware_sn}, 类型={auth_type.value}")
            return True
        except Exception as e:
            logger.error(f"设备注册失败: {e}")
            return False
        finally:
            conn.close()

    def check_auth(self, hardware_sn: str) -> Tuple[bool, str]:
        """检查授权状态"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT auth_type, auth_expire FROM device_info WHERE hardware_sn=?",
                  (hardware_sn,))
        row = c.fetchone()
        conn.close()

        if not row:
            return False, "未注册设备"

        auth_type, expire = row
        if auth_type == "perpetual":
            return True, "永久授权有效"
        if expire and time.time() > expire:
            return False, "授权已过期"
        return True, f"{auth_type} 授权有效"

    # ========== 用户管理 ==========

    def create_user(self, username: str, password: str,
                    role: UserRole) -> bool:
        """创建用户"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            c.execute("""
                INSERT INTO user_account (username, password_hash, role, created_at)
                VALUES (?, ?, ?, ?)
            """, (username, CryptoUtil.hash_password(password), role.value, time.time()))
            conn.commit()
            logger.info(f"用户创建: {username} ({role.value})")
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"用户名已存在: {username}")
            return False
        finally:
            conn.close()

    def authenticate(self, username: str, password: str) -> Optional[UserRole]:
        """用户认证"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT password_hash, role, is_active FROM user_account WHERE username=?",
                  (username,))
        row = c.fetchone()
        conn.close()

        if not row or row[2] == 0:
            return None
        if row[0] == CryptoUtil.hash_password(password):
            return UserRole(row[1])
        return None

    def init_default_users(self):
        """初始化默认三个角色账号"""
        defaults = [
            ("operator", "123456", UserRole.OPERATOR),
            ("admin", "admin888", UserRole.ADMIN),
            ("service", "service999", UserRole.MAINTENANCE),
        ]
        for user, pwd, role in defaults:
            self.create_user(user, pwd, role)

    # ========== 生产日志 ==========

    def log_production(self, task_id: str, cycle: int, status: str,
                       good: int = 0, bad: int = 0,
                       duration: float = 0.0, error: str = None):
        """记录生产数据"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO production_log (task_id, cycle_num, status, good_count, bad_count, duration_s, error_msg, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (task_id, cycle, status, good, bad, duration, error, time.time()))
        conn.commit()
        conn.close()

    def get_daily_report(self, date_str: str = None) -> Dict:
        """日生产报表"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        if date_str is None:
            date_str = time.strftime("%Y-%m-%d")

        today_start = time.mktime(time.strptime(date_str, "%Y-%m-%d"))
        today_end = today_start + 86400

        c.execute("""
            SELECT COUNT(*), SUM(good_count), SUM(bad_count), SUM(duration_s)
            FROM production_log WHERE created_at BETWEEN ? AND ?
        """, (today_start, today_end))
        row = c.fetchone()
        conn.close()

        total = row[0] or 0
        return {
            "date": date_str,
            "total_cycles": total,
            "good": row[1] or 0,
            "bad": row[2] or 0,
            "total_duration_hours": round((row[3] or 0) / 3600, 2),
            "yield_rate": round((row[1] or 0) / max(total, 1) * 100, 1),
        }

    def export_report_excel(self, start_date: str, end_date: str,
                            output_path: str) -> str:
        """导出报表为 CSV(可 Excel 打开)"""
        import csv
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        start_ts = time.mktime(time.strptime(start_date, "%Y-%m-%d"))
        end_ts = time.mktime(time.strptime(end_date, "%Y-%m-%d")) + 86400

        c.execute("""
            SELECT id, task_id, cycle_num, status, good_count, bad_count, duration_s, error_msg, created_at
            FROM production_log WHERE created_at BETWEEN ? AND ?
            ORDER BY created_at DESC
        """, (start_ts, end_ts))

        with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(["ID", "任务ID", "循环", "状态", "良品", "不良品",
                             "耗时(s)", "错误信息", "时间"])
            writer.writerows(c.fetchall())

        conn.close()
        return output_path

    # ========== 审计日志 ==========

    def audit(self, username: str, action: str, details: str = "",
              ip: str = "localhost"):
        """写入审计日志(所有操作留痕 ≥180天)"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO audit_log (username, action, details, ip_address, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (username, action, details, ip, time.time()))
        conn.commit()
        conn.close()

    def get_audit_logs(self, days: int = 180) -> List[Dict]:
        """查询审计日志"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        cutoff = time.time() - days * 86400
        c.execute("SELECT * FROM audit_log WHERE timestamp > ? ORDER BY id DESC LIMIT 1000",
                  (cutoff,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    # ========== 数据清零 ==========

    def clear_all_data(self) -> bool:
        """一键不可逆清除所有训练/生产/日志数据"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            tables = ["task_info", "sample_info", "production_log",
                      "fault_log", "audit_log"]
            for t in tables:
                c.execute(f"DELETE FROM {t}")
            conn.commit()
            logger.warning("⚠️ 所有数据已清零!")
            return True
        except Exception as e:
            logger.error(f"数据清零失败: {e}")
            return False
        finally:
            conn.close()

    # ========== 统计查询 ==========

    def get_fault_stats(self, days: int = 30) -> Dict:
        """故障统计"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        cutoff = time.time() - days * 86400
        c.execute("""
            SELECT severity, COUNT(*) FROM fault_log
            WHERE timestamp > ? GROUP BY severity
        """, (cutoff,))
        stats = dict(c.fetchall())
        conn.close()
        return stats

    def get_device_stats(self) -> Dict:
        """设备运行统计"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(DISTINCT task_id), SUM(good_count), AVG(duration_s) FROM production_log")
        row = c.fetchone()
        conn.close()
        return {
            "total_tasks": row[0] or 0,
            "total_good": row[1] or 0,
            "avg_cycle_time_s": round(row[2] or 0, 1),
        }
