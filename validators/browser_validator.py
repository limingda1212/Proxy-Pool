# -*- coding: utf-8 -*-

from playwright.async_api import async_playwright, ProxySettings
import time
import asyncio
import os
import concurrent.futures
from datetime import date

from core.config import ConfigManager
from storage.database import DatabaseManager
from utils.interrupt_handler import InterruptFileManager
from utils.signal_manager import signal_manager

class BrowserValidator:
    def __init__(self, config: ConfigManager):
        self.config = config
        self.database = DatabaseManager(config.get("main.db_file", "./data/proxies.db"))
        self.interrupt = InterruptFileManager(self.config.get("main.interrupt_dir","interrupt"),config)

    # 使用Playwright验证单个代理的浏览器可用性
    def check_proxy_with_browser_single(self, proxy, proxy_type="http", test_url="https://httpbin.org/ip", timeout=15000):
        """
        使用Playwright验证单个代理的浏览器可用性
        返回: (是否成功, 错误信息, 响应时间ms)
        """

        async def _check():
            async with async_playwright() as p:
                browser = None
                try:
                    # 配置浏览器选项
                    browser_args = [
                        "--headless=new",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-web-security",
                        "--disable-features=VizDisplayCompositor",
                        "--disable-background-timer-throttling",
                        "--disable-backgrounding-occluded-windows",
                        "--disable-renderer-backgrounding"
                    ]

                    # 启动浏览器
                    browser = await p.chromium.launch(args=browser_args)

                    # 配置代理
                    proxy_config = ProxySettings(
                        server=f"{proxy_type}://{proxy}"
                    )

                    context = await browser.new_context(proxy=proxy_config)
                    page = await context.new_page()

                    # 设置超时
                    page.set_default_timeout(timeout)

                    # 开始计时
                    start_time = time.time()

                    # 访问测试页面
                    response = await page.goto(test_url, wait_until="domcontentloaded")

                    # 检查响应状态
                    if response.status != 200:
                        return False, f"状态码: {response.status}", None

                    # 获取页面内容验证
                    content = await page.content()
                    if "origin" not in content:
                        return False, "响应内容无效", None

                    # 计算响应时间
                    response_time = int((time.time() - start_time) * 1000)

                    return True, None, response_time

                except Exception as e:
                    return False, str(e), None
                finally:
                    if browser:
                        await browser.close()

        # 处理事件循环
        try:
            # 尝试获取现有事件循环
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # 如果没有事件循环，创建新的
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # 运行异步检查
        try:
            return loop.run_until_complete(_check())
        except Exception as e:
            return False, f"异步执行错误: {str(e)}", None

    # 批量验证代理的浏览器可用性
    def validate_proxies_with_browser(self, proxies, proxy_types, config, from_interrupt=False):
        """批量验证代理的浏览器可用性"""
        signal_manager.clear_interrupt()  # 清除中断状态

        if not proxies:
            print("[failed] 没有代理需要浏览器验证")
            return {}

        original_count = len(proxies)
        max_concurrent = config.get("max_concurrent", 3)
        test_url = self.config.get("main.test_url_browser","https://httpbin.org/ip")

        print(f"[start] 开始浏览器验证，共 {original_count} 个代理，并发数: {max_concurrent}")
        print("这可能需要一些时间，请耐心等待...")

        interrupt_file = str(os.path.join(self.config.get("interrupt.interrupt_dir","interrupt"),
                                      self.config.get("interrupt.interrupt_file_browser","interrupted_browser_proxies.csv"))
                             )
        # 保存中断文件（如果不是从中断恢复的）
        if not from_interrupt:
            self.interrupt.save_interrupted_proxies(proxies, config, original_count, interrupt_file=interrupt_file, from_browser=True)
            print(f"[file] 已创建浏览器验证中断恢复文件: {self.config.get('interrupt.interrupt_file_browser','interrupted_browser_proxies.csv')}")

        results = {}
        completed = 0

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as executor:
                future_to_proxy = {}

                for proxy in proxies:
                    if signal_manager.is_interrupted():
                        break

                    proxy_type = proxy_types.get(proxy, "http")
                    future = executor.submit(
                        self.check_proxy_with_browser_single,
                        proxy, proxy_type, test_url
                    )
                    future_to_proxy[future] = proxy

                for future in concurrent.futures.as_completed(future_to_proxy):
                    if signal_manager.is_interrupted():
                        # 取消所有未完成的任务
                        for f in future_to_proxy:
                            f.cancel()
                        break

                    proxy = future_to_proxy[future]
                    completed += 1

                    try:
                        success, error, response_time = future.result()

                        # 将错误信息压缩为单行
                        if success:
                            results[proxy] = {
                                "browser_valid": True,
                                "browser_check_date": date.today().isoformat(),
                                "browser_response_time": response_time
                            }
                            # 成功时显示响应时间，格式化为整数
                            time_ms = f"({int(response_time)}ms)" if response_time else ""
                            print(f"[{completed:3d}/{original_count}] ✅ {proxy:25s} {time_ms}")
                        else:
                            results[proxy] = {
                                "browser_valid": False,
                                "browser_check_date": date.today().isoformat(),
                                "browser_error": error
                            }
                            # 失败时提取关键错误信息，压缩到一行
                            error_summary = self.extract_error_summary(error)
                            print(f"[{completed:3d}/{original_count}] ❌ {proxy:25s} {error_summary}")

                    except Exception as e:
                        results[proxy] = {
                            "browser_valid": False,
                            "browser_check_date": date.today().isoformat(),
                            "browser_error": str(e)
                        }
                        error_msg = str(e)[:50] + "..." if len(str(e)) > 50 else str(e)
                        print(f"[{completed:3d}/{original_count}] ❌ {proxy:25s} 异常: {error_msg}")

            if signal_manager.is_interrupted():
                # 处理中断情况
                verified_proxies = set(results.keys())
                remaining_proxies = [proxy for proxy in proxies if proxy not in verified_proxies]

                if remaining_proxies:
                    self.interrupt.save_interrupted_proxies(remaining_proxies, config, original_count, interrupt_file=interrupt_file,
                                             from_browser=True)
                    print(
                        f"\n[pause] 浏览器验证已中断！已验证 {len(verified_proxies)} 个代理，剩余 {len(remaining_proxies)} 个代理待验证")
                    print(f"[file] 中断文件已更新: {self.config.get('interrupt.interrupt_file_browser','interrupted_browser_proxies.csv')}")
                else:
                    self.interrupt.delete_interrupt_file(interrupt_file)
                    print(f"\n[success] 浏览器验证完成！所有代理已验证")
                return results

            # 正常完成验证
            self.interrupt.delete_interrupt_file(interrupt_file)

            # 统计结果
            success_count = sum(1 for result in results.values() if result.get("browser_valid"))
            target_success = config.get("target_success")

            print(f"\n[end] 浏览器验证完成!")
            print(f"[success] 成功: {success_count}/{original_count}")

            if target_success:
                if success_count >= target_success:
                    print(f"[success] 达到目标成功数量: {success_count}/{target_success}")
                else:
                    print(f"[warning] 未达到目标成功数量: {success_count}/{target_success}")

            return results

        except Exception as e:
            if not signal_manager.is_interrupted():
                print(f"[error] 浏览器验证过程中发生错误: {str(e)}")
            return results

    # 从验证错误信息中提取关键部分，压缩为单行显示
    def extract_error_summary(self, error_message):
        """
        从错误信息中提取关键部分，压缩为单行显示
        """
        if not error_message:
            return "未知错误"

        # 如果错误信息是字符串，按换行分割
        if isinstance(error_message, str):
            lines = error_message.strip().split("\n")

            # 提取第一行关键错误
            for line in lines:
                line = line.strip()
                if line and "net::" in line:
                    # 提取 net:: 错误代码
                    if "at https://" in line:
                        # 类似: Page.goto: net::ERR_CONNECTION_RESET at https://httpbin.org/ip
                        # 只保留错误代码部分
                        parts = line.split("net::")
                        if len(parts) > 1:
                            error_part = parts[1].split(" at ")[0]
                            return f"net::{error_part}"
                    return line[:40] + "..." if len(line) > 40 else line

                if line and ("Page.goto:" in line or "navigation" in line):
                    # 截取关键部分
                    return line[:40] + "..." if len(line) > 40 else line

            # 如果没有找到特定错误，返回第一行
            first_line = lines[0] if lines else str(error_message)
            return first_line[:50] + "..." if len(first_line) > 50 else first_line

        return str(error_message)[:50] + "..." if len(str(error_message)) > 50 else str(error_message)

    # 分层浏览器验证 - 根据配置筛选代理并进行浏览器验证
    def layered_browser_validation(self, config=None, from_interrupt=False, proxies_to_validate=None):
        """
        分层浏览器验证
        """
        if config is None:
            config = {}

        # 如果未提供 proxies_to_validate，使用空列表
        if proxies_to_validate is None:
            proxies_to_validate = []

        # 加载代理池
        all_proxies, all_proxy_info = self.database.load_proxies_from_db()

        if not all_proxies:
            print("[failed] 代理池为空")
            return None

        # 如果不是从中断恢复，需要筛选代理
        if not from_interrupt:
            filtered_proxies = []
            for proxy, score in all_proxies.items():
                # 分数筛选
                min_score = config.get("min_score", 80)
                if score < min_score:
                    continue

                # 类型筛选
                allowed_types = config.get("proxy_types", ["http", "socks4", "socks5"])
                proxy_info = all_proxy_info.get(proxy, {})
                proxy_types_list = proxy_info.get("types", [])
                if not any(t in allowed_types for t in proxy_types_list):
                    continue

                # 国内支持筛选
                china_req = config.get("china_support")
                if china_req is not None and proxy_info.get("support", {}).get("china", False) != china_req:
                    continue

                # 国际支持筛选
                intl_req = config.get("international_support")
                if intl_req is not None and proxy_info.get("support", {}).get("international", False) != intl_req:
                    continue

                # 透明代理筛选
                transparent_req = config.get("transparent_only")
                if transparent_req is not None and proxy_info.get("transparent", False) != transparent_req:
                    continue

                # 浏览器验证状态筛选
                browser_status = config.get("browser_status")
                if browser_status is not None:
                    browser_info = proxy_info.get("browser", {})
                    browser_valid = browser_info.get("valid")

                    if browser_status == "failed":  # 仅验证失败的
                        if browser_valid is not False:  # 不是明确失败（可能是成功或未验证）
                            continue
                    elif browser_status == "success":  # 仅验证成功的
                        if browser_valid is not True:  # 不是明确成功（可能是失败或未验证）
                            continue
                    elif browser_status == "unknown":  # 仅验证未验证的
                        # 如果浏览器信息不存在，或valid字段不存在，或valid为None，视为未验证
                        if not browser_info or browser_valid is not None:
                            continue

                filtered_proxies.append(proxy)

            print(f"[info] 筛选条件:")
            print(f"   最低分数: {config.get('min_score', 80)}")
            print(f"   代理类型: {config.get('proxy_types', ['http', 'socks4', 'socks5'])}")
            print(f"   国内支持: {config.get('china_support', '不限制')}")
            print(f"   国际支持: {config.get('international_support', '不限制')}")
            print(f"   透明代理: {config.get('transparent_only', '不限制')}")

            # 显示浏览器验证状态筛选条件
            browser_status_map = {
                None: "不限制",
                "failed": "仅验证失败的代理",
                "success": "仅验证成功的代理",
                "unknown": "仅验证未验证的代理"
            }
            print(f"   浏览器验证状态: {browser_status_map.get(config.get('browser_status'), '不限制')}")

            print(f"   找到 {len(filtered_proxies)} 个符合条件的代理")

            # 限制验证数量
            max_proxies = config.get("max_proxies", 50)
            if len(filtered_proxies) > max_proxies:
                print(f"[info] 限制验证数量为 {max_proxies} 个")
                # 按分数排序，取分数高的
                filtered_proxies = sorted(
                    filtered_proxies,
                    key=lambda p: all_proxies[p],
                    reverse=True
                )[:max_proxies]

            proxies_to_validate = filtered_proxies

        if not proxies_to_validate:
            print("[failed] 没有符合条件的代理")
            return None

        # 获取代理类型（使用第一个类型）
        filtered_types = {}
        for proxy in proxies_to_validate:
            proxy_info = all_proxy_info.get(proxy, {})
            types = proxy_info.get("types", [])
            filtered_types[proxy] = types[0] if types else "http"

        # 进行浏览器验证
        browser_results = self.validate_proxies_with_browser(
            proxies_to_validate, filtered_types, config, from_interrupt=from_interrupt
        )

        # 更新代理池
        if browser_results:
            self.update_proxy_browser_status(browser_results)
            print("[success] 代理池浏览器验证状态已更新")

        return browser_results

    # 更新代理池中的浏览器验证状态
    def update_proxy_browser_status(self, browser_results):
        """更新代理池中的浏览器验证状态"""
        # 加载现有代理池
        existing_proxies, existing_info = self.database.load_proxies_from_db()

        # 更新浏览器验证状态
        for proxy, result in browser_results.items():
            if proxy in existing_info:
                # 确保browser字段存在
                if "browser" not in existing_info[proxy]:
                    existing_info[proxy]["browser"] = {}

                existing_info[proxy]["browser"]["valid"] = result.get("browser_valid", False)
                existing_info[proxy]["browser"]["check_date"] = result.get("browser_check_date", "unknown")
                if result.get("browser_valid"):
                    existing_info[proxy]["browser"]["response_time"] = result.get("browser_response_time", -1)

        # 保存更新后的代理池
        self.database.save_valid_proxies(existing_proxies, existing_info)

