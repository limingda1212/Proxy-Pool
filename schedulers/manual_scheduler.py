# -*- coding: utf-8 -*-
from typing import List, Dict, Any, Optional
from core.config import ConfigManager
from storage.database import DatabaseManager


class ManualScheduler:
    def __init__(self, config: ConfigManager, database: DatabaseManager):
        self.config = config
        self.database = database

    def extract_proxies_by_type(self, num: int, proxy_type: str = "all",
                                china_support: bool = None, international_support: bool = None,
                                transparent_only: bool = None, browser_only: bool = None,
                                min_security_passed: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        按类型、支持范围、透明代理、浏览器可用性和安全通过数量提取指定数量的代理，优先提取分高的
        """
        proxies, proxy_info = self.database.load_proxies_from_db()

        filtered_proxies = []  # 存储 (score, proxy, info, passed_count)
        for proxy, score in proxies.items():
            info = proxy_info.get(proxy, {})

            # 类型筛选
            if proxy_type != "all":
                proxy_types = info.get("types", [])
                if proxy_type not in proxy_types:
                    continue

            # 支持范围筛选
            support = info.get("support", {})
            if china_support is not None and support.get("china", False) != china_support:
                continue
            if international_support is not None and support.get("international", False) != international_support:
                continue

            # 透明代理筛选
            if transparent_only is not None and info.get("transparent", False) != transparent_only:
                continue

            # 浏览器可用筛选
            if browser_only is not None:
                browser_valid = info.get("browser", {}).get("valid", False)
                if browser_valid != browser_only:
                    continue

            # 计算安全通过数量（始终计算，便于后续返回）
            security = info.get("security", {})
            security_keys = ["dns_hijacking", "ssl_valid", "malicious_content", "data_integrity", "behavior_analysis"]
            passed_count = sum(1 for key in security_keys if security.get(key) == "pass")

            # 安全通过数量筛选
            if min_security_passed is not None and passed_count < min_security_passed:
                continue

            filtered_proxies.append((score, proxy, info, passed_count))

        # 按分数降序排序
        filtered_proxies.sort(key=lambda x: x[0], reverse=True)

        result = []
        for score, proxy, info, passed in filtered_proxies[:num]:
            actual_type = info.get("types", ["http"])[0] if info.get("types") else "http"
            china = info.get("support", {}).get("china", False)
            international = info.get("support", {}).get("international", False)
            transparent = info.get("transparent", False)
            browser_valid = info.get("browser", {}).get("valid", False)

            item = {
                "proxy": f"{actual_type}://{proxy}",
                "score": score,
                "china": china,
                "international": international,
                "transparent": transparent,
                "browser_valid": browser_valid,
                "security_passed": passed  # 新增字段
            }
            result.append(item)

        return result

