# -*- coding: utf-8 -*-

from core.config import ConfigManager
from storage.database import DatabaseManager


class PoolMonitor:
    def __init__(self, config: ConfigManager, database: DatabaseManager):
        self.config = config
        self.database = database

    # 显示代理池状态(按类型、分数、支持范围和透明代理等统计)
    def show_proxy_pool_status(self):
        """显示代理池状态"""
        proxies, proxy_info = self.database.load_proxies_from_db()
        total = len(proxies)

        if total == 0:
            print("[failed] 代理池为空")
            return

        # 获取每行显示的项目数
        items_per_row = self.config.get("main.number_of_items_per_row", 5)

        # 按类型分组
        type_groups = {}
        for proxy, score in proxies.items():
            info = proxy_info.get(proxy, {})
            proxy_types = info.get("types", ["unknown"])
            # 确保proxy_types是列表
            if not isinstance(proxy_types, list):
                print(f"[warning] 代理 {proxy} 的types字段不是列表: {proxy_types}")
                proxy_types = ["unknown"]
            for proxy_type in proxy_types:
                if proxy_type not in type_groups:
                    type_groups[proxy_type] = []
                type_groups[proxy_type].append((proxy, score, info))

        print(f"\n[info] 代理池状态 ({self.config.get('main.db_file','proxies.db')}):")
        print(f"总代理数量: {total}")
        print(f"每行显示项目数: {items_per_row}")

        # 支持范围统计
        china_only = 0
        intl_only = 0
        both_support = 0
        no_support = 0

        for proxy, info in proxy_info.items():
            support = info.get("support", {})
            china = support.get("china", False)
            international = support.get("international", False)

            if china and not international:
                china_only += 1
            elif not china and international:
                intl_only += 1
            elif china and international:
                both_support += 1
            else:
                no_support += 1

        # 透明代理统计
        transparent_count = sum(1 for info in proxy_info.values() if info.get("transparent", False))
        anonymous_count = total - transparent_count

        # 浏览器验证统计
        browser_valid_count = 0
        browser_invalid_count = 0
        browser_unknown_count = 0

        for info in proxy_info.values():
            browser = info.get("browser", {})
            if browser.get("valid") is True:
                browser_valid_count += 1
            elif browser.get("valid") is False:
                browser_invalid_count += 1
            else:
                browser_unknown_count += 1

        # 计算各列的最大宽度
        # 支持范围统计列
        support_items = [
            f"仅支持国内: {china_only}个",
            f"仅支持国际: {intl_only}个",
            f"支持国内外: {both_support}个",
            f"无支持(无效): {no_support}个"
        ]

        # 浏览器验证统计列
        browser_items = [
            f"验证成功: {browser_valid_count}个",
            f"验证失败/未验证: {browser_invalid_count + browser_unknown_count}个",
        ]

        # 透明代理统计列
        transparent_items = [
            f"透明代理: {transparent_count}个",
            f"匿名代理: {anonymous_count}个"
        ]

        # 计算每列的最大行数
        max_lines = max(len(support_items), len(browser_items), len(transparent_items))

        # 填充列表使它们具有相同的行数
        while len(support_items) < max_lines:
            support_items.append("")
        while len(browser_items) < max_lines:
            browser_items.append("")
        while len(transparent_items) < max_lines:
            transparent_items.append("")

        print("\n统计概览:")
        print("支持范围统计".ljust(30) + "浏览器验证统计".ljust(30) + "透明代理统计")
        print("-" * 90)

        # 并排打印三列
        for i in range(max_lines):
            # 每列固定宽度为30字符
            support_line = support_items[i].ljust(30)
            browser_line = browser_items[i].ljust(30)
            transparent_line = transparent_items[i]
            print(f"{support_line}{browser_line}{transparent_line}")

        # 按类型显示分数分布
        for proxy_type, proxy_list in type_groups.items():
            type_count = len(proxy_list)
            print(f"\n{proxy_type} 代理: {type_count}个")

            # 统计分数分布
            score_count = {}
            for _, score, _ in proxy_list:
                score_count[score] = score_count.get(score, 0) + 1

            # 按分数排序显示
            sorted_scores = sorted(score_count.items(), key=lambda x: x[0], reverse=True)

            # 按每行 items_per_row 个项目的格式显示
            for i in range(0, len(sorted_scores), items_per_row):
                # 获取当前行的项目
                row_items = sorted_scores[i:i + items_per_row]

                # 格式化每行的显示
                row_parts = []
                for score, count in row_items:
                    # 计算所需的间距，使对齐更美观
                    score_len = len(f"{score}")
                    count_len = len(f"{count}")
                    # 格式化字符串：左对齐分数，右对齐数量
                    row_parts.append(f"{score}分:{count:>{6 - score_len}}个")

                # 使用空格分隔，确保每行对齐
                print("  " + "    ".join(row_parts))

        print("=" * 40)
        print(f"总计: {total} 个代理")