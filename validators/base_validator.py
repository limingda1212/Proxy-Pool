# -*- coding: utf-8 -*-
import requests
import concurrent.futures
from datetime import date
from typing import Dict, Any, Tuple, List
import random
import time
import os

from utils.helpers import set_up_proxy,is_valid_ip
from core.config import ConfigManager
from data.settings import HEADERS
from utils.interrupt_handler import InterruptFileManager
from storage.database import DatabaseManager
from utils.signal_manager import signal_manager

class BaseValidator:
    def __init__(self, config: ConfigManager):
        self.config = config
        self.database = DatabaseManager(config.get("main.db_file", "./data/proxies.db"))
        self.interrupt = InterruptFileManager(self.config.get("main.interrupt_dir","interrupt"),config)

    # 获取自己的公网IP地址
    def get_own_ip(self, max_retries=6, retry_delay=2):
        """
        获取自己的公网IP地址

        :param max_retries: 最大重试次数
        :param retry_delay: 重试延迟(秒)
        :return: IP地址字符串，失败返回None
        """
        services = self.config.get("main.test_url_transparent",["https://httpbin.org/ip"])
        timeout = self.config.get("main.timeout_transparent",8)

        for attempt in range(max_retries):
            # 随机获取一个服务来获取
            service = random.choice(services)
            try:

                print(f"[info] 尝试从 {service} 获取本机IP...")
                response = requests.get(service, timeout=timeout, headers=HEADERS)

                if response.status_code == 200:
                    if service == "https://httpbin.org/ip":
                        # httpbin返回JSON格式
                        ip_data = response.json()
                        ip = ip_data.get("origin")
                    else:
                        # 其他服务返回纯字符串
                        ip = response.text.strip()

                    # 验证IP格式
                    if ip and is_valid_ip(ip):
                        print(f"[success] 成功获取本机IP: {ip}")
                        # 尝试保存本次获取,方便下次获取失败时可以使用本次的
                        self.config.set("main.own_ip", ip)
                        self.config.save()

                        return ip
                    else:
                        print(f"[warning] 从 {service} 获取的IP格式无效: {ip}")

            except requests.exceptions.Timeout:
                print(f"[warning] 请求 {service} 超时")
                continue
            except requests.exceptions.ConnectionError:
                print(f"[warning] 无法连接到 {service}")
                continue
            except Exception as e:
                print(f"[warning] 从 {service} 获取IP时出错: {str(e)}")
                continue

            # 服务失败，等待后重试
            if attempt < max_retries - 1:
                print(f"[info] IP获取失败，{retry_delay}秒后重试... ({attempt + 1}/{max_retries})")
                time.sleep(retry_delay)

        print("[error] 本次未获取本机IP地址，使用上次的ip记录")
        return None

    # 获取单个代理信息
    def get_ip_info(self, proxy, proxy_type="http") -> str | Dict[str, Any]:
        """
        获取单个代理信息

        :param proxy: 代理地址
        :param proxy_type: 代理类型
        :return: proxy_ip_info/unkown
        """
        try:
            # 设置代理
            proxies_config = set_up_proxy(proxy, proxy_type)

            # 使用服务
            url = self.config.get("main.test_url_info","https://ipinfo.io/json")

            # 使用代理访问检测网站
            response = requests.get(
                url,
                proxies=proxies_config,
                timeout=self.config.get("main.timeout_ipinfo",8)
            )

            if response.status_code == 200:
                # 返回JSON格式
                proxy_ip_info = response.json()

                return proxy_ip_info
            else:
                return "unknown"

        except:
            return "unknown"

    # 检测代理是否为透明代理
    def check_transparent_proxy(self, proxy, proxy_type="http", own_ip=None) -> Tuple[bool,bool,str]:
        """
        检测代理是否为透明代理

        :param proxy: 代理地址
        :param proxy_type: 代理类型
        :param own_ip: 自己的公网IP
        :return: 是否检测成功, 是否为透明代理, 检测到的IP -> error: False, False, "unknown"

        """
        try:
            # 设置代理
            proxies_config = set_up_proxy(proxy, proxy_type)

            # 使用服务
            urls = self.config.get("main.test_url_transparent",["https://httpbin.org/ip"])
            # 随机挑选一个
            url = random.choice(urls)

            # 使用代理访问检测网站
            response = requests.get(
                url,
                proxies=proxies_config,
                timeout=self.config.get("main.timeout_transparent",8)
            )

            if response.status_code == 200:
                if url == "https://httpbin.org/ip":
                    # httpbin返回JSON格式
                    ip_data = response.json()
                    ip = ip_data.get("origin")
                else:
                    # 其他服务返回纯字符串
                    ip = response.text.strip()

                # 判断是否为透明代理：如果返回的IP包含真实IP，则为透明代理
                is_transparent = own_ip in ip

                return True, is_transparent, ip
            else:
                return False, False, "unknown"

        except Exception as e:
            # print(e)    # 减少输出,部分代理由于超时等问题也会报错,这类可以忽略
            # print(f"[error] 对{proxy}进行透明检测时出错")
            return False, False, "unknown"

    # 检查单个代理IP对单个URL的可用性（支持HTTP和SOCKS）
    def check_proxy_single(self, proxy: str, test_url: str, timeout: int,
                           retries: int = 1, proxy_type: str = "auto") -> tuple[bool, float, str] | tuple[bool, None, str]:
        """
        检查单个代理IP对单个URL的可用性（支持HTTP和SOCKS）

        :param proxy_type: 代理类型 - "auto"(自动检测), "http", "socks4", "socks5"
        :param proxy: 代理IP地址和端口 (格式: ip:port)
        :param test_url: 用于测试的URL
        :param timeout: 请求超时时间(秒)
        :param retries: 重试次数
        :return: 是否可用, 响应时间, 检测到的类型
        """
        # 根据代理类型设置proxies字典
        if proxy_type == "auto":
            # 自动检测：先尝试HTTP，再尝试SOCKS5，最后SOCKS4
            protocols_to_try = ["http", "socks5", "socks4"]
        else:
            # 指定类型时，只尝试该类型
            protocols_to_try = [proxy_type]

        detected_type = proxy_type if proxy_type != "auto" else "unknown"

        for current_protocol in protocols_to_try:
            # 设置代理
            proxies_config = set_up_proxy(proxy, current_protocol)

            for attempt in range(retries):
                try:
                    start_time = time.time()
                    response = requests.get(
                        test_url,
                        proxies=proxies_config,
                        timeout=timeout,
                        allow_redirects=False
                    )
                    end_time = time.time()
                    response_time = end_time - start_time

                    if response_time > timeout:
                        # 超时，继续下一个协议（如果是自动检测）
                        break

                    # if 200 <= response.status_code < 400:   # 接受200-400,宽松
                    # if 200 <= response.status_code < 300:   # 接受200-300,较宽松
                    # if response.status_code in [200, 204]:  # 接受200或204,严格
                    if response.status_code == 204:  # 使用204站点,只接受204,严格
                        detected_type = current_protocol  # 类型
                        return True, response_time, detected_type

                except:
                    if attempt < retries - 1:
                        time.sleep(0.5)
                        continue
                    # 当前协议失败，如果是自动检测则尝试下一个协议
                    break

        # 如果是指定类型验证失败，返回指定类型（即使失败）
        if proxy_type != "auto":
            detected_type = proxy_type

        return False, None, detected_type

    # 双重验证代理
    def check_proxy_dual(self, proxy: str, already_have_info: Dict[str, int],
                         proxy_type: str = "auto", avg_response_time: float = -1,
                         success_rate: float = 0.5) -> Dict[str, Any]:
        """
        双重验证代理
        同时验证百度(国内)和Google(国际)，可选透明代理检测

        :param proxy: 被检测的单个代理
        :param already_have_info: 是否已有信息
        :param proxy_type: 代理类型
        :param avg_response_time: 代理平均响应时间
        :param success_rate: 代理平均响应成功率
        :return: 代理信息
        """
        new_ip_info: Dict[str, Any] = {  # 初始化时为unknown或False,: Dict[str, Any]用于去掉pycharm的黄色提示
            "types": [],
            "support": {
                "china": False,
                "international": False
            },
            "transparent": False,
            "detected_ip": "unknown",
            "location": {
                "city": "unknown",
                "region": "unknown",
                "country": "unknown",
                "loc": "unknown",
                "org": "unknown",
                "postal": "unknown",
                "timezone": "unknown"
            },
            "performance": {
                "avg_response_time": -1,
                "success_rate": 0.5,
                "last_checked": date.today().isoformat()
            }
        }

        # 验证国内网站
        url_cn = random.choice(self.config.get("main.test_url_cn", [
            "https://connect.rom.miui.com/generate_204",
            "https://www.qualcomm.cn/generate_204"
        ]))  # 避免总是使用同一个服务

        cn_success, cn_response_time, detected_type_cn = self.check_proxy_single(
            proxy, url_cn,self.config.get("main.timeout_cn", 6), 1, proxy_type
        )

        # 验证国际网站
        url_intl = random.choice(self.config.get("main.test_url_intl",[
            "https://www.google.com/generate_204",
            "https://mail.google.com/generate_204",
            "https://play.google.com/generate_204",
            "https://accounts.google.com/generate_204"
        ]))  # 避免总是使用同一个服务

        intl_success, intl_response_time, detected_type_intl = self.check_proxy_single(
            proxy, url_intl, self.config.get("main.timeout_intl",10), 1, proxy_type
        )

        # 添加new_ip_info的类型
        # 如果两种个都不是unknown
        if (detected_type_cn != "unknown") and (detected_type_intl != "unknown"):
            # 如果是两种类型
            if detected_type_cn != detected_type_intl:
                # 都加上
                new_ip_info["types"].append(detected_type_cn)
                new_ip_info["types"].append(detected_type_intl)
            else:
                # 随便加一个,毕竟都已排除unknown且两个一样
                new_ip_info["types"].append(detected_type_cn)
        # 只有一个成功获取
        elif (detected_type_cn != "unknown") or (detected_type_intl != "unknown"):
            new_ip_info["types"].append(detected_type_cn if detected_type_cn != "unknown" else detected_type_intl)
        # 都没有就不添加

        # 添加支持范围
        new_ip_info["support"]["china"] = cn_success
        new_ip_info["support"]["international"] = intl_success

        # 透明代理检测(只在代理有效且需要检测时进行)
        is_transparent = False
        detected_ip = "unknown"
        if (self.config.get("main.check_transparent", "true").lower() == "true") and (cn_success or intl_success):
            for type_ in new_ip_info["types"]:
                own_ip = self.config.get("main.own_ip","27.218.2.248")   # CHANGEOFTEN 默认值须经常改
                check_status, transparent, detected_ip = self.check_transparent_proxy(proxy, type_, own_ip)
                if check_status:  # 当检查成功时
                    is_transparent = transparent
                    break  # 在有多种类型时,只要一次成功就不用继续了,防止做无用功
        # 添加透明检测结果
        new_ip_info["transparent"] = is_transparent
        new_ip_info["detected_ip"] = detected_ip

        # 其他信息获取(只在代理有效,没有信息且需要检测时进行)
        other_info = {}
        if (self.config.get("main.get_ip_info","true").lower() == "true") and (cn_success or intl_success) and (
                already_have_info[proxy] == 0):
            # 获取ip其他信息
            for type_ in new_ip_info["types"]:
                info = self.get_ip_info(proxy, type_)
                if info != "unknown":
                    other_info = info
                    break  # 在有多种类型时,只要一次成功就不用继续了,防止做无用功
            # 添加服务器信息
            new_ip_info["location"]["city"] = other_info.get("city", "unknown")
            new_ip_info["location"]["region"] = other_info.get("region", "unknown")
            new_ip_info["location"]["country"] = other_info.get("country", "unknown")
            new_ip_info["location"]["loc"] = other_info.get("loc", "unknown")
            new_ip_info["location"]["org"] = other_info.get("org", "unknown")
            new_ip_info["location"]["postal"] = other_info.get("postal", "unknown")
            new_ip_info["location"]["timezone"] = other_info.get("timezone", "unknown")

        elif (self.config.get("main.get_ip_info","true").lower() == "true") and (cn_success or intl_success) and (
                already_have_info[proxy] == 1):
            new_ip_info["location"]["city"] = "already_have_info"
            new_ip_info["location"]["region"] = "already_have_info"
            new_ip_info["location"]["country"] = "already_have_info"
            new_ip_info["location"]["loc"] = "already_have_info"
            new_ip_info["location"]["org"] = "already_have_info"
            new_ip_info["location"]["postal"] = "already_have_info"
            new_ip_info["location"]["timezone"] = "already_have_info"
        # 其他情况会默认unknown

        # 计算平均响应时间(只计算成功的请求，并与历史数据加权平均)
        current_success_times = []
        if cn_success:
            current_success_times.append(cn_response_time)
        if intl_success:
            current_success_times.append(intl_response_time)

        if current_success_times:
            current_avg = sum(current_success_times) / len(current_success_times)
            # 如果提供了历史数据，进行加权平均（当前测试权重0.3，历史数据权重0.7）
            if avg_response_time > 0:
                new_ip_info["performance"]["avg_response_time"] = current_avg * 0.3 + avg_response_time * 0.7
            else:
                new_ip_info["performance"]["avg_response_time"] = current_avg
        else:
            # 如果当前测试都失败，使用历史数据
            new_ip_info["performance"]["avg_response_time"] = avg_response_time if avg_response_time > 0 else -1

        # 计算成功率(当前测试与历史数据加权平均)
        current_success_rate = sum([cn_success, intl_success]) / 2.0
        # 加权平均（当前测试权重0.3，历史数据权重0.7）
        new_ip_info["performance"]["success_rate"] = current_success_rate * 0.3 + success_rate * 0.7

        return new_ip_info

    # 批量检查代理IP列表(双重验证+透明代理检测)
    def check_proxies_batch(self, proxies, already_have_info, proxy_types, avg_response_time_dict=None,
                            success_rate_dict=None, max_workers=100, check_type="new"):
        """
        批量检查代理IP列表
        双重验证,验证百度和谷歌
        透明代理检测

        :param proxies: 代理字典 {proxy: score}
        :param already_have_info: 代理是否已有信息 {proxy: 0/1}
        :param proxy_types: 代理类型字典 {proxy: type}
        :param avg_response_time_dict: 代理平均响应时间字典
        :param success_rate_dict: 代理平均响应成功率字典
        :param max_workers: 最大并发量
        :param check_type: "new" 新代理 / "existing" 已有代理
        :return: updated_proxies, updated_info
        """

        updated_proxies = {}
        updated_info = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_proxy = {}
            for proxy in proxies:
                if signal_manager.is_interrupted():
                    break

                # 对于已有代理，使用文件中记录的类型；对于新代理，先看是否指定,否则使用自动检测
                if check_type == "existing" and proxy in proxy_types:
                    proxy_type = proxy_types[proxy]
                    if (avg_response_time_dict is not None) and (success_rate_dict is not None):
                        avg_response_time = avg_response_time_dict[proxy]
                        success_rate = success_rate_dict[proxy]
                    else:
                        success_rate = 0.5  # 初始化0.5
                        avg_response_time = -1  # 初始化-1
                else:
                    proxy_type = proxy_types.get(proxy, "auto")  # 从传入的类型字典获取
                    success_rate = 0.5  # 初始化时0.5
                    avg_response_time = -1  # 初始化时-1 - 即没有测过

                future = executor.submit(self.check_proxy_dual, proxy, already_have_info, proxy_type, avg_response_time,
                                         success_rate)
                future_to_proxy[future] = proxy

            for future in concurrent.futures.as_completed(future_to_proxy):
                if signal_manager.is_interrupted():
                    # 取消所有未完成的任务
                    for f in future_to_proxy:
                        f.cancel()
                    break

                proxy = future_to_proxy[future]
                try:
                    new_ip_info = future.result()

                    # 计算分数和更新逻辑
                    current_score = proxies.get(proxy, 1)

                    if new_ip_info["location"]["city"] == "unknown":
                        get_info = "failed"
                    elif new_ip_info["location"]["city"] == "already_have_info":
                        get_info = "already_have_info"
                    else:
                        get_info = "success"

                    if check_type == "new":
                        # 新代理：只要通过任一测试就98分
                        if new_ip_info["support"]["china"] or new_ip_info["support"]["international"]:
                            updated_proxies[proxy] = 98
                            # 透明代理警告
                            transparent_warning = " | [warning] transparent" if new_ip_info["transparent"] else ""
                            print(
                                f"✅[success] {proxy} | type:{new_ip_info['types']} | China:{'pass' if new_ip_info['support']['china'] else 'fail'} | International:{'pass' if new_ip_info['support']['international'] else 'fail'} | get_info:{get_info}{transparent_warning}")
                        else:
                            updated_proxies[proxy] = 0
                            print(f"❌[failed] {proxy}")
                    else:
                        # 已有代理：根据测试结果调整分数
                        if new_ip_info["support"]["china"] and new_ip_info["support"]["international"]:
                            # 两次都通过，加2分
                            updated_proxies[proxy] = min(current_score + 2,self.config.get("main.max_score",100))
                            transparent_warning = " | [warning] transparent" if new_ip_info['transparent'] else ""
                            print(
                                f"✅[success] {proxy} | type:{new_ip_info['types']} | China:pass | International:pass | score:{current_score}->{updated_proxies[proxy]} | get_info:{get_info}{transparent_warning}")
                        elif new_ip_info["support"]["china"] or new_ip_info["support"]["international"]:
                            # 只通过一个，加1分
                            updated_proxies[proxy] = min(current_score + 1, self.config.get("main.max_score",100))
                            status = "China:pass | International:fail" if new_ip_info["support"][
                                "china"] else "China:fail | International:pass"
                            transparent_warning = " | [warning] transparent" if new_ip_info["transparent"] else ""
                            print(
                                f"✅[success] {proxy} | type:{new_ip_info['types']} | {status} | score: {current_score}->{updated_proxies[proxy]} | get_info:{get_info}{transparent_warning}")
                        else:
                            # 两个都不通过，减1分
                            updated_proxies[proxy] = max(0, current_score - 1)
                            print(
                                f"❌[failed] {proxy} | type:{new_ip_info['types']} | China:fail | International:fail | score:{current_score}->{updated_proxies[proxy]}")

                    # 记录
                    updated_info[proxy] = new_ip_info

                except Exception as e:
                    if not signal_manager.is_interrupted():
                        # 只有不是中断引起的异常才打印
                        print(f"❌[error] {proxy} - {str(e)}")

                    if check_type == "existing" and proxy in proxies:
                        updated_proxies[proxy] = max(0, proxies[proxy] - 1)
                    else:
                        updated_proxies[proxy] = 0

                    # 创建默认的错误信息
                    updated_info[proxy] = {
                        "types": ["http"],
                        "support": {"china": False, "international": False},
                        "transparent": False,
                        "detected_ip": "unknown",
                        "location": {"city": "unknown", "region": "unknown", "country": "unknown",
                                     "loc": "unknown", "org": "unknown", "postal": "unknown", "timezone": "unknown"},
                        "performance": {
                            "avg_response_time": -1,
                            "success_rate": 0.3,
                            "last_checked": date.today().isoformat()
                        }
                    }

        return updated_proxies, updated_info

    # 验证新代理
    def validate_new_proxies(self, new_proxies: List[str], proxy_type: str = "auto",
                             from_interrupt: bool = False, source: str = "crawl"):
        """验证新代理（支持中断恢复和透明代理检测）"""
        signal_manager.clear_interrupt()   # 清除中断状态（开始新任务前）

        if not new_proxies:
            print("[failed] 没有代理需要验证")
            return

        # PERF: 初始化本机ip,用于透明代理检测(防止每个验证都重新获取,这样一轮一次)
        if self.config.get("main.check_transparent","true").lower() == "true":
            print("[info] 启用透明代理检测")
            self.get_own_ip()

        # 根据来源选择中断文件(爬取中断/加载中断)
        interrupt_file_name = self.config.get("interrupt.interrupt_file_crawl","interrupted_crawl_proxies.csv") if source == "crawl" else \
            self.config.get("interrupt.interrupt_file_load","interrupted_load_proxies.csv")
        interrupt_file = str(os.path.join(
            self.config.get("interrupt.interrupt_dir","interrupt"), interrupt_file_name)
        )
        original_count = len(new_proxies)
        print(f"[start] 共加载 {original_count} 个新代理，使用{proxy_type}类型开始双重测试...")

        # 保存初始状态到中断文件（如果不是从中断恢复的）
        if not from_interrupt:
            self.interrupt.save_interrupted_proxies(new_proxies, proxy_type, original_count, interrupt_file, from_browser=False)
            print(f"[file] 已创建中断恢复文件: {interrupt_file_name}")

        # 新代理初始分数为0
        new_proxies_dict = {proxy: 0 for proxy in new_proxies}
        new_types_dict = {proxy: proxy_type for proxy in new_proxies}
        # 都没有信息
        already_have_info = {proxy: 0 for proxy in new_proxies}

        try:
            updated_proxies, updated_info = self.check_proxies_batch(
                new_proxies_dict, already_have_info, new_types_dict, None, None,
                self.config.get("main.max_workers",100), check_type="new"
            )

            if signal_manager.is_interrupted():
                # 计算剩余未验证的代理
                verified_proxies = set(updated_proxies.keys())
                remaining_proxies = [proxy for proxy in new_proxies if proxy not in verified_proxies]

                # 保存已验证的代理
                existing_proxies, existing_info = self.database.load_proxies_from_db()
                for proxy, score in updated_proxies.items():
                    if proxy not in existing_proxies or existing_proxies[proxy] < score:
                        info = {  # 新代理的初始模板
                            "types": updated_info[proxy]["types"],
                            "support": {
                                "china": updated_info[proxy]["support"]["china"],
                                "international": updated_info[proxy]["support"]["international"]
                            },
                            "transparent": updated_info[proxy]["transparent"],
                            "detected_ip": updated_info[proxy]["detected_ip"],
                            "location": {
                                "city": updated_info[proxy]["location"]["city"],
                                "region": updated_info[proxy]["location"]["region"],
                                "country": updated_info[proxy]["location"]["country"],
                                "loc": updated_info[proxy]["location"]["loc"],
                                "org": updated_info[proxy]["location"]["org"],
                                "postal": updated_info[proxy]["location"]["postal"],
                                "timezone": updated_info[proxy]["location"]["timezone"]
                            },
                            "browser": {
                                "valid": False,
                                "check_date": "unknown",
                                "response_time": -1
                            },
                            "security": {
                                "dns_hijacking": "unknown",
                                "ssl_valid": "unknown",
                                "malicious_content": "unknown",
                                "check_date": "unknown"
                            },
                            "performance": {
                                "avg_response_time": updated_info[proxy]["performance"]["avg_response_time"],
                                "success_rate": updated_info[proxy]["performance"]["success_rate"],
                                "last_checked": date.today().isoformat()
                            }
                        }
                        existing_proxies[proxy] = score
                        existing_info[proxy] = info

                self.database.save_valid_proxies(existing_proxies, existing_info)

                # 更新中断文件
                if remaining_proxies:
                    self.interrupt.save_interrupted_proxies(remaining_proxies, proxy_type, original_count, interrupt_file)
                    print(
                        f"\n[pause] 验证已中断！已保存 {len(verified_proxies)} 个代理到代理池，剩余 {len(remaining_proxies)} 个代理待验证")
                    print(f"[file] 中断文件已更新: {interrupt_file_name}")
                else:
                    self.interrupt.delete_interrupt_file(interrupt_file)
                    print(f"\n[success] 验证完成！所有代理已验证并保存")
                return

            # 正常完成验证
            # 合并到现有代理池
            existing_proxies, existing_info = self.database.load_proxies_from_db()
            for proxy, score in updated_proxies.items():
                if proxy not in existing_proxies or existing_proxies[proxy] < score:
                    info = {  # 新代理的初始模板
                        "types": updated_info[proxy]["types"],
                        "support": {
                            "china": updated_info[proxy]["support"]["china"],
                            "international": updated_info[proxy]["support"]["international"]
                        },
                        "transparent": updated_info[proxy]["transparent"],
                        "detected_ip": updated_info[proxy]["detected_ip"],
                        "location": {
                            "city": updated_info[proxy]["location"]["city"],
                            "region": updated_info[proxy]["location"]["region"],
                            "country": updated_info[proxy]["location"]["country"],
                            "loc": updated_info[proxy]["location"]["loc"],
                            "org": updated_info[proxy]["location"]["org"],
                            "postal": updated_info[proxy]["location"]["postal"],
                            "timezone": updated_info[proxy]["location"]["timezone"]
                        },
                        "browser": {
                            "valid": False,
                            "check_date": "unknown",
                            "response_time": -1
                        },
                        "security": {
                            "dns_hijacking": "unknown",
                            "ssl_valid": "unknown",
                            "malicious_content": "unknown",
                            "check_date": "unknown"
                        },
                        "performance": {
                            "avg_response_time": updated_info[proxy]["performance"]["avg_response_time"],
                            "success_rate": updated_info[proxy]["performance"]["success_rate"],
                            "last_checked": updated_info[proxy]["performance"]["last_checked"]
                        }
                    }
                    existing_proxies[proxy] = score
                    existing_info[proxy] = info

            self.database.save_valid_proxies(existing_proxies, existing_info)

            # 删除中断文件
            self.interrupt.delete_interrupt_file(interrupt_file)

            # 统计结果
            success_count = sum(1 for score in updated_proxies.values() if score == 98)
            china_only = sum(1 for proxy in updated_proxies if
                             updated_info[proxy]["support"]["china"] and not updated_info[proxy]["support"][
                                 "international"])
            intl_only = sum(1 for proxy in updated_proxies if
                            not updated_info[proxy]["support"]["china"] and updated_info[proxy]["support"][
                                "international"])
            both_support = sum(1 for proxy in updated_proxies if
                               updated_info[proxy]["support"]["china"] and updated_info[proxy]["support"][
                                   "international"])
            transparent_count = sum(1 for proxy in updated_proxies if updated_info[proxy]["transparent"])

            print(f"\n[success] 验证完成!")
            print(f"成功代理: {success_count}/{original_count}")
            print(f"仅支持国内: {china_only} | 仅支持国际: {intl_only} | 双支持: {both_support}")
            print(f"透明代理: {transparent_count} 个")
            print(f"代理池已更新至: {self.config.get("main.db_file","./data/proxies.db")}")

        except Exception as e:
            if not signal_manager.is_interrupted():
                print(f"[error] 验证过程中发生错误: {str(e)}")

    # 加载验证已有代理池中的代理
    def validate_existing_proxies(self):
        """验证已有代理池中的代理（中断恢复和透明代理检测）"""
        signal_manager.clear_interrupt()   # 清除中断状态

        proxies_to_validate = None

        interrupt_file = str(os.path.join(self.config.get("interrupt.interrupt_dir", "interrupt"),
                                          self.config.get("interrupt.interrupt_file_existing",
                                                          "interrupted_existing_proxies.csv"))
                             )

        # 首先检查是否有中断记录
        from_interrupt, remaining_proxies, type_or_config, original_count = self.interrupt.check_interrupted_records(
            interrupt_file
        )
        if (from_interrupt == False) and (remaining_proxies == "return"):  # 返回上级菜单
            return

        elif from_interrupt and remaining_proxies:  # 选择恢复,且有剩余
            proxies_to_validate = remaining_proxies
            original_count = original_count  # 选择更新后的数量

        elif (from_interrupt == False) and (remaining_proxies is None):  # 选择不恢复
            self.interrupt.delete_interrupt_file(interrupt_file)
            proxies_to_validate = None  # 重新加载所有代理

        print(f"[info] 开始验证已有代理，文件：{self.config.get("main.db_file", "./data/proxies.db")}...")

        # PERF: 初始化本机ip,用于透明代理检测(防止每个验证都重新获取,这样一轮一次)
        if self.config.get("main.check_transparent", "true").lower() == "true":
            self.get_own_ip()
            print("[info] 启用透明代理检测")

        # 加载代理池
        all_proxies, proxy_info = self.database.load_proxies_from_db()

        if proxies_to_validate is None:
            # 重新验证所有代理
            proxies_to_validate = list(all_proxies.keys())
            original_count = len(proxies_to_validate)

        if not proxies_to_validate:
            print("[failed] 没有代理需要验证")
            return

        print(f"[start] 共加载 {len(proxies_to_validate)} 个代理，开始测试...")

        # 保存初始状态到中断文件
        self.interrupt.save_interrupted_proxies(
            proxies_to_validate, "already_have", original_count, interrupt_file
        )
        print(
            f"[file] 已创建中断恢复文件: {self.config.get("interrupt.interrupt_file_existing", "interrupted_existing_proxies.csv")}")

        try:
            # 从代理池中获取当前分数和类型
            proxies_dict = {proxy: all_proxies[proxy] for proxy in proxies_to_validate}
            types_dict = {}
            already_have_info = {}
            avg_response_time_dict = {}
            success_rate_dict = {}

            for proxy in proxies_to_validate:
                # 使用types列表中的第一个类型，如果没有则用"auto"
                if proxy in proxy_info and proxy_info[proxy].get("types"):
                    types_dict[proxy] = proxy_info[proxy]["types"][0]
                else:
                    types_dict[proxy] = "auto"

                # 获取性能数据
                if proxy in proxy_info:
                    avg_response_time_dict[proxy] = proxy_info[proxy].get("performance", {}).get(
                        "avg_response_time",
                        -1)
                    success_rate_dict[proxy] = proxy_info[proxy].get("performance", {}).get("success_rate", 0.5)
                else:
                    avg_response_time_dict[proxy] = -1
                    success_rate_dict[proxy] = 0.5

                # 是否已有信息
                if proxy in proxy_info:
                    have_info = proxy_info[proxy].get("location", {}).get("city", "unknown") == "unknown"
                    # 没有时
                    if have_info:
                        already_have_info[proxy] = 0
                    # 已有信息
                    else:
                        already_have_info[proxy] = 1

            updated_proxies, updated_info = self.check_proxies_batch(
                proxies_dict, already_have_info, types_dict, avg_response_time_dict, success_rate_dict,
                self.config.get("main.max_workers", 100), "existing"
            )

            # 中断
            if signal_manager.is_interrupted():
                # 计算剩余未验证的代理
                verified_proxies = set(updated_proxies.keys())
                remaining_proxies = [proxy for proxy in proxies_to_validate if proxy not in verified_proxies]

                # 更新已验证的代理分数和支持范围
                for proxy, score in updated_proxies.items():
                    all_proxies[proxy] = score
                    if updated_info[proxy]["types"]:  # 有type即表示代理可用,只有可用才修改
                        proxy_info[proxy]["types"] = list(set(proxy_info[proxy]["types"] + updated_info[proxy]["types"]))  # 添加新的类型,并去重
                        proxy_info[proxy]["support"]["china"] = updated_info[proxy]["support"]["china"]
                        proxy_info[proxy]["support"]["international"] = updated_info[proxy]["support"]["international"]
                        proxy_info[proxy]["transparent"] = updated_info[proxy]["transparent"]
                        proxy_info[proxy]["detected_ip"] = updated_info[proxy]["detected_ip"]

                        # 只修改信息未知的代理,因为已知道的没有进行验证,不使用already_have_info字段判断是因为太麻烦,这个可以达到同样效果
                        if proxy_info[proxy]["location"]["city"] == "unknown":
                            proxy_info[proxy]["location"]["city"] = updated_info[proxy]["location"]["city"]
                            proxy_info[proxy]["location"]["region"] = updated_info[proxy]["location"]["region"]
                            proxy_info[proxy]["location"]["country"] = updated_info[proxy]["location"]["country"]
                            proxy_info[proxy]["location"]["loc"] = updated_info[proxy]["location"]["loc"]
                            proxy_info[proxy]["location"]["org"] = updated_info[proxy]["location"]["org"]
                            proxy_info[proxy]["location"]["postal"] = updated_info[proxy]["location"]["postal"]
                    # 这三项每次都要改
                    proxy_info[proxy]["performance"]["avg_response_time"] = updated_info[proxy]["performance"]["avg_response_time"]
                    proxy_info[proxy]["performance"]["success_rate"] = updated_info[proxy]["performance"]["success_rate"]
                    proxy_info[proxy]["performance"]["last_checked"] = updated_info[proxy]["performance"]["last_checked"]

                # 保存更新后的代理池
                self.database.save_valid_proxies(all_proxies, proxy_info)

                # 更新中断文件
                if remaining_proxies:
                    self.interrupt.save_interrupted_proxies(remaining_proxies, "already_have", original_count,
                                                            interrupt_file)
                    print(
                        f"\n[pause] 验证已中断！已更新 {len(verified_proxies)} 个代理，剩余 {len(remaining_proxies)} 个代理待验证")
                    print(
                        f"[file] 中断文件已更新: {self.config.get("interrupt.interrupt_file_existing", "interrupted_existing_proxies.csv")}")
                else:
                    self.interrupt.delete_interrupt_file(interrupt_file)
                    print(f"\n[success] 验证完成！所有代理已更新")
                return

            # 正常完成验证
            # 更新所有代理分数和支持范围
            for proxy, score in updated_proxies.items():
                all_proxies[proxy] = score
                if updated_info[proxy]["types"]:  # 有type即表示代理可用,只有可用才修改
                    proxy_info[proxy]["types"] = list(set(proxy_info[proxy]["types"] + updated_info[proxy]["types"]))  # 添加新的类型,并去重
                    proxy_info[proxy]["support"]["china"] = updated_info[proxy]["support"]["china"]
                    proxy_info[proxy]["support"]["international"] = updated_info[proxy]["support"]["international"]
                    proxy_info[proxy]["transparent"] = updated_info[proxy]["transparent"]
                    proxy_info[proxy]["detected_ip"] = updated_info[proxy]["detected_ip"]

                    # 只修改信息未知的代理,因为已知道的没有进行验证,不传递并使用already_have_info字段是因为太麻烦,这个可以达到同样效果
                    if proxy_info[proxy]["location"]["city"] == "unknown":
                        proxy_info[proxy]["location"]["city"] = updated_info[proxy]["location"]["city"]
                        proxy_info[proxy]["location"]["region"] = updated_info[proxy]["location"]["region"]
                        proxy_info[proxy]["location"]["country"] = updated_info[proxy]["location"]["country"]
                        proxy_info[proxy]["location"]["loc"] = updated_info[proxy]["location"]["loc"]
                        proxy_info[proxy]["location"]["org"] = updated_info[proxy]["location"]["org"]
                        proxy_info[proxy]["location"]["postal"] = updated_info[proxy]["location"]["postal"]
                # 这三项每次都要改
                proxy_info[proxy]["performance"]["avg_response_time"] = updated_info[proxy]["performance"]["avg_response_time"]
                proxy_info[proxy]["performance"]["success_rate"] = updated_info[proxy]["performance"]["success_rate"]
                proxy_info[proxy]["performance"]["last_checked"] = updated_info[proxy]["performance"]["last_checked"]

            # 保存更新后的代理池
            self.database.save_valid_proxies(all_proxies, proxy_info)

            # 删除中断文件
            self.interrupt.delete_interrupt_file(interrupt_file)

            # 最终统计
            final_count = sum(1 for score in updated_proxies.values() if score > 0)
            china_only = sum(1 for proxy in proxies_to_validate if
                             updated_info[proxy]["support"]["china"] and not updated_info[proxy]["support"]["international"])
            intl_only = sum(1 for proxy in proxies_to_validate if
                            not updated_info[proxy]["support"]["china"] and updated_info[proxy]["support"]["international"])
            both_support = sum(1 for proxy in proxies_to_validate if
                               updated_info[proxy]["support"]["china"] and updated_info[proxy]["support"]["international"])
            transparent_count = sum(1 for proxy in proxies_to_validate if updated_info[proxy]["transparent"])

            print(f"\n[success] 验证完成! 剩余有效代理: {final_count}/{original_count}")
            print(f"仅支持国内: {china_only} | 仅支持国际: {intl_only} | 双支持: {both_support}")
            print(f"[warning]  透明代理: {transparent_count} 个")
            print(f"已移除 {original_count - final_count} 个无效代理")

        except Exception as e:
            if not signal_manager.is_interrupted():
                print(f"[error] 验证过程中发生错误: {str(e)}")