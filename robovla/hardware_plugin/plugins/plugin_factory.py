"""
RoboVLA V2.0 - 机器人插件工厂

根据配置自动扫描、匹配并实例化对应品牌的机器人插件。
支持运行时动态加载新插件，无需重启。
"""

import logging
from typing import Dict, Optional, Type
import importlib

from hardware_plugin.robot_base import RobotBase
from hardware_plugin.plugins.aubo_plugin import AuboPlugin
from hardware_plugin.plugins.dobot_plugin import DobotPlugin

logger = logging.getLogger(__name__)


class RobotPluginFactory:
    """
    插件工厂 - 统一管理所有品牌插件

    使用方式:
        factory = RobotPluginFactory()
        robot = factory.scan_and_connect()  # 自动扫描局域网设备
        robot = factory.create("aubo", ip="192.168.1.100")
    """

    # 已注册的插件映射
    REGISTERED_PLUGINS: Dict[str, Type[RobotBase]] = {
        "aubo": AuboPlugin,
        "dobot": DobotPlugin,
        # 预留: "unitree": UnitreeDogPlugin,  # V2.1
    }

    # 品牌识别规则(IP/端口特征)
    BRAND_HEURISTICS = [
        ("aubo", lambda ip, port: port == 8899),
        ("dobot", lambda ip, port: port == 6000),
    ]

    def __init__(self):
        self._active_plugins: Dict[str, RobotBase] = {}

    def create(self, brand: str, ip: str = "192.168.1.100",
               port: int = 8899, **kwargs) -> Optional[RobotBase]:
        """
        创建指定品牌的机器人实例

        Args:
            brand: 品牌标识 ("aubo", "dobot")
            ip: 机器人IP地址
            port: 通信端口
            **kwargs: 品牌特有参数
        """
        brand_lower = brand.lower()
        if brand_lower not in self.REGISTERED_PLUGINS:
            logger.error(f"不支持的品牌: {brand}, 支持: {list(self.REGISTERED_PLUGINS.keys())}")
            return None

        plugin_cls = self.REGISTERED_PLUGINS[brand_lower]
        try:
            instance = plugin_cls(robot_ip=ip, port=port, **kwargs)
            self._active_plugins[brand_lower] = instance
            return instance
        except Exception as e:
            logger.error(f"创建 {brand} 插件失败: {e}")
            return None

    def scan_and_connect(self, subnet: str = "192.168.1",
                         ports: list = None) -> Dict[str, RobotBase]:
        """
        自动扫描局域网内的机器人设备并连接

        Args:
            subnet: 子网前缀 (e.g. "192.168.1")
            ports: 扫描端口列表
        Returns:
            {brand: RobotBase} 成功连接的设备字典
        """
        if ports is None:
            ports = [8899, 6000]

        logger.info(f"开始扫描局域网 {subnet}.0/24 ...")
        connected = {}

        for ip_end in range(1, 255):
            ip = f"{subnet}.{ip_end}"
            for port in ports:
                # 根据端口推测品牌
                for brand, heuristic in self.BRAND_HEURISTICS:
                    if heuristic(ip, port):
                        robot = self.create(brand, ip=ip, port=port)
                        if robot and robot.connect():
                            connected[brand] = robot
                            logger.info(f"✅ 发现并连接: {brand} @ {ip}:{port}")
                            break
        return connected

    def register_plugin(self, brand: str, plugin_cls: Type[RobotBase]):
        """
        动态注册新品牌插件(运行时扩展)

        Args:
            brand: 品牌标识字符串
            plugin_cls: 继承自 RobotBase 的插件类
        """
        if not issubclass(plugin_cls, RobotBase):
            raise TypeError(f"{plugin_cls} 必须继承 RobotBase")
        self.REGISTERED_PLUGINS[brand.lower()] = plugin_cls
        logger.info(f"已注册新插件: {brand} → {plugin_cls.__name__}")

    def get_active_plugins(self) -> Dict[str, RobotBase]:
        """获取所有已连接的设备"""
        return {
            k: v for k, v in self._active_plugins.items()
            if v.is_connected()
        }

    def disconnect_all(self):
        """断开所有设备"""
        for brand, robot in self._active_plugins.items():
            try:
                robot.disconnect()
            except Exception as e:
                logger.error(f"断开 {brand} 失败: {e}")
        self._active_plugins.clear()
