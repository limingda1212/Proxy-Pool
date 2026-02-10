# -*- coding: utf-8 -*-
from typing import List, Dict, Any
from core.config import ConfigManager
from storage.database import DatabaseManager


class ManualScheduler:
    def __init__(self, config: ConfigManager, database: DatabaseManager):
        self.config = config
        self.database = database

    def extract_proxies_by_type(self, num: int, proxy_type: str = "all",
                                china_support: bool = None, international_support: bool = None,
                                transparent_only: bool = None, browser_only: bool = None) -> List[Dict[str, Any]]:
        """
        按类型和支持范围提取指定数量的代理，优先提取分高的
        """
        proxies, proxy_info = self.database.load_proxies_from_db()

        # 按类型,支持范围,透明代理,浏览器可用筛选
        filtered_proxies = {}
        for proxy, score in proxies.items():
            info = proxy_info.get(proxy, {})

            # 类型筛选
            if proxy_type != "all":
                proxy_types = info.get("types", [])
                if proxy_type not in proxy_types:
                    continue

            # 中国支持筛选
            if china_support is not None and info.get("support", {}).get("china", False) != china_support:
                continue

            # 国际支持筛选
            if international_support is not None and info.get("support", {}).get("international",False) != international_support:
                continue

            # 透明代理筛选
            if transparent_only is not None and info.get("transparent", False) != transparent_only:
                continue

            # 浏览器可用筛选
            if browser_only is not None:
                browser_status = info.get("browser", {}).get("valid", False)
                if browser_status != browser_only:
                    continue

            filtered_proxies[proxy] = score

        # 按分数降序排序
        sorted_proxies = sorted(filtered_proxies.items(), key=lambda x: x[1], reverse=True)

        result = []
        for proxy, score in sorted_proxies:
            if len(result) >= num:
                break
            info = proxy_info.get(proxy, {})
            actual_type = info.get("types", ["http"])[0] if info.get("types") else "http"
            china = info.get("support", {}).get("china", False)
            international = info.get("support", {}).get("international", False)
            transparent = info.get("transparent", False)
            browser_valid = info.get("browser", {}).get("valid", False)

            result.append({
                "proxy": f"{actual_type}://{proxy}",
                "score": score,
                "china": china,
                "international": international,
                "transparent": transparent,
                "browser_valid": browser_valid
            })

        return result

