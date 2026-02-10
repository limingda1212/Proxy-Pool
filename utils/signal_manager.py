# -*- coding: utf-8 -*-
# 统一的信号管理器，使用线程安全的Event处理中断

import signal
import threading
import logging
from typing import Callable

logger = logging.getLogger(__name__)


class SignalManager:
    """信号管理器（单例模式）"""

    # 类属性，确保全局只有一个实例
    _instance = None
    _interrupt_event = threading.Event()
    _cleanup_handlers = []
    _is_registered = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # 防止重复初始化
        if not hasattr(self, "_initialized"):
            self._initialized = True

    @classmethod
    def register(cls):
        """注册信号处理器（必须调用）"""
        if cls._is_registered:
            print("已经注册信号")
            return

        def signal_handler(signum, frame):
            """信号处理函数"""
            print(f"\n[signal] 接收到中断信号 {signum}，准备退出,请耐心等待...")
            cls._interrupt_event.set()

            # 执行清理函数
            for handler in cls._cleanup_handlers:
                try:
                    handler()
                except Exception as e:
                    print(f"[warning] 清理函数执行失败: {e}")

        # 注册常见的中断信号
        try:
            signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
            signal.signal(signal.SIGTERM, signal_handler)  # 终止信号
        except Exception as e:
            print(f"[warning] 信号注册失败: {e}")

        cls._is_registered = True
        print("[info] 中断信号处理器已注册")

    @classmethod
    def is_interrupted(cls) -> bool:
        """检查是否收到中断信号"""
        return cls._interrupt_event.is_set()

    @classmethod
    def wait_for_interrupt(cls, timeout: float = None):
        """等待中断信号"""
        return cls._interrupt_event.wait(timeout)

    @classmethod
    def clear_interrupt(cls):
        """清除中断状态（谨慎使用）"""
        cls._interrupt_event.clear()

    @classmethod
    def add_cleanup_handler(cls, handler: Callable):
        """添加清理函数"""
        cls._cleanup_handlers.append(handler)

    @classmethod
    def reset(cls):
        """重置（主要用于测试）"""
        cls._interrupt_event.clear()
        cls._cleanup_handlers.clear()
        cls._is_registered = False


# 创建全局实例（方便导入）
signal_manager = SignalManager()