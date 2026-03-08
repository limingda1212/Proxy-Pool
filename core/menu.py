# -*- coding: utf-8 -*-

import os
import json
import time

from core.config import ConfigManager
from collectors.web_crawler import WebCrawler
from collectors.file_loader import LoadFile
from validators.base_validator import BaseValidator
from validators.browser_validator import BrowserValidator
from schedulers.manual_scheduler import ManualScheduler
from schedulers.pool_monitor import PoolMonitor
from sync.github_sync import GithubSync
from storage.database import DatabaseManager
from utils.use_api import UseAPI
from utils.interrupt_handler import InterruptFileManager
from utils.change_configs import ChangeConfig
from utils.playwright_check import ensure_playwright_ready
from data.settings import INFO,INTRODUCTION




class MainMenu:
    def __init__(self, config: ConfigManager):
        self.config = config
        self.database = DatabaseManager(config.get("main.db_file","./data/proxies.db"))
        self.web_crawler = WebCrawler(config)
        self.load_file = LoadFile(config)
        self.base_validator = BaseValidator(config)
        self.browser_validator = BrowserValidator(config)
        self.manual_scheduler = ManualScheduler(config, self.database)
        self.pool_monitor = PoolMonitor(config, self.database)
        self.github_sync = GithubSync(config, self.database)
        self.interrupt = InterruptFileManager(self.config.get("interrupt.interrupt_dir"),config)
        self.use_api = UseAPI(config)
        self.change_config = ChangeConfig(config)

    def run(self):
        """运行主菜单"""
        while True:
            self.show_main_menu()
            choice = input("[input] 选择：").strip()
            self.handle_choice(choice)

    def show_main_menu(self):
        """显示主菜单"""
        print(f"""
[choice] 功能:
    1: 加载并验证新代理 (成功后添加到代理池)
    2: 检验并更新已有代理 (更新代理池代理分数)
    3: 浏览器可用验证 (检测出浏览器可用代理)
    4: 代理安全性验证 (检验代理安全性)
    
    5: 筛选并提取代理
    6: 查看代理池状态
    7: 同步代理池 (与GitHub Actions同步)
    8: API服务
    9: 清理数据库中的0分代理
    
    setting: 设置
    help: 帮助
    输入其他: 退出
        """)

    def handle_choice(self, choice: str):
        """处理用户选择"""
        handlers = {
            "1": self.validate_new_proxies_menu,
            "2": self.validate_existing_proxies_menu,
            "3": self.browser_validation_menu,
            "4": self.security_validation_menu,
            "5": self.extract_proxies_menu,
            "6": self.show_proxy_pool_status_menu,
            "7": self.synchronous_proxy_pool_menu,
            "8": self.api_integration_menu,
            "9": self.cleanup_zero_score_menu,
            "setting": self.setting_menu,
            "help": self.help_menu
        }

        handler = handlers.get(choice)
        if handler:
            handler()
        else:
            print("[exit] 退出")
            exit()

    def show_warranty(self):
        """显示保修信息（GPL要求）"""
        print("""
        本程序不提供任何担保，在法律允许的最大范围内。
        详细条款请参考GNU通用公共许可证第15、16条。
        """)

    def show_conditions(self):
        """显示再分发条件（GPL要求）"""
        print("""
        您可以自由地再分发本程序，但必须遵守以下条件：
        1. 保留原始版权声明和许可证信息
        2. 提供完整的源代码
        3. 修改后的版本必须以相同许可证发布
        完整条款请查看GNU通用公共许可证。
        """)

    # 加载并验证菜单
    def validate_new_proxies_menu(self):
        """加载并验证菜单"""
        new_proxies = None
        by_type = False

        print("""\n
======= 加载并验证代理 =======
    来自:
        1: 来自爬虫爬取
        2: 来自本地文件(proxy,port)

        输入其他: 返回上级菜单
            """)
        from_choice = input("[input] 选择:").strip()

        if from_choice == "1":
            interrupt_file = str(
                os.path.join(self.config.get("interrupt.interrupt_dir", "interrupt"),
                            self.config.get("interrupt.interrupt_file_crawl","interrupted_crawl_proxies.csv"))
            )
            # 先查找中断恢复
            from_interrupt, remaining_proxies, type_or_config, original_count = self.interrupt.check_interrupted_records(
                interrupt_file
            )
            if (from_interrupt == False) and (remaining_proxies == "return"):  # 返回上级菜单
                return

            elif from_interrupt and remaining_proxies:  # 来自中断恢复,且有剩余
                new_proxies = remaining_proxies
                by_type = type_or_config

            elif (from_interrupt == False) and (remaining_proxies is None):  # 重新爬取
                new_proxies, by_type = self.web_crawler.crawl_proxies()

            if new_proxies:  # 如果有新代理
                # by_type在爬取文件中默认auto
                self.base_validator.validate_new_proxies(new_proxies, by_type, from_interrupt)
            else:
                print("[failed] 没有新代理")

        elif from_choice == "2":
            interrupt_file = str(
                os.path.join(self.config.get("interrupt.interrupt_dir", "interrupt"),
                            self.config.get("interrupt.interrupt_file_load","interrupted_load_proxies.csv"))
            )
            # 先查找中断恢复
            from_interrupt, remaining_proxies, type_or_config, original_count = self.interrupt.check_interrupted_records(
                interrupt_file
            )
            if (from_interrupt == False) and (remaining_proxies == "return"):  # 返回上级菜单
                return

            elif from_interrupt and remaining_proxies:  # 来自中断恢复,且有剩余
                self.base_validator.validate_new_proxies(remaining_proxies, type_or_config, from_interrupt=True, source="load")

            elif (from_interrupt == False) and (remaining_proxies is None):  # 重新加载
                new_proxies, selected_type = self.load_file.load()

                if new_proxies:
                    # 使用指定类型(也可能为auto)验证
                    self.base_validator.validate_new_proxies(new_proxies, selected_type, source="load")

                else:
                    print("[failed] 没有新代理需要验证")

        else:
            print("[info] 返回上级菜单")
            return

    # 验证已有代理
    def validate_existing_proxies_menu(self):
        self.base_validator.validate_existing_proxies()   # 不用选择

    # 浏览器验证菜单
    def browser_validation_menu(self):
        """浏览器验证菜单"""

        # 检查 Playwright
        if not ensure_playwright_ready():
            print("[error] Playwright 不可用，跳过浏览器验证")
            return None

        # 先定义模式的菜单
        # 模式1: 自定义分层验证
        def custom_layered_validation():
            """自定义分层验证"""

            try:
                # 基本配置
                min_score = int(input("[input] 最低分数 (默认95): ") or "95")
                max_proxies = int(input("[input] 最大验证数量 (默认100): ") or "100")
                target_success = int(input("[input] 目标成功数量 (默认10): ") or "10")
                max_concurrent = int(input("[input] 并发数 (默认3): ") or "3")

                # 类型筛选
                print("\n[choice] 选择代理类型:")
                print("1: HTTP/HTTPS")
                print("2: SOCKS5")
                print("3: SOCKS4")
                print("4: 全部类型")
                type_choice = input("[input] 请选择 (1-4): ").strip()

                type_map = {
                    "1": ["http"],
                    "2": ["socks5"],
                    "3": ["socks4"],
                    "4": ["http", "socks4", "socks5"]
                }
                proxy_types = type_map.get(type_choice, ["http", "socks5"])

                # 支持范围筛选
                print("\n[choice] 选择支持范围:")
                print("1: 仅支持国内")
                print("2: 仅支持国际")
                print("3: 支持国内外")
                print("4: 不限制")
                support_choice = input("[input] 请选择 (1-4): ").strip()

                china_support = None
                international_support = None
                if support_choice == "1":
                    china_support = True
                    international_support = False
                elif support_choice == "2":
                    china_support = False
                    international_support = True
                elif support_choice == "3":
                    china_support = True
                    international_support = True
                # 4 不限制

                # 透明代理筛选
                print("\n[choice] 选择是否验证透明代理:")
                print("1: 仅验证透明代理")
                print("2: 仅验证非透明代理")
                print("3: 不限制")
                transparent_choice = input("[input] 请选择 (1-3): ").strip()

                transparent_only = None
                if transparent_choice == "1":
                    transparent_only = True
                elif transparent_choice == "2":
                    transparent_only = False
                # 3 不限制

                # 浏览器验证状态筛选
                print("\n[choice] 选择浏览器验证状态:")
                print("1: 仅验证浏览器验证失败的代理")
                print("2: 仅验证浏览器验证成功的代理")
                print("3: 仅验证未进行浏览器验证的代理")
                print("4: 不限制")
                browser_status_choice = input("[input] 请选择 (1-4): ").strip()

                browser_status = None  # None表示不限制，可选值："failed", "success", "unknown"
                if browser_status_choice == "1":
                    browser_status = "failed"  # 仅验证失败的
                elif browser_status_choice == "2":
                    browser_status = "success"  # 仅验证成功的
                elif browser_status_choice == "3":
                    browser_status = "unknown"  # 仅验证未验证的
                # 4 不限制

                config = {
                    "min_score": min_score,
                    "max_proxies": max_proxies,
                    "target_success": target_success,
                    "max_concurrent": max_concurrent,
                    "proxy_types": proxy_types,
                    "china_support": china_support,
                    "international_support": international_support,
                    "transparent_only": transparent_only,
                    "browser_status": browser_status
                }

                self.browser_validator.layered_browser_validation(config)

            except ValueError:
                print("[error] 输入无效")

        # === 主菜单 ===
        # 首先检查是否有浏览器验证中断记录
        interrupt_file = str(os.path.join(self.config.get("interrupt.interrupt_dir","interrupt"),
                                      self.config.get("interrupt.interrupt_file_browser","interrupted_browser_proxies.csv"))
                             )
        from_interrupt, remaining_proxies, type_or_config, original_count = self.interrupt.check_interrupted_records(
            interrupt_file
        )
        if (from_interrupt == False) and (remaining_proxies == "return"):  # 返回上级菜单
            return

        elif from_interrupt and remaining_proxies:
            # 直接解析 type_or_config，它一定是 JSON（因为是浏览器中断文件）
            try:
                config = json.loads(type_or_config)
                self.browser_validator.layered_browser_validation(
                    config=config,
                    from_interrupt=True,
                    proxies_to_validate=remaining_proxies
                )
            except json.JSONDecodeError:
                # 理论上不会到这里，但为了安全可以处理
                print("[error] 中断配置解析失败，可能是无效的浏览器验证中断")

        elif (from_interrupt == False) and (remaining_proxies is None):  # 重新
            print("[INFO] 筛选并验证代理")
            custom_layered_validation()

    # 安全验证菜单
    def security_validation_menu(self):
        """安全验证菜单"""
        # 首先检查是否有中断记录
        interrupt_file = str(os.path.join(
            self.config.get("interrupt.interrupt_dir", "interrupt"),
            self.config.get("interrupt.interrupt_file_safety", "interrupted_safety_proxies.csv")
        ))

        from_interrupt, remaining_proxies, type_or_config, original_count = self.interrupt.check_interrupted_records(
            interrupt_file
        )
        if (from_interrupt == False) and (remaining_proxies == "return"):
            return
        elif from_interrupt and remaining_proxies:
            # 从中断恢复，type_or_config 是 JSON 字符串
            try:
                config = json.loads(type_or_config)
                # 需要从 validators.security_checker 导入 SecurityValidator
                from validators.security_checker import SecurityValidator
                validator = SecurityValidator(self.config)
                validator.layered_security_validation(
                    config=config,
                    from_interrupt=True,
                    proxies_to_validate=remaining_proxies
                )
            except Exception as e:
                print(f"[error] 中断恢复失败: {e}")
        else:
            # 自定义安全验证条件
            def custom_security_validation():
                """自定义安全验证条件"""
                try:
                    min_score = int(input("[input] 最低分数 (默认80): ") or "80")
                    max_proxies = int(input("[input] 最大验证数量 (默认50): ") or "50")
                    max_concurrent = int(input("[input] 并发数 (默认100): ") or "100")

                    # 类型筛选
                    print("\n[choice] 选择代理类型:")
                    print("1: HTTP/HTTPS")
                    print("2: SOCKS5")
                    print("3: SOCKS4")
                    print("4: 全部类型")
                    type_choice = input("[input] 请选择 (1-4): ").strip()
                    type_map = {
                        "1": ["http"],
                        "2": ["socks5"],
                        "3": ["socks4"],
                        "4": ["http", "socks4", "socks5"]
                    }
                    proxy_types = type_map.get(type_choice, ["http"])

                    # 支持范围筛选
                    print("\n[choice] 选择支持范围:")
                    print("1: 仅支持国内")
                    print("2: 仅支持国际")
                    print("3: 支持国内外")
                    print("4: 不限制")
                    support_choice = input("[input] 请选择 (1-4): ").strip()
                    china = None
                    intl = None
                    if support_choice == "1":
                        china, intl = True, False
                    elif support_choice == "2":
                        china, intl = False, True
                    elif support_choice == "3":
                        china, intl = True, True

                    # 透明代理
                    print("\n[choice] 选择透明代理:")
                    print("1: 仅验证透明代理")
                    print("2: 仅验证非透明代理")
                    print("3: 不限制")
                    trans_choice = input("[input] 请选择 (1-3): ").strip()
                    trans_only = None
                    if trans_choice == "1":
                        trans_only = True
                    elif trans_choice == "2":
                        trans_only = False

                    # 浏览器状态（可选）
                    print("\n[choice] 选择浏览器验证状态:")
                    print("1: 仅验证浏览器失败的代理")
                    print("2: 仅验证浏览器成功的代理")
                    print("3: 仅验证未进行浏览器验证的代理")
                    print("4: 不限制")
                    browser_status_choice = input("[input] 请选择 (1-4): ").strip()
                    browser_status = None
                    if browser_status_choice == "1":
                        browser_status = "failed"
                    elif browser_status_choice == "2":
                        browser_status = "success"
                    elif browser_status_choice == "3":
                        browser_status = "unknown"

                    config = {
                        "min_score": min_score,
                        "max_proxies": max_proxies,
                        "max_concurrent": max_concurrent,
                        "proxy_types": proxy_types,
                        "china_support": china,
                        "international_support": intl,
                        "transparent_only": trans_only,
                        "browser_status": browser_status
                    }

                    from validators.security_checker import SecurityValidator
                    validator = SecurityValidator(self.config)
                    validator.layered_security_validation(config)
                except ValueError:
                    print("[error] 输入无效")

            # 新验证，让用户输入筛选条件（类似 browser_validator 中的自定义分层验证）
            custom_security_validation()

    # 提取代理菜单
    def extract_proxies_menu(self):
        """提取代理菜单（支持按类型、支持范围和透明代理筛选）"""
        try:
            count = int(input("[input] 请输入要提取的代理数量: ").strip())
            if count <= 0:
                print("[failed] 数量必须大于0")
                return

            # 选择代理类型
            print("\n[choice] 选择代理类型:")
            print("1: http/https")
            print("2: socks4")
            print("3: socks5")
            print("4: 全部类型")
            type_choice = input("[input] 请选择(1-4): ").strip()

            type_map = {
                "1": "http",
                "2": "socks4",
                "3": "socks5",
                "4": "all"
            }

            proxy_type = type_map.get(type_choice, "all")

            # 选择支持范围
            print("\n[choice] 选择支持范围:")
            print("1: 仅支持国内")
            print("2: 仅支持国际")
            print("3: 支持国内外")
            print("4: 不限制支持范围")
            support_choice = input("[input] 请选择(1-4): ").strip()

            china_support = None
            international_support = None

            if support_choice == "1":
                china_support = True
                international_support = False
            elif support_choice == "2":
                china_support = False
                international_support = True
            elif support_choice == "3":
                china_support = True
                international_support = True
            # 4 和其他情况不限制

            # 选择透明代理筛选
            print("\n[choice] 选择透明代理筛选:")
            print("1: 仅提取透明代理")
            print("2: 仅提取非透明代理")
            print("3: 不限制")
            transparent_choice = input("[input] 请选择(1-3): ").strip()

            transparent_only = None
            if transparent_choice == "1":
                transparent_only = True
            elif transparent_choice == "2":
                transparent_only = False
            # 3 和其他情况不限制

            # 浏览器可用筛选
            print("\n[choice] 选择浏览器可用代理筛选:")
            print("1: 仅提取浏览器可用代理")
            print("2: 仅提取浏览器不可用代理")
            print("3: 不限制")
            browser_choice = input("[input] 请选择(1-3): ").strip()

            browser_only = None
            if browser_choice == "1":
                browser_only = True
            elif browser_choice == "2":
                browser_only = False
            # 3 和其他情况不限制

            # 安全通过数量要求
            print("\n[choice] 选择安全验证项目通过数量要求 (0-5，留空不限制):")
            security_req = input("[input] 至少要求通过数量: ").strip()
            if security_req == "":
                min_security = None
            else:
                try:
                    min_security = int(security_req)
                    if not 0 <= min_security <= 5:
                        print("[failed] 请输入0-5之间的数字")
                        return
                except ValueError:
                    print("[error] 输入无效")
                    return

            # 调用提取方法
            proxies = self.manual_scheduler.extract_proxies_by_type(
                count, proxy_type, china_support, international_support,
                transparent_only, browser_only, min_security_passed=min_security
            )

            if not proxies:
                print("[warning] 代理池中没有符合条件的代理")
                return

            if len(proxies) < count:
                print(f"[warning] 只有 {len(proxies)} 个符合条件代理，少于请求的 {count} 个")

            print(f"\n[success] 提取的代理列表({proxy_type}):")
            for i, proxy_info in enumerate(proxies, 1):
                support_desc = []
                if proxy_info["china"]:
                    support_desc.append("国内")
                if proxy_info["international"]:
                    support_desc.append("国际")
                support_str = "|".join(support_desc) if support_desc else "无"
                transparent_str = "[warning]透明" if proxy_info["transparent"] else "匿名"
                security_str = f" | 安全:{proxy_info['security_passed']}/5"
                print(
                    f"{i}. {proxy_info['proxy']} | 分数:{proxy_info['score']} | 支持:{support_str} | {transparent_str}{security_str}"
                )

            save_choice = input("[input] 是否保存到文件? (y/n): ").lower().strip()
            if save_choice == "y":
                filename = input("[input] 请输入文件名(默认proxies.csv): ") or "proxies.csv"
                with open(filename, "w", encoding="utf-8") as file:
                    for proxy_info in proxies:
                        file.write(f"{proxy_info['proxy']}\n")
                print(f"[success] 已保存到 {filename}")
        except ValueError:
            print("[error] 请输入有效的数字")

    # 展示代理池状态
    def show_proxy_pool_status_menu(self):
        self.pool_monitor.show_proxy_pool_status()    # 不用选择

    # 同步代理池功能
    def synchronous_proxy_pool_menu(self):
        """同步代理池功能 - 与GitHub仓库同步"""
        print(f"""\n
======= 代理池同步功能 =======
    1: 从GitHub下载代理池(合并到本地)
    2: 上传本地代理池到GitHub({"✅已有token可上传" if self.config.get("github.token", "") else "❌未提供token无法上传"})

    输入其他: 返回上级菜单
        """)

        choice = input("[input] 请选择: ").strip()

        if choice == "1":
            self.github_sync.download_from_github()
        elif choice == "2":
            # 再次确认
            print("[info] 再次确认")
            upload = input("[input] 输入任意内容以继续,不输入则取消:")
            if len(upload) == 0:
                print("[info] 取消上传")
            else:
                self.github_sync.upload_to_github()

        else:
            return

    # API集成菜单
    def api_integration_menu(self):
        """API集成菜单"""
        print("""\n
======= API集成功能 =======
    1: 启动代理池API服务
    2: 测试API连接
    3: 通过API获取代理
    4: 查看API统计
    5: 让api重新加载代理池
    6: 生成api爬虫调用模板代码(.py)
    
    其他: 返回上级菜单
        """)

        choice = input("[input] 请选择:").strip()

        current_host = self.config.get("api.host","0.0.0.0")
        current_port = self.config.get("api.port", 8000)

        if choice == "1":
            self.use_api.start_api_server(current_host, current_port)
        elif choice == "2":
            self.use_api.test_api_connection(current_host, current_port)
        elif choice == "3":
            self.use_api.get_proxy_via_api(current_host, current_port)
        elif choice == "4":
            self.use_api.get_api_stats(current_host, current_port)
        elif choice == "5":
            self.use_api.reload_proxy_api(current_host, current_port)
        elif choice == "6":
            self.use_api.api_usage_template()
        else:
            return

    # 0分代理清理
    def cleanup_zero_score_menu(self):
        self.database.cleanup_zero_score_proxies()    # 不用选择

    # 更改和查看设置
    def setting_menu(self):
        """更改和查看设置"""
        while True:
            print("""\n
======= 配置管理 =======
    1: 查看当前配置
    2: 编辑主要设置
    3: 编辑中断设置
    4: 编辑GitHub设置
    5: 编辑API设置
    6: 重置为默认配置
    
    其他: 返回主菜单
                    """)

            choice = input("[input] 请选择操作: ").strip()

            if choice == "1":
                self.change_config.show_full_config()
            elif choice == "2":
                self.change_config.edit_main_settings()
            elif choice == "3":
                self.change_config.edit_interrupt_settings()
            elif choice == "4":
                self.change_config.edit_github_settings()
            elif choice == "5":
                self.change_config.edit_api_settings()
            elif choice == "6":
                self.change_config.reset_to_defaults()
            else:
                print("[INFO] 返回上级菜单")
                break


    # 帮助菜单
    def help_menu(self):
        """帮助菜单"""
        print("""
======= 帮助菜单 =======
    1: 查看介绍
    2: 快速开始
    
    show w: 保修信息
    show c: 再分发条件
    
    其他: 返回
        """)

        choice = input("[input] 输入:").strip()

        if choice == "1":
            print(f"{INFO}")
            print(f"{INTRODUCTION}")
            print(f"代理池({self.config.get("main.db_file","./data/proxies.db")})")

        elif choice == "2":
            print("开始之前,需要确保已经完善python环境,推荐使用虚拟环境(venv)")
            i = input("未完成请直接回车,完成请输入任意内容后回车:")
            if not i:
                print("🌟请尽快完善python环境,程序已自动退出")
                exit(0)

            i = input("需要先获取代理才能进行接下来的管理(输入任意内容后回车表示开始,直接回车跳过):")
            if i:
                print("🌟注意:本代码支持中断恢复,当你觉得消耗时间太长时,可以按下Ctrl+c,我们会自动保存你的进度")
                time.sleep(2)
                self.validate_new_proxies_menu()
                print("看来你已经获取了代理,现在可以管理或使用了")

            i = input("需不需要再重新验证一下刚刚获取的代理(输入任意内容后回车表示需要,直接回车跳过):")
            if i:
                print("🌟注意:本代码支持中断恢复,当你觉得消耗时间太长时,可以按下Ctrl+c,我们会自动保存你的进度")
                time.sleep(2)
                self.validate_existing_proxies_menu()

            i = input("需不需要看看自己的成果,展示当前代理池状态(输入任意内容后回车表示需要,直接回车跳过):")
            if i:
                self.show_proxy_pool_status_menu()

            i = input("当你需要使用时可以手动提取,也可以开放api便于爬虫调用(输入任意内容后回车表示尝试一下,直接回车跳过):")
            if i:
                print("请输入1/2")
                print("1: 尝试手动提取")
                print("2: 尝试开放api端口")
                a = input("选择1/2/默认1:")

                if a == "2":
                    print("请输入'1'以开启api")
                    host = self.config.get("api.host", "0.0.0.0")
                    port = self.config.get("api.port", 8000)
                    print(f"🌟注意:api服务将在http://{host}:{port}运行,请确保此端口没被占用(若占用可以从主菜单setting选项更改)")
                    print(f"🌟开放端口后可以用浏览器访问http://{host}:{port}来查看管理界面")
                    print("🌟按下Ctrl+c可以关闭api")
                    time.sleep(2)
                    self.api_integration_menu()
                else:   # 默认手动提取
                    self.extract_proxies_menu()
            print("看来你已经学会使用基础功能了,但是代理太多会浪费很多时间")
            print("你可以尝试获取部署在Github Actions的云端自动维护的代理,这样就不会很麻烦了")
            i = input("(输入任意内容后回车表示尝试一下,直接回车跳过):")
            if i:
                print("🌟注意:在国内(中国)访问github极不稳定,同步极有可能因超时而失败,建议多尝试几次")
                time.sleep(2)
                self.synchronous_proxy_pool_menu()
            print("你已经学会使用本代理池了")
            print("🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉")

        elif choice == "show w":
            self.show_warranty()

        elif choice == "show c":
            self.show_conditions()

        else:
            return



