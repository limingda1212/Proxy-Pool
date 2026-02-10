# -*- coding: utf-8 -*-

import socket
import sqlite3
import os
from typing import List

from core.config import ConfigManager

def is_valid_ip(ip: str) -> bool:
    """验证IP地址格式是否有效"""
    try:
        socket.inet_pton(socket.AF_INET, ip)
        return True
    except socket.error:
        try:
            socket.inet_pton(socket.AF_INET6, ip)
            return True
        except socket.error:
            return False

def is_valid_proxy_format(proxy: str) -> bool:
    """
    验证代理格式是否有效

    :param proxy: 代理字符串 (ip:port)
    :return: 是否有效
    """
    # if not proxy or ":" not in proxy:
    if (not proxy) or (":" not in proxy) or (len(proxy) > 30) or (len(proxy) < 9):
        return False

    try:
        ip, port = proxy.split(":", 1)

        # 验证IP格式
        if not is_valid_ip(ip):
            return False

        # 验证端口格式
        port_num = int(port)
        if not (1 <= port_num <= 65535):
            return False

        return True

    except (ValueError, AttributeError):
        return False

def set_up_proxy(proxy, proxy_type="http"):
    r"""
    设置代理

    if proxy_type == "http":
        proxies_config = {
            "http": f"http://{proxy}",
            "https": f"http://{proxy}"
        }
    elif proxy_type == "socks4":
        proxies_config = {
            "http": f"socks4://{proxy}",
            "https": f"socks4://{proxy}"
        }
    elif proxy_type == "socks5":
        proxies_config = {
            "http": f"socks5://{proxy}",
            "https": f"socks5://{proxy}"
        }
    else:
        proxies_config = {
            "http": f"http://{proxy}",
            "https": f"http://{proxy}"
        }

    :param proxy: 代理地址
    :param proxy_type: 代理类型
    :return: proxy_ip_info
    """

    if proxy_type == "http":
        proxies_config = {
            "http": f"http://{proxy}",
            "https": f"http://{proxy}"
        }
    elif proxy_type == "socks4":
        proxies_config = {
            "http": f"socks4://{proxy}",
            "https": f"socks4://{proxy}"
        }
    elif proxy_type == "socks5":
        proxies_config = {
            "http": f"socks5://{proxy}",
            "https": f"socks5://{proxy}"
        }
    else:
        proxies_config = {
            "http": f"http://{proxy}",
            "https": f"http://{proxy}"
        }

    return proxies_config


def filter_proxies(all_proxies: List[str]) -> List[str]:
    """从新获取代理中去掉无效的、重复的"""
    """
        从新获取代理中去掉无效的、重复的（数据库版本）

        使用集合进行查找，时间复杂度O(1)

        :param all_proxies: 新代理列表
        :return: 筛选后的代理列表
        """
    if not all_proxies:
        print("[info] 没有代理需要筛选")
        return []

    print(f"[info] 开始筛选 {len(all_proxies)} 个代理...")

    # 加载现有代理池（从数据库读取，使用集合提高查找效率）
    existing_proxies_set = set()
    config = ConfigManager()
    db_path = config.load_config()["main"]["db_file"]   # 数据库文件路径
    # 从数据库查询已有代理
    if os.path.exists(db_path):
        conn = None
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            # 代理存储在proxies表的proxy字段中
            cursor.execute("SELECT proxy FROM proxies")
            # 提取所有代理字符串到集合
            existing_proxies_set = {row[0].strip() for row in cursor.fetchall() if row[0]}
            print(f"[info] 从数据库加载了 {len(existing_proxies_set)} 个已有代理")
        except sqlite3.Error as e:
            print(f"[warning] 读取数据库代理失败: {e}")
        finally:
            if conn:
                conn.close()  # 确保连接关闭
    else:
        print(f"[info] 数据库文件不存在，视为无已有代理")

    # 使用集合进行去重和验证
    seen_proxies = set()
    new_proxies_set = set()
    duplicate_count = 0
    invalid_count = 0
    format_error_count = 0

    for proxy in all_proxies:
        if not proxy or not isinstance(proxy, str):
            invalid_count += 1
            continue

        proxy = proxy.strip()

        # 检查当前批次内的重复
        if proxy in seen_proxies:
            duplicate_count += 1
            continue
        seen_proxies.add(proxy)

        # 验证代理格式（ip:port）
        if not is_valid_proxy_format(proxy):
            format_error_count += 1
            continue

        # 检查是否已存在于数据库中
        if proxy in existing_proxies_set:
            duplicate_count += 1
            continue

        # 检查是否在新代理集合中重复
        if proxy in new_proxies_set:
            duplicate_count += 1
            continue

        new_proxies_set.add(proxy)

    # 转换为列表返回
    new_proxies = list(new_proxies_set)

    print(f"[success] 筛选完成!")
    print(f"  有效新代理: {len(new_proxies)}")
    print(f"  重复代理: {duplicate_count}")
    print(f"  格式错误: {format_error_count}")
    print(f"  无效代理: {invalid_count}")

    return new_proxies