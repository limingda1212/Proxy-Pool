from typing import Any, Callable, Type
from core.config import ConfigManager


class ChangeConfig:
    def __init__(self, config: ConfigManager):
        self.config = config

    # 通用输入函数
    def get_input(self, prompt: str, current_value: Any, input_type: Type = str,
                  validation: Callable[[Any], bool] = None) -> Any:
        """通用输入函数"""
        while True:
            user_input = input(f"[input] {prompt}(当前:{current_value}): ").strip()
            if not user_input:
                return current_value

            try:
                if input_type is int:
                    if user_input.isdigit() and int(user_input) > 0:
                        value = int(user_input)
                    else:
                        print("[failed] 请输入正整数")
                        continue
                elif input_type is bool:
                    if user_input.lower() in ["true", "1", "yes", "y"]:
                        value = True
                    elif user_input.lower() in ["false", "0", "no", "n"]:
                        value = False
                    else:
                        print("[failed] 请输入 true/yes 或 false/no")
                        continue
                else:
                    value = user_input

                if validation and not validation(value):
                    continue

                return value
            except ValueError:
                print("[error] 输入错误")

    # 编辑主要设置
    def edit_main_settings(self):
        """编辑主要设置"""
        # 获取当前配置值
        check_transparent = self.config.get("main.check_transparent", "true")
        get_ip_info = self.config.get("main.get_ip_info", "true")
        high_score_agency_scope = self.config.get("main.high_score_agency_scope", 70)
        test_url_cn = self.config.get("main.test_url_cn", "https://www.baidu.com")
        test_url_intl = self.config.get("main.test_url_intl", "https://www.google.com")
        timeout_cn = self.config.get("main.timeout_cn", 5)
        timeout_intl = self.config.get("main.timeout_intl", 10)
        timeout_transparent = self.config.get("main.timeout_transparent", 5)
        timeout_ipinfo = self.config.get("main.timeout_ipinfo", 5)
        max_workers = self.config.get("main.max_workers", 50)
        db_file = self.config.get("main.db_file", "../data/proxies.db")
        max_score = self.config.get("main.max_score", 100)
        number_of_items_per_row = self.config.get("main.number_of_items_per_row", 5)

        print(f"""[info] 当前设置:
            1:透明代理检查:{"开启" if str(check_transparent).lower() == "true" else "关闭"}
            2:获取IP信息:{"开启" if str(get_ip_info).lower() == "true" else "关闭"}
            3:高分代理范围不低于:{high_score_agency_scope}
            4:国内测试URL:{test_url_cn}
            5:国际测试URL:{test_url_intl}
            6:国内测试超时:{timeout_cn}秒
            7:国际测试超时:{timeout_intl}秒
            8:透明代理测试超时:{timeout_transparent}秒
            9:IP信息获取超时:{timeout_ipinfo}秒
            10:最大并发数:{max_workers}
            11:输出数据库:{db_file}
            12:最大分数:{max_score}
            13:代理池状态每行显示各分数段数量:{number_of_items_per_row}
        """)

        edit_choice = input("[input] 修改项目序号(回车不修改):")

        if not edit_choice:
            return False

        try:
            if edit_choice == "1":
                # 切换透明代理检查
                current_value = str(check_transparent).lower() == "true"
                new_value = not current_value
                self.config.set("main.check_transparent", str(new_value).lower())
                print(f"[success] 透明代理检查已{'开启' if new_value else '关闭'}")

            elif edit_choice == "2":
                # 切换获取IP信息
                current_value = str(get_ip_info).lower() == "true"
                new_value = not current_value
                self.config.set("main.get_ip_info", str(new_value).lower())
                print(f"[success] 获取IP信息已{'开启' if new_value else '关闭'}")

            elif edit_choice == "3":
                # 修改高分代理范围
                def validate_scope(value):
                    if 0 <= value <= 100:
                        return True
                    print("[failed] 请输入0-100之间的数字")
                    return False

                new_scope = self.get_input("请输入新的高分代理范围",
                                           high_score_agency_scope,
                                           int, validate_scope)
                self.config.set("main.high_score_agency_scope", new_scope)
                print(f"[success] 高分代理范围已设置为: {new_scope}")

            elif edit_choice == "4":
                # 修改国内测试URL
                new_url = self.get_input("请输入新的国内测试URL", test_url_cn)
                self.config.set("main.test_url_cn", new_url)
                print(f"[success] 国内测试URL已设置为: {new_url}")

            elif edit_choice == "5":
                # 修改国际测试URL
                new_url = self.get_input("请输入新的国际测试URL", test_url_intl)
                self.config.set("main.test_url_intl", new_url)
                print(f"[success] 国际测试URL已设置为: {new_url}")

            elif edit_choice == "6":
                # 修改国内测试超时
                new_timeout = self.get_input("请输入新的国内测试超时时间(秒)", timeout_cn, int)
                self.config.set("main.timeout_cn", new_timeout)
                print(f"[success] 国内测试超时已设置为: {new_timeout}秒")

            elif edit_choice == "7":
                # 修改国际测试超时
                new_timeout = self.get_input("请输入新的国际测试超时时间(秒)", timeout_intl, int)
                self.config.set("main.timeout_intl", new_timeout)
                print(f"[success] 国际测试超时已设置为: {new_timeout}秒")

            elif edit_choice == "8":
                # 修改透明代理测试超时
                new_timeout = self.get_input("请输入新的透明代理测试超时时间(秒)",
                                             timeout_transparent, int)
                self.config.set("main.timeout_transparent", new_timeout)
                print(f"[success] 透明代理测试超时已设置为: {new_timeout}秒")

            elif edit_choice == "9":
                # 修改IP信息获取超时
                new_timeout = self.get_input("请输入新的IP信息获取超时时间(秒)",
                                             timeout_ipinfo, int)
                self.config.set("main.timeout_ipinfo", new_timeout)
                print(f"[success] IP信息获取超时已设置为: {new_timeout}秒")

            elif edit_choice == "10":
                # 修改最大并发数
                new_workers = self.get_input("请输入新的最大并发数", max_workers, int)
                self.config.set("main.max_workers", new_workers)
                print(f"[success] 最大并发数已设置为: {new_workers}")

            elif edit_choice == "11":
                # 修改输出数据库路径
                new_path = self.get_input("请输入新的输出数据库(SQLite)路径", db_file)
                self.config.set("main.db_file", new_path)
                print(f"[success] 输出路径已设置为: {new_path}")

            elif edit_choice == "12":
                # 修改最大分数
                new_score = self.get_input("请输入新的最大分数", max_score, int)
                self.config.set("main.max_score", new_score)
                print(f"[success] 最大分数已设置为: {new_score}")

            elif edit_choice == "13":
                # 修改每行显示项目数
                def validate_items_per_row(value):
                    if 1 <= value <= 20:
                        return True
                    print("[failed] 请输入1-20之间的数字")
                    return False

                new_items = self.get_input("请输入每行显示的项目数",
                                           number_of_items_per_row,
                                           int, validate_items_per_row)
                self.config.set("main.number_of_items_per_row", new_items)
                print(f"[success] 每行显示项目数已设置为: {new_items}")

            else:
                print("[info] 无效的选择，返回上级菜单")
                return False

            # 保存配置到文件
            if self.config.save():
                print("[success] 配置已保存到文件")
            else:
                print("[warning] 配置保存失败")

            return True

        except Exception as e:
            print(f"[error] 修改配置时出错: {e}")
            return False

    # 编辑中断设置
    def edit_interrupt_settings(self):
        """编辑中断设置"""
        # 获取当前配置值
        interrupt_dir = self.config.get("interrupt.interrupt_dir", "../interrupt")
        interrupt_file_crawl = self.config.get("interrupt.interrupt_file_crawl",
                                               "interrupted_crawl_proxies.csv")
        interrupt_file_load = self.config.get("interrupt.interrupt_file_load",
                                              "interrupted_load_proxies.csv")
        interrupt_file_existing = self.config.get("interrupt.interrupt_file_existing",
                                                  "interrupted_existing_proxies.csv")
        interrupt_file_safety = self.config.get("interrupt.interrupt_file_safety",
                                                "interrupted_safety_proxies.csv")
        interrupt_file_browser = self.config.get("interrupt.interrupt_file_browser",
                                                 "interrupted_browser_proxies.csv")

        print(f"""[info] 中断设置:
            1:中断文件目录:{interrupt_dir}
            2:爬取验证中断文件:{interrupt_file_crawl}
            3:本地文件加载中断文件:{interrupt_file_load}
            4:更新代理池中断文件:{interrupt_file_existing}
            5:安全性验证中断文件:{interrupt_file_safety}
            6:浏览器验证中断文件:{interrupt_file_browser}
        """)

        edit_choice = input("[input] 修改项目序号(回车不修改):")

        if not edit_choice:
            return False

        try:
            if edit_choice == "1":
                new_dir = self.get_input("请输入新的中断文件目录", interrupt_dir)
                self.config.set("interrupt.interrupt_dir", new_dir)
                print(f"[success] 中断文件目录已设置为: {new_dir}")

            elif edit_choice == "2":
                new_file = self.get_input("请输入新的爬取验证中断文件名", interrupt_file_crawl)
                self.config.set("interrupt.interrupt_file_crawl", new_file)
                print(f"[success] 爬取验证中断文件名已设置为: {new_file}")

            elif edit_choice == "3":
                new_file = self.get_input("请输入新的本地文件加载中断文件名", interrupt_file_load)
                self.config.set("interrupt.interrupt_file_load", new_file)
                print(f"[success] 本地文件加载中断文件名已设置为: {new_file}")

            elif edit_choice == "4":
                new_file = self.get_input("请输入新的更新代理池中断文件名", interrupt_file_existing)
                self.config.set("interrupt.interrupt_file_existing", new_file)
                print(f"[success] 更新代理池中断文件名已设置为: {new_file}")

            elif edit_choice == "5":
                new_file = self.get_input("请输入新的安全性验证中断文件名", interrupt_file_safety)
                self.config.set("interrupt.interrupt_file_safety", new_file)
                print(f"[success] 安全性验证中断文件名已设置为: {new_file}")

            elif edit_choice == "6":
                new_file = self.get_input("请输入新的浏览器验证中断文件名", interrupt_file_browser)
                self.config.set("interrupt.interrupt_file_browser", new_file)
                print(f"[success] 浏览器验证中断文件名已设置为: {new_file}")

            else:
                print("[info] 无效的选择，返回上级菜单")
                return False

            # 保存配置到文件
            if self.config.save():
                print("[success] 中断设置已保存到文件")
            else:
                print("[warning] 配置保存失败")

            return True

        except Exception as e:
            print(f"[error] 修改中断设置时出错: {e}")
            return False

    # 编辑GitHub设置
    def edit_github_settings(self):
        """编辑GitHub设置"""
        # 获取当前配置值
        github_token = self.config.get("github.token", "")

        if github_token:
            masked_token = github_token[0:15] + ("*" * (len(github_token) - 15)) if len(github_token) > 15 else "***"
        else:
            masked_token = "未设置"

        print(f"""[info] GitHub同步设置:
            1: GitHub Token: {masked_token}
        """)

        edit_choice = input("[input] 修改项目序号(回车不修改):")

        if not edit_choice:
            return False

        try:
            if edit_choice == "1":
                current_token = github_token
                masked_token = "*" * len(current_token) if current_token else "未设置"
                new_token = input(f"[input] 请输入新的GitHub Token(当前:{masked_token}): ").strip()
                if new_token:
                    self.config.set("github.token", new_token)
                    print("[success] GitHub Token已更新")
                    # 保存配置到文件
                    if self.config.save():
                        print("[success] GitHub设置已保存到文件")
                    else:
                        print("[warning] 配置保存失败")
                else:
                    print("[info] 未修改GitHub Token")
            else:
                print("[info] 无效的选择，返回上级菜单")
                return False

            return True

        except Exception as e:
            print(f"[error] 修改GitHub设置时出错: {e}")
            return False

    # 编辑API设置
    def edit_api_settings(self):
        """编辑API设置"""
        # 获取当前配置值
        api_host = self.config.get("api.host", "127.0.0.1")
        api_port = self.config.get("api.port", 8000)

        print(f"""[info] API设置:
            1: host: {api_host}
            2: port: {api_port}
        """)

        edit_choice = input("[input] 修改项目序号(回车不修改):")

        if not edit_choice:
            return False

        try:
            if edit_choice == "1":
                new_host = input(f"[input] 请输入新的API host(当前:{api_host}): ").strip()
                if new_host:
                    self.config.set("api.host", new_host)
                    print("[success] host已更新")
                else:
                    print("[info] 未修改host")

            elif edit_choice == "2":
                try:
                    new_port_input = input(f"[input] 请输入新的API port(当前:{api_port}): ").strip()
                    if new_port_input:
                        new_port = int(new_port_input)
                        if 0 < new_port < 65535:
                            self.config.set("api.port", new_port)
                            print("[success] port已更新")
                        else:
                            print("[failed] 端口号必须在1-65534之间")
                            return False
                    else:
                        print("[info] 未修改port")
                except ValueError:
                    print("[error] 请输入有效数字")
                    return False

            else:
                print("[info] 无效的选择，返回上级菜单")
                return False

            # 保存配置到文件
            if self.config.save():
                print("[success] API设置已保存到文件")
            else:
                print("[warning] 配置保存失败")

            return True

        except Exception as e:
            print(f"[error] 修改api设置时出错: {e}")
            return False

    # 显示完整配置
    def show_full_config(self):
        """显示完整配置"""
        print("[info] 当前完整配置:")
        for section, values in self.config.config.items():
            print(f"\n=== {section.upper()} ===")
            if isinstance(values, dict):
                for key, value in values.items():
                    # 敏感信息处理
                    if "token" in key.lower() and value:
                        masked_value = value[:10] + "..." if len(value) > 10 else "***"
                        print(f"  {key}: {masked_value}")
                    else:
                        print(f"  {key}: {value}")
            else:
                print(f"  {values}")

    # 重置配置到默认值
    def reset_to_defaults(self):
        """重置配置到默认值"""
        confirm = input("[input] 确定要重置所有配置到默认值吗？(y/n): ").strip().lower()
        if confirm in ["y", "yes"]:
            # 定义默认配置
            default_config = {
                "main": {
                    "check_transparent": "true",
                    "get_ip_info": "true",
                    "high_score_agency_scope": 98,
                    "test_url_cn": "https://www.baidu.com",
                    "test_url_intl": "https://www.google.com",
                    "timeout_cn": 6,
                    "timeout_intl": 10,
                    "timeout_transparent": 8,
                    "timeout_ipinfo": 8,
                    "max_workers": 100,
                    "db_file": "../data/proxies.db",
                    "max_score": 100,
                    "number_of_items_per_row": 5
                },
                "interrupt": {
                    "interrupt_dir": "../interrupt",
                    "interrupt_file_crawl": "interrupted_crawl_proxies.csv",
                    "interrupt_file_load": "interrupted_load_proxies.csv",
                    "interrupt_file_existing": "interrupted_existing_proxies.csv",
                    "interrupt_file_safety": "interrupted_safety_proxies.csv",
                    "interrupt_file_browser": "interrupted_browser_proxies.csv"
                },
                "github": {
                    "token": ""
                },
                "api": {
                    "host": "127.0.0.1",
                    "port": 8000
                }
            }

            # 应用默认配置
            for section, values in default_config.items():
                if isinstance(values, dict):
                    for key, value in values.items():
                        self.config.set(f"{section}.{key}", value)

            # 保存到文件
            if self.config.save():
                print("[success] 配置已重置为默认值并保存")
            else:
                print("[warning] 配置保存失败")
        else:
            print("[info] 已取消重置操作")