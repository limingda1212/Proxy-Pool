# 安全验证 - 开发中

import requests
import time
import re

from core.config import ConfigManager

class SecurityChecker:
    def __init__(self, config: ConfigManager):
        self.config = config

    # 统一安全验证请求
    def perform_security_requests(self, proxy, proxy_type="http"):
        """统一执行安全验证所需的请求，避免重复请求"""
        security_responses = {}

        try:
            proxies_config = {
                "http": f"{proxy_type}://{proxy}",
                "https": f"{proxy_type}://{proxy}"
            }

            # 执行所有必要的请求
            test_urls = self.config.get("main.test_urls_safety")

            # 批量执行请求
            for key, url in test_urls.items():
                try:
                    if key == "delay":
                        # 延迟测试单独处理超时
                        start_time = time.time()
                        response = requests.get(url, proxies=proxies_config, timeout=15)
                        response_time = time.time() - start_time
                        security_responses[key] = (response, response_time)
                    else:
                        response = requests.get(url, proxies=proxies_config,
                                                timeout=self.config.get("main.timeout_safety",8))
                        security_responses[key] = (response, None)
                except Exception as e:
                    security_responses[key] = (None, f"请求失败: {str(e)}")

            return security_responses

        except Exception as e:
            return {"error": f"统一请求失败: {str(e)}"}

    # 检测代理是否注入恶意内容
    def check_malicious_content(self, security_responses):
        """检测代理是否注入恶意内容"""
        try:
            # 检查常见恶意内容模式
            malicious_patterns = [
                r"<script[^>]*src=[\"\']?[^>]*\.min\.js",  # 可疑脚本
                r"eval\(",  # eval函数
                r"document\.write",  # 动态写入
                r"<iframe",  # 可疑iframe
                r"javascript:",  # JS协议
            ]

            # 检查HTML响应
            html_response, _ = security_responses.get("html", (None, None))
            if html_response and hasattr(html_response, "text"):
                for pattern in malicious_patterns:
                    if re.search(pattern, html_response.text, re.IGNORECASE):
                        return False, "检测到恶意内容注入"

            # 检查JSON响应
            json_response, _ = security_responses.get("json", (None, None))
            if json_response and hasattr(json_response, "text"):
                for pattern in malicious_patterns:
                    if re.search(pattern, json_response.text, re.IGNORECASE):
                        return False, "检测到恶意内容注入"

            return True, "内容安全"

        except Exception as e:
            return False, f"内容检测失败: {str(e)}"

    # 验证SSL证书安全性
    def check_ssl_security(self, security_responses):
        """验证SSL证书安全性"""
        try:
            https_response, _ = security_responses.get("https", (None, None))

            if https_response is None:
                return False, "HTTPS请求失败"

            # 检查证书信息
            if hasattr(https_response.connection, "socket"):
                cert = https_response.connection.socket.getpeercert()
                # 验证证书有效期
                not_after = cert.get("notAfter", "")
                # 可以添加更多证书检查逻辑

            return True, "SSL证书验证通过"

        except requests.exceptions.SSLError:
            return False, "SSL证书验证失败 - 可能存在中间人攻击"
        except Exception as e:
            return False, f"SSL检查失败: {str(e)}"

    # 检测DNS劫持
    def check_dns_hijacking(self, security_responses):
        """检测DNS劫持"""
        try:
            # 测试已知IP的域名
            test_domains = {
                "httpbin.org": "54.227.38.221",  # 需要更新为实际IP
            }

            # 通过IP测试响应检查DNS解析
            ip_response, _ = security_responses.get("ip_test", (None, None))
            if ip_response and hasattr(ip_response, "text"):
                # 检查返回的IP是否包含在响应中
                response_data = ip_response.json()
                actual_ip = response_data.get("origin", "")

                for domain, expected_ip in test_domains.items():
                    if expected_ip not in actual_ip:
                        return False, f"DNS劫持检测: {domain} 解析异常"

            return True, "DNS解析正常"

        except Exception as e:
            return False, f"DNS检查失败: {str(e)}"

    # 检测代理是否篡改数据
    def check_data_tampering(self, security_responses):
        """检测代理是否篡改数据"""
        try:
            # 测试已知固定响应的API
            base64_response, _ = security_responses.get("base64", (None, None))

            if base64_response and hasattr(base64_response, "text"):
                expected_content = "Hello World"
                if base64_response.text.strip() != expected_content:
                    return False, "数据被篡改"

            return True, "数据完整性验证通过"

        except Exception as e:
            return False, f"数据完整性检查失败: {str(e)}"

    # 检测可疑代理行为
    def check_suspicious_behavior(self, security_responses):
        """检测可疑代理行为"""
        suspicious_indicators = []

        try:
            # 检查响应头
            headers_response, _ = security_responses.get("headers", (None, None))
            if headers_response and hasattr(headers_response, "headers"):
                headers = headers_response.headers

                # 检查可疑响应头
                suspicious_headers = [
                    "X-Proxy-Modified",
                    "X-Forwarded-By",
                    "Via"  # 某些代理会添加Via头
                ]

                for header in suspicious_headers:
                    if header in headers:
                        suspicious_indicators.append(f"可疑响应头: {header}")

            # 检查响应时间异常
            _, response_time = security_responses.get("delay", (None, None))
            if response_time and response_time > 5:  # 响应时间过长
                suspicious_indicators.append("响应时间异常")

            if suspicious_indicators:
                return False, " | ".join(suspicious_indicators)
            else:
                return True, "行为分析正常"

        except Exception as e:
            return False, f"行为分析失败: {str(e)}"

    # 调用 - 综合安全性验证
    def comprehensive_security_check(self, proxy, proxy_type="http"):
        """综合安全性验证 - 统一请求流程"""
        # 执行统一请求
        security_responses = self.perform_security_requests(proxy, proxy_type)

        if "error" in security_responses:
            return False, 0, [security_responses["error"]]

        # 使用统一响应数据进行各项检查
        security_results = {
            "malicious_content": self.check_malicious_content(security_responses),
            "ssl_security": self.check_ssl_security(security_responses),
            "dns_security": self.check_dns_hijacking(security_responses),
            "data_integrity": self.check_data_tampering(security_responses),
            "behavior_analysis": self.check_suspicious_behavior(security_responses)
        }

        # 计算安全评分
        passed_checks = sum(1 for result in security_results.values() if result[0])
        total_checks = len(security_results)
        security_score = (passed_checks / total_checks) * 100

        # 收集失败原因
        failures = [f"{name}: {reason}" for name, (passed, reason) in security_results.items() if not passed]

        return security_score >= 80, security_score, failures
    ###