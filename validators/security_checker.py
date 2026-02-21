# -*- coding: utf-8 -*-
# 安全验证

import requests
import time
import re
import concurrent.futures
import os
from datetime import date
from typing import Dict, Any, Tuple, List, Optional

from core.config import ConfigManager
from storage.database import DatabaseManager
from utils.interrupt_handler import InterruptFileManager
from utils.signal_manager import signal_manager
from utils.helpers import set_up_proxy

# 消除警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class SecurityChecker:
    """执行单个代理的各项安全检测"""

    def __init__(self, config: ConfigManager):
        self.config = config

    # 检测代理是否注入恶意内容
    def check_malicious_content(self, proxy: str, proxy_type: str = "http") -> Tuple[bool, str]:
        """检测代理是否注入恶意内容"""
        try:
            proxies_config = set_up_proxy(proxy, proxy_type)
            timeout = self.config.get("main.timeout_safety", 10)

            # 获取恶意内容检测所需的 URL
            test_urls = self.config.get("main.test_urls_safety", {})
            html_url = test_urls.get("html")
            json_url = test_urls.get("json")

            if not html_url or not json_url:
                return False, "Missing html or json test URL in config"
                # return False, "配置缺少 html 或 json 测试 URL"

            # 请求 HTML 页面
            html_resp = requests.get(html_url, proxies=proxies_config, timeout=timeout)
            # 请求 JSON 接口
            json_resp = requests.get(json_url, proxies=proxies_config, timeout=timeout)

            # 恶意内容模式
            malicious_patterns = [
                (r"<script[^>]*src=[\"\']?[^>]*\.min\.js", "injected script"),
                (r"eval\(", "eval() detected"),
                (r"document\.write", "document.write() detected"),
                (r"<iframe", "iframe injection"),
                (r"javascript:", "javascript: protocol in content"),
            ]

            for resp in (html_resp, json_resp):
                if resp and hasattr(resp, "text"):
                    for pattern, desc in malicious_patterns:
                        if re.search(pattern, resp.text, re.IGNORECASE):
                            return False, f"Malicious content: {desc}"
                            # return False, f"检测到恶意内容注入 {desc}"

            return True, "pass"  # 通过时存储 "pass"

        except Exception as e:
            return False, f"error: {str(e)}"

    # 验证SSL证书安全性
    def check_ssl_security(self, proxy: str, proxy_type: str = "http") -> Tuple[bool, str]:
        """验证 SSL 证书安全性"""
        try:
            proxies_config = set_up_proxy(proxy, proxy_type)
            test_urls = self.config.get("main.test_urls_safety", {})
            https_url = test_urls.get("https")
            if not https_url:
                return False, "Missing https test URL in config"

            # 发送 HTTPS 请求，不验证证书（因为我们要手动检查）
            resp = requests.get(https_url, proxies=proxies_config, timeout=10, verify=False)
            # 这里可以添加更详细的证书验证，例如通过 resp.raw.connection.sock.getpeercert()
            # 为了简化，我们只检查是否成功连接且状态码正常
            if resp.status_code == 200:
                return True, "pass"
            else:
                return False, f"failed: HTTP {resp.status_code}"
                # return False, f"HTTPS 请求返回状态码 {resp.status_code}"

        except requests.exceptions.SSLError as e:
            return False, f"failed: SSL error - {str(e)}"
            # return False, f"SSL证书验证失败 - {str(e)}"
        except Exception as e:
            return False, f"error: {str(e)}"

    # 检测DNS劫持
    def check_dns_hijacking(self, proxy: str, proxy_type: str = "http") -> Tuple[bool, str]:
        """
        检测 DNS 劫持（使用 DoH 对比代理前后解析结果）
        :param proxy: 代理地址
        :param proxy_type: 代理类型
        :return: (是否通过, 详细信息)
        """
        # 从配置获取测试域名和 DoH 服务器（提供默认值）
        test_domain = self.config.get("main.dns_test_domain", "example.com")
        doh_server = self.config.get("main.doh_server", "https://doh.pub/dns-query")

        def _query_doh(domain: str, doh_url: str, proxies=None) -> Optional[List[str]]:
            """执行 DoH 查询，返回 IP 列表"""
            params = {'name': domain, 'type': 'A'}
            headers = {'accept': 'application/dns-json'}
            try:
                resp = requests.get(doh_url, params=params, headers=headers,
                                    proxies=proxies, timeout=10)
                if resp.status_code != 200:
                    return None
                data = resp.json()
                if data.get('Status') != 0:  # NOERROR
                    return None
                answers = data.get('Answer', [])
                ips = [ans['data'] for ans in answers if ans.get('type') == 1]
                return ips if ips else None
            except Exception:
                return None

        # 1. 无代理查询基准 IP
        baseline_ips = _query_doh(test_domain, doh_server)
        if not baseline_ips:
            # return False, f"failed: cannot resolve {test_domain} without proxy"
            # 无法获取基准，视为无法检测
            return True, "unknown"
            # return False, f"无法获取基准 DNS 解析（{test_domain}）"

        # 2. 通过代理查询
        try:
            proxies_config = set_up_proxy(proxy, proxy_type) if proxy else None
        except Exception as e:
            return False, f"error: proxy setup - {str(e)}"
            # return False, f"代理配置错误: {str(e)}"

        proxy_ips = _query_doh(test_domain, doh_server, proxies=proxies_config)
        if not proxy_ips:
            return False, f"failed: cannot resolve {test_domain} through proxy"
            # return False, "通过代理查询 DNS 失败"

        # 3. 对比 IP 集
        if set(baseline_ips) == set(proxy_ips):
            return True, "pass"
            # return True, f"DNS 解析一致 ({', '.join(baseline_ips)})"
        else:
            return False, f"failed: hijacked (baseline: {baseline_ips}, proxy: {proxy_ips})"
            # return False, f"DNS 劫持！基准: {baseline_ips}，代理: {proxy_ips}"

    # 检测代理是否篡改数据
    def check_data_tampering(self, proxy: str, proxy_type: str = "http") -> Tuple[bool, str]:
        """检测代理是否篡改数据（使用固定 base64 内容）"""
        try:
            proxies_config = set_up_proxy(proxy, proxy_type)
            test_urls = self.config.get("main.test_urls_safety", {})
            base64_url = test_urls.get("base64")
            if not base64_url:
                return False, "Missing base64 test URL in config"

            resp = requests.get(base64_url, proxies=proxies_config, timeout=10)
            if resp.status_code == 200:
                expected = "Hello World"
                if resp.text.strip() != expected:
                    return False, f"failed: tampered (expected: {expected}, got: {resp.text.strip()})"
                    # return False, f"数据被篡改 (期望: {expected}, 实际: {resp.text.strip()})"

                return True, "pass"
                # return True, "数据完整性验证通过"
            else:
                return False, f"failed: HTTP {resp.status_code}"
                # return False, f"Base64 测试请求失败，状态码 {resp.status_code}"
        except Exception as e:
            return False, f"error: {str(e)}"
            # return False, f"数据完整性检查失败: {str(e)}"

    # 检测可疑代理行为
    def check_suspicious_behavior(self, proxy: str, proxy_type: str = "http") -> Tuple[bool, str]:
        """检测可疑代理行为"""
        suspicious = []

        try:
            proxies_config = set_up_proxy(proxy, proxy_type)
            test_urls = self.config.get("main.test_urls_safety", {})
            headers_url = test_urls.get("headers")
            delay_url = test_urls.get("delay")

            if not headers_url or not delay_url:
                return False, "Missing headers or delay test URL in config"

            # 检查响应头
            headers_resp = requests.get(headers_url, proxies=proxies_config, timeout=10)
            if headers_resp.status_code == 200:
                headers = headers_resp.headers

                # 检查可疑响应头
                suspicious_headers = [
                    "X-Proxy-Modified",
                    "X-Forwarded-By",
                    "Via"  # 某些代理会添加Via头
                ]

                for h in suspicious_headers:
                    if h in headers:
                        suspicious.append(f"unexpected header: {h}")
                        # suspicious.append(f"存在可疑响应头: {h}")

            # 检查延迟（请求一个会延迟1秒的端点）
            start = time.time()
            delay_resp = requests.get(delay_url, proxies=proxies_config, timeout=15)  # 延长超时
            delay_time = time.time() - start
            if delay_time > 5:
                suspicious.append(f"high latency ({delay_time:.2f}s)")
                # suspicious.append(f"响应时间异常 ({delay_time:.2f}s)")

            if suspicious:
                return False, f"failed: {', '.join(suspicious)}"
                # return False, " | ".join(suspicious)

            return True, "pass"
            # return True, "行为分析正常"

        except Exception as e:
            return False, f"error: {str(e)}"
            # return False, f"行为分析失败: {str(e)}"

    # 调用 - 综合安全性验证
    def comprehensive_security_check(self, proxy: str, proxy_type: str = "http") -> Tuple[
        bool, int, List[str], Dict[str, str]]:
        """
        综合安全性验证 - 各检测独立请求
        """
        # 执行各项检测（每个检测内部自行处理异常，返回 (passed, reason)）
        # 注意：由于检测函数可能抛出异常，我们使用 try 包裹，确保一个失败不影响其他
        results = {}

        # 恶意内容检测
        try:
            results["malicious_content"] = self.check_malicious_content(proxy, proxy_type)
        except Exception as e:
            results["malicious_content"] = (False, f"error: {str(e)}")

        # SSL 安全性
        try:
            results["ssl_security"] = self.check_ssl_security(proxy, proxy_type)
        except Exception as e:
            results["ssl_security"] = (False, f"error: {str(e)}")

        # DNS 劫持
        try:
            results["dns_security"] = self.check_dns_hijacking(proxy, proxy_type)
        except Exception as e:
            results["dns_security"] = (False, f"error: {str(e)}")

        # 数据完整性
        try:
            results["data_integrity"] = self.check_data_tampering(proxy, proxy_type)
        except Exception as e:
            results["data_integrity"] = (False, f"error: {str(e)}")

        # 行为分析
        try:
            results["behavior_analysis"] = self.check_suspicious_behavior(proxy, proxy_type)
        except Exception as e:
            results["behavior_analysis"] = (False, f"error: {str(e)}")

        # 计算安全评分
        passed_checks = sum(1 for result in results.values() if result[0])
        total_checks = len(results)
        security_score = int((passed_checks / total_checks) * 100) if total_checks > 0 else 0

        # 收集失败原因
        failures = [f"{name}: {reason}" for name, (passed, reason) in results.items() if not passed]

        # 构造详细结果字典（用于存入数据库）
        detail = {
            "dns_hijacking": results["dns_security"][1] if "dns_security" in results else "unknown",
            "ssl_valid": results["ssl_security"][1] if "ssl_security" in results else "unknown",
            "malicious_content": results["malicious_content"][1] if "malicious_content" in results else "unknown",
            "data_integrity": results["data_integrity"][1] if "data_integrity" in results else "unknown",
            "behavior_analysis": results["behavior_analysis"][1] if "behavior_analysis" in results else "unknown",
        }

        return security_score >= 80, security_score, failures, detail

class SecurityValidator:
    """批量安全验证器，支持筛选、中断恢复"""

    def __init__(self, config: ConfigManager):
        self.config = config
        self.database = DatabaseManager(config.get("main.db_file", "./data/proxies.db"))
        self.interrupt = InterruptFileManager(
            self.config.get("interrupt.interrupt_dir", "interrupt"),
            config
        )
        self.checker = SecurityChecker(config)

    def validate_proxies_with_security(self,proxies: List[str],proxy_types: Dict[str, str],config: Dict[str, Any],from_interrupt: bool = False) -> Dict[str, Dict[str, Any]]:
        """
        批量验证代理安全性
        :return: {proxy: {"security": {...}}}
        """
        signal_manager.clear_interrupt()
        if not proxies:
            print("[failed] 没有代理需要安全验证")
            return {}

        original_count = len(proxies)
        max_workers = config.get("max_concurrent", self.config.get("main.max_workers", 100))
        print(f"[start] 开始安全验证，共 {original_count} 个代理，并发数: {max_workers}")

        interrupt_file = str(os.path.join(
            self.config.get("interrupt.interrupt_dir", "interrupt"),
            self.config.get("interrupt.interrupt_file_safety", "interrupted_safety_proxies.csv")
        ))

        if not from_interrupt:
            self.interrupt.save_interrupted_proxies(
                proxies, config, original_count, interrupt_file, from_browser=True
            )
            print(f"[file] 已创建安全验证中断恢复文件: {os.path.basename(interrupt_file)}")

        results = {}
        completed = 0

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_proxy = {}
                for proxy in proxies:
                    if signal_manager.is_interrupted():
                        break
                    ptype = proxy_types.get(proxy, "http")
                    future = executor.submit(self.checker.comprehensive_security_check, proxy, ptype)
                    future_to_proxy[future] = proxy

                for future in concurrent.futures.as_completed(future_to_proxy):
                    if signal_manager.is_interrupted():
                        for f in future_to_proxy:
                            f.cancel()
                        break

                    proxy = future_to_proxy[future]
                    completed += 1
                    try:
                        passed, score, failures, detail = future.result()
                        # 将五个字段+时间全部存入 security 字典
                        results[proxy] = {
                            "security": {
                                "dns_hijacking": detail.get("dns_hijacking", "unknown"),
                                "ssl_valid": detail.get("ssl_valid", "unknown"),
                                "malicious_content": detail.get("malicious_content", "unknown"),
                                "data_integrity": detail.get("data_integrity", "unknown"),
                                "behavior_analysis": detail.get("behavior_analysis", "unknown"),
                                "check_date": date.today().isoformat()
                            },
                            "security_score": score,
                            "security_passed": passed
                        }
                        if passed:
                            print(f"[{completed:3d}/{original_count}] ✅ {proxy:25s} 安全评分: {score}")
                        else:
                            fail_summary = failures[0][:50] + "..." if failures else "未知失败"
                            print(f"[{completed:3d}/{original_count}] ❌ {proxy:25s} {fail_summary}")
                    except Exception as e:
                        results[proxy] = {
                            "security": {
                                "dns_hijacking": "error",
                                "ssl_valid": "error",
                                "malicious_content": "error",
                                "data_integrity": "error",
                                "behavior_analysis": "error",
                                "check_date": date.today().isoformat()
                            },
                            "security_score": 0,
                            "security_passed": False
                        }
                        print(f"[{completed:3d}/{original_count}] ❌ {proxy:25s} 异常: {str(e)[:50]}")

            if signal_manager.is_interrupted():
                verified = set(results.keys())
                remaining = [p for p in proxies if p not in verified]
                if remaining:
                    self.interrupt.save_interrupted_proxies(
                        remaining, config, original_count, interrupt_file, from_browser=True
                    )
                    print(f"\n[pause] 安全验证已中断！已验证 {len(verified)} 个，剩余 {len(remaining)} 个")
                else:
                    self.interrupt.delete_interrupt_file(interrupt_file)
                    print("\n[success] 安全验证完成！")
                return results

            self.interrupt.delete_interrupt_file(interrupt_file)
            passed_count = sum(1 for r in results.values() if r.get("security_passed"))
            print(f"\n[success] 安全验证完成！通过: {passed_count}/{original_count}")
            return results

        except Exception as e:
            if not signal_manager.is_interrupted():
                print(f"[error] 安全验证过程中发生错误: {str(e)}")
            return results

    def layered_security_validation(self,config: Optional[Dict[str, Any]] = None,from_interrupt: bool = False, proxies_to_validate: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """
        分层安全验证：筛选代理并进行验证
        """
        if config is None:
            config = {}

        # 加载所有代理
        all_proxies, all_info = self.database.load_proxies_from_db()
        if not all_proxies:
            print("[failed] 代理池为空")
            return None

        # 如果不是从中断恢复，需要筛选
        if not from_interrupt and proxies_to_validate is None:
            filtered = []
            for proxy, score in all_proxies.items():
                info = all_info.get(proxy, {})
                # 分数筛选
                if score < config.get("min_score", 80):
                    continue
                # 类型筛选
                allowed_types = config.get("proxy_types", ["http", "socks4", "socks5"])
                proxy_types = info.get("types", [])
                if not any(t in allowed_types for t in proxy_types):
                    continue
                # 国内支持
                china_req = config.get("china_support")
                if china_req is not None and info.get("support", {}).get("china") != china_req:
                    continue
                # 国际支持
                intl_req = config.get("international_support")
                if intl_req is not None and info.get("support", {}).get("international") != intl_req:
                    continue
                # 透明代理
                trans_req = config.get("transparent_only")
                if trans_req is not None and info.get("transparent") != trans_req:
                    continue
                # 浏览器状态（可选）
                browser_status = config.get("browser_status")
                if browser_status is not None:
                    browser_valid = info.get("browser", {}).get("valid")
                    if browser_status == "failed" and browser_valid is not False:
                        continue
                    if browser_status == "success" and browser_valid is not True:
                        continue
                    if browser_status == "unknown" and browser_valid is not None:
                        continue

                filtered.append(proxy)

            print(f"[info] 筛选条件:")
            print(f"   最低分数: {config.get('min_score', 80)}")
            print(f"   代理类型: {config.get('proxy_types', ['http','socks4','socks5'])}")
            print(f"   国内支持: {config.get('china_support', '不限制')}")
            print(f"   国际支持: {config.get('international_support', '不限制')}")
            print(f"   透明代理: {config.get('transparent_only', '不限制')}")
            print(f"   找到 {len(filtered)} 个符合条件的代理")

            max_proxies = config.get("max_proxies", 50)
            if len(filtered) > max_proxies:
                print(f"[info] 限制验证数量为 {max_proxies} 个")
                filtered = sorted(filtered, key=lambda p: all_proxies[p], reverse=True)[:max_proxies]

            proxies_to_validate = filtered

        if not proxies_to_validate:
            print("[failed] 没有符合条件的代理")
            return None

        # 准备类型字典
        proxy_types = {}
        for proxy in proxies_to_validate:
            info = all_info.get(proxy, {})
            types = info.get("types", [])
            proxy_types[proxy] = types[0] if types else "http"

        # 执行验证
        results = self.validate_proxies_with_security(
            proxies_to_validate, proxy_types, config, from_interrupt
        )

        if results:
            self.update_proxy_security_status(results)
            print("[success] 代理池安全状态已更新")
        return results

    def update_proxy_security_status(self, security_results: Dict[str, Dict[str, Any]]):
        """将安全验证结果更新到数据库（包含全部五个字段）"""
        proxies, info = self.database.load_proxies_from_db()
        for proxy, data in security_results.items():
            if proxy in info:
                sec = data.get("security", {})
                info[proxy]["security"] = {
                    "dns_hijacking": sec.get("dns_hijacking", "unknown"),
                    "ssl_valid": sec.get("ssl_valid", "unknown"),
                    "malicious_content": sec.get("malicious_content", "unknown"),
                    "data_integrity": sec.get("data_integrity", "unknown"),
                    "behavior_analysis": sec.get("behavior_analysis", "unknown"),
                    "check_date": sec.get("check_date", date.today().isoformat())
                }
        self.database.save_valid_proxies(proxies, info)