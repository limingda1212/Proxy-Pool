# -*- coding: utf-8 -*-
# 中断文件处理

import os
import csv
import json
from typing import List, Tuple, Optional, Any
import sqlite3

from core.config import ConfigManager


class InterruptFileManager:
    def __init__(self, interrupt_dir: str, config: ConfigManager):
        self.interrupt_dir = interrupt_dir
        self.create_interrupt_dir()
        self.config = config

    # 创建中断目录
    def create_interrupt_dir(self) -> bool:
        """创建中断目录"""
        try:
            os.makedirs(self.interrupt_dir, exist_ok=True)
            return True
        except Exception as e:
            print(f"[error] 创建中断目录失败: {e}")
            return False

    # 保存中断时的代理列表
    def save_interrupted_proxies(self, remaining_proxies: List[str],
                                 type_or_config: Any, original_count: int,
                                 interrupt_file: str, from_browser: bool = False):
        """保存中断时的代理列表"""

        self.create_interrupt_dir()
        with open(interrupt_file, "w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            if from_browser:
                writer.writerow([json.dumps(type_or_config), original_count])
            else:
                writer.writerow([type_or_config, original_count])  # 第一行保存类型和原始数量
            for proxy in remaining_proxies:
                writer.writerow([proxy])

    # 加载中断的代理列表
    def load_interrupted_proxies(self, interrupt_file: str) -> Tuple[Optional[List[str]], Optional[Any], Optional[int]]:
        """加载中断的代理列表"""
        # 如果没有中断记录
        if not os.path.exists(interrupt_file):
            return None, None, None

        try:
            with open(interrupt_file, "r", encoding="utf-8") as file:
                reader = csv.reader(file)
                first_row = next(reader, None)
                # 如果无效
                if not first_row or len(first_row) < 2:
                    return None, None, None

                type_or_config = first_row[0]
                original_count = int(first_row[1])
                remaining_proxies = [row[0] for row in reader if row]
            # 有效并成功读取
            return remaining_proxies, type_or_config, original_count  # 剩余代理,类型,原始数量
        # 失败
        except:
            return None, None, None

    # 筛选中断记录中的代理，移除数据库中已不存在的代理
    def filter_interrupted_proxies(self, remaining_proxies, original_count) -> Tuple[list, int, int]:
        """
        筛选中断记录中的代理，移除数据库中已不存在的代理

        :param remaining_proxies: 中断记录中的代理列表
        :param original_count: 原始总数
        :return: (筛选后的代理列表, 有效代理数, 被筛除的代理数)
        """
        if not remaining_proxies:
            return [], 0, 0

        print(f"[info] 开始筛选中断记录中的代理...")
        print(f"  中断记录中的代理数: {len(remaining_proxies)}/{original_count}")

        # 从数据库加载现有代理
        existing_proxies = set()
        db_path = self.config.get("main.db_file","./data/proxies.db")

        if os.path.exists(db_path):
            conn = None
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT proxy FROM proxies WHERE score > 0")  # 只查询分数大于0的代理
                existing_proxies = {row[0].strip() for row in cursor.fetchall() if row[0]}
                print(f"[info] 数据库中现有有效代理数: {len(existing_proxies)}")
            except sqlite3.Error as e:
                print(f"[warning] 读取数据库代理失败: {e}")
            finally:
                if conn:
                    conn.close()
        else:
            print(f"[info] 数据库文件不存在，所有中断代理将被忽略")
            return [], 0, len(remaining_proxies)

        # 筛选代理
        valid_proxies = []
        removed_count = 0

        for proxy in remaining_proxies:
            if proxy in existing_proxies:
                valid_proxies.append(proxy)
            else:
                removed_count += 1
                print(f"[warning] 中断记录中的代理 {proxy} 已不存在于数据库，将被移除")

        # 更新原始数量
        new_original_count = original_count - removed_count

        print(f"[success] 中断记录筛选完成!")
        print(f"  有效代理数: {len(valid_proxies)}/{new_original_count}")
        print(f"  被筛除代理: {removed_count} 个")

        if removed_count > 0 and new_original_count <= 0:
            print("[warning] 中断记录中所有代理都已不存在，中断记录将被删除")
            return [], 0, removed_count

        return valid_proxies, new_original_count, removed_count

    # 检查是否有中断记录（会筛选已不存在的代理）
    def check_interrupted_records(self, interrupt_file: str):
        """
        检查是否有中断记录（会筛选已不存在的代理）

        y: 加载中断

        n: 删除中断

        其他: 返回上级菜单

        :return: from_interrupt(False/True), 剩余代理(remaining_proxies/"return"/None), 类型或配置(type_or_config/None), 原始数量(original_count/None)
        """
        remaining_proxies, type_or_config, original_count = self.load_interrupted_proxies(interrupt_file)
        if remaining_proxies:
            print(f"[info] 发现上次中断记录!")
            print(f"   剩余代理: {len(remaining_proxies)}/{original_count} 个")
            print(f"   验证参数: {type_or_config}")

            # 如果是验证已有代理或浏览器验证，需要筛选掉数据库中已不存在的代理
            if (type_or_config == "already_have") or (type_or_config.startswith("{") and type_or_config.endswith("}")):
                print("[info] 正在检查中断记录中的代理是否仍存在于数据库...")
                filtered_proxies, new_original_count, removed_count = self.filter_interrupted_proxies(
                    remaining_proxies, original_count
                )

                # 更新数据
                remaining_proxies = filtered_proxies
                original_count = new_original_count

                if removed_count > 0:
                    # 如果所有代理都被筛除，删除中断文件并返回
                    if not remaining_proxies:
                        print("[info] 中断记录中所有代理都已不存在，将删除中断文件")
                        self.delete_interrupt_file(interrupt_file)
                        return False, None, None, None

            print("\n[choice] 请输入:")
            print("  y: 使用上次记录")
            print("  n: 删除记录并继续")
            print("  其他: 返回上级菜单")

            choice = input("[input] 请选择 (y/n/其他): ").lower().strip()

            if choice == "y":
                print("[info] 使用上次记录...")
                from_interrupt = True
                return from_interrupt, remaining_proxies, type_or_config, original_count
            elif choice == "n":
                self.delete_interrupt_file(interrupt_file)
                print("[info] 已删除中断记录，重新开始...")
                from_interrupt = False
                return from_interrupt, None, None, None
            else:
                print("[info] 返回上级菜单")
                return False, "return", None, None
        else:
            from_interrupt = False
            return from_interrupt, None, None, None

    # 删除中断文件
    def delete_interrupt_file(self,interrupt_file):
        """删除中断文件"""
        if os.path.exists(interrupt_file):
            os.remove(interrupt_file)
