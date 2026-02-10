# -*- coding: utf-8 -*-
# 文件加载

import os
import csv

from utils.helpers import filter_proxies
from validators.base_validator import BaseValidator
from core.config import ConfigManager


class LoadFile:
    def __init__(self, config: ConfigManager):
        self.base_validator = BaseValidator(config)

    def load(self):

        try:
            filename = input('[input] 文件名(路径): ')
            if not os.path.exists(filename):
                print("[failed] 文件不存在")
                return None, None

            # 选择代理类型
            print("\n[choice] 选择代理类型:")
            print("1. http/https")
            print("2. socks4")
            print("3. socks5")
            print("4. 自动检测")
            print("输入其他: 使用默认值http")
            type_choice = input("[input] 请选择(1-4): ").strip()

            type_map = {
                "1": "http",
                "2": "socks4",
                "3": "socks5",
                "4": "auto"
            }

            selected_type = type_map.get(type_choice, "http")
            print(f"[input] 使用类型: {selected_type}")

            data = []
            with open(filename, 'r', encoding='utf-8') as file:
                reader = csv.reader(file)
                for row in reader:
                    if len(row) >= 2:
                        # 支持 ip,port 格式
                        ip = row[0].strip()
                        port = row[1].strip()
                        if ip and port:
                            data.append(f"{ip}:{port}")
                    elif len(row) == 1 and ':' in row[0]:
                        # 支持 ip:port 格式
                        data.append(row[0].strip())

            if not data:
                print("[failed] 文件中没有找到有效的代理")
                return None, None

            print(f"[info] 从文件加载了 {len(data)} 个代理")

            # 与当前代理池比较,筛选去重
            return filter_proxies(data), selected_type

        except Exception as e:
            print(f'[error] 出错了: {str(e)}')
