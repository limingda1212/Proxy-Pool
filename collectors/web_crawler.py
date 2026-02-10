# -*- coding: utf-8 -*-
# 网页爬虫

import requests
import re
import time
import sys
import asyncio
import aiohttp
from typing import List, Tuple, Optional

from core.config import ConfigManager
from data.settings import HEADERS,GITHUB_PROXY_SOURCES
from utils.helpers import filter_proxies

class WebCrawler:
    def __init__(self, config: ConfigManager):
        self.config = config

    def scrape_html_proxies(self, url: str, regex_pattern: str,
                            capture_groups: List[str]) -> List[str]:
        """
        :param url: 请求地址
        :param regex_pattern: re解析式，用于解析爬取结果
        :param capture_groups: 要返回的re中的值，[IpName, Port]
        :return: [proxy: port]
        """
        extracted_data = []
        encoding = "utf-8"
        try:
            response = requests.get(url=url, headers=HEADERS, timeout=self.config.get("main.timeout_cn",6))
            if response.status_code == 200:  # 判断状态码
                response.encoding = encoding  # 使用utf-8
                regex = re.compile(regex_pattern, re.S)  # 创建一个re对象
                matches = regex.finditer(response.text)  # 对获取的东西进行解析
                for match in matches:
                    for group_name in capture_groups:  # 依次输出参数capture_groups中的指定内容
                        extracted_data.append(f"{match.group(group_name)}")
                proxy_list = [f"{extracted_data[i].strip()}:{extracted_data[i + 1].strip()}" for i in
                              range(0, len(extracted_data), 2)]  # 整合列表为[proxy:port]
                response.close()
                return proxy_list
            else:
                print(f"\n[failed] 爬取失败,状态码{response.status_code}")  # 前面的\n防止与进度条混在一行
                return []

        except Exception as e:
            print(f"\n[error] 爬取错误: {str(e)}")
            return []

    def scrape_github_proxies(self,choice: str):
        """
        从 GitHub raw 文件爬取代理
        处理 GitHub 代理源的通用函数
        :param choice: 用户选择的编号
        :return: 代理列表, 代理类型
        """
        source = GITHUB_PROXY_SOURCES.get(choice)
        if not source:
            return None, None

        print(f'\n[info] 爬取: {source["name"]}')
        print(f'URL: {source["url"]}')
        print('[start]')

        error_count = 0

        try:
            response = requests.get(source["url"], headers=HEADERS)
            if response.status_code == 200:
                if source["cleanup"]:
                    # 清理格式如 ip:port:country:type 的行
                    text = re.sub(r':\D.*?\n', '\n', response.text)
                    lines = text.split("\n")
                else:
                    lines = response.text.split("\n")

                proxy_list = [line.strip() for line in lines if line.strip()]

            else:
                print(f"\n[failed] 爬取失败,状态码{response.status_code}")
                proxy_list = []
        except Exception as e:
            print(f"\n[error] 爬取错误: {str(e)}")
            proxy_list = []

        if proxy_list:
            print(f'100%|████████████████████████████████████████| 1/1  错误数:{error_count}')
            print(f'[info] 爬取到 {len(proxy_list)} 个代理')
            print('\n[end] 爬取完成!')
            return proxy_list, source["type"]
        else:
            error_count = 1
            print(f'100%|████████████████████████████████████████| 1/1  错误数:{error_count}')
            print('\n[failed] 爬取失败')
            return proxy_list, source["type"]

    def crawl_proxies(self) -> Tuple[Optional[List[str]], Optional[str]]:
        """爬取免费代理"""

        print("""[info] 已创建的可爬网站
        1 ：https://proxy5.net/cn/free-proxy/china
              备注:被封了,成功率 40%
        2 ：https://www.89ip.cn/
              备注:240个,成功率 10%
        3 ：https://cn.freevpnnode.com/
              备注:30个,成功率 3%
        4 ：https://www.kuaidaili.com/free/inha/ 
              备注:7600多页,成功率 5%
        5 ：http://www.ip3366.net/
              备注:100个,成功率 1%
        6 ：https://proxypool.scrape.center/random
              备注:随机的,成功率 40%
        7 ：https://proxy.scdn.io/text.php
              备注:12000多个,成功率 30%
        8 ：https://proxyhub.me/zh/cn-http-proxy-list.html
              备注:20个,成功率 0%
        --- GitHub 代理源 ---
        9 : databay-labs HTTP
              备注:大约3000个,成功率 15%
        10: databay-labs SOCKS5
              备注:大约2000个,成功率 10%
        11: databay-labs HTTPS
              备注:大约3000个,成功率 10%
        12: hideip.me HTTP
              备注:大约1000个,成功率 20%
        13: hideip.me HTTPS
              备注:大约1000个,成功率 0%
        14: hideip.me SOCKS4
              备注:大约100个,成功率 30%
        15: hideip.me SOCKS5
              备注:大约50个,成功率 30% 
        16: r00tee HTTPS
              备注:大约50000个,成功率 0.001%
        17: r00tee SOCKS4
              备注:大约50000个,成功率 0.001%
        18: r00tee SOCKS5
              备注:大约4000个,成功率 0.01%

        输入其他：退出
        """)
        scraper_choice = input("[input] 选择：").strip()
        all_proxies = []  # 存储所有爬取的代理
        by_type = 'auto'  # 通过指定类型验证,默认为auto

        if scraper_choice == "1":
            print('\n[info] 爬取:https://proxy5.net/cn/free-proxy/china')
            print('[start]')

            error_count = 0
            '''
            <tr>.*?<td><strong>(?P<ip>.*?)</strong></td>.*?<td>(?P<port>.*?)</td>.*?</tr>
            '''
            proxy_list = self.scrape_html_proxies('https://proxy5.net/cn/free-proxy/china',
                                             "<tr>.*?<td><strong>(?P<ip>.*?)</strong></td>.*?<td>(?P<port>.*?)</td>.*?</tr>",
                                             ["ip", "port"])

            if proxy_list:
                all_proxies.extend(proxy_list)
            else:
                error_count += 1
            print(f'100%|██████████████████████████████████████████████████| 1/1  错误数:{error_count}')
            print('\n[end] 爬取完成!')

        elif scraper_choice == "2":
            print('\n[info] 爬取:https://www.89ip.cn/')
            print('[start]')

            error_count = 0
            total_pages = 6
            for page in range(1, total_pages + 1):
                if page == 1:
                    url = 'https://www.89ip.cn/'
                else:
                    url = f'https://www.89ip.cn/index_{page}.html'

                proxy_list = self.scrape_html_proxies(url,
                                                 "<tr>.*?<td>(?P<ip>.*?)</td>.*?<td>(?P<port>.*?)</td>.*?</tr>",
                                                 ["ip", "port"])
                if proxy_list:
                    all_proxies.extend(proxy_list)
                else:
                    error_count += 1

                time.sleep(1)

                # 计算进度百分比
                percent = page * 100 // total_pages
                # 计算进度条长度
                completed = page * 50 // total_pages
                remaining = 50 - completed
                # 处理百分比显示的对齐
                if percent < 10:
                    padding = "  "
                elif percent < 100:
                    padding = " "
                else:
                    padding = ""
                # 更新进度条
                print(
                    f"\r{percent}%{padding}|{'█' * completed}{'-' * remaining}| {page}/{total_pages}  错误数:{error_count}",
                    end="")
                sys.stdout.flush()
            print('\n\n[end] 爬取完成!')

        elif scraper_choice == "3":
            print('\n[info] 爬取:https://cn.freevpnnode.com/')
            error_count = 0
            print('[start]')
            proxy_list = self.scrape_html_proxies("https://cn.freevpnnode.com/",
                                             '<tr>.*?<td>(?P<ip>.*?)</td>.*?<td>(?P<port>.*?)</td>.*?<td><span>.*?</span> <img src=".*?" width="20" height="20" .*? class="js_openeyes"></td>.*?</td>',
                                             ["ip", "port"])
            if proxy_list:
                all_proxies.extend(proxy_list)
            else:
                error_count += 1
            print(f'100%|██████████████████████████████████████████████████| 1/1  错误数:{error_count}')
            print('\n[end] 爬取完成!')

        elif scraper_choice == "4":
            print('[info] 爬取:https://www.kuaidaili.com/free/inha/')
            error_count = 0
            try:
                print('[info] 信息:共约7000页,建议一次爬取数量不大于500页,防止被封')
                start_page = int(input('[input] 爬取起始页（整数）：').strip())
                end_page = int(input("[input] 爬取结束页（整数）:").strip())
                if end_page < 1 or start_page < 1 or end_page > 7000 or start_page > 7000 or start_page > end_page:
                    print("[error] 不能小于1或大于7000,起始页不能大于结束页")
                    return None, None

                print('[start]')

                for page in range(start_page, end_page + 1):

                    proxy_list = self.scrape_html_proxies(f"https://www.kuaidaili.com/free/inha/{page}/",
                                                     '{"ip": "(?P<ip>.*?)", "last_check_time": ".*?", "port": "(?P<port>.*?)", "speed": .*?, "location": ".*?"}',
                                                     ["ip", "port"])
                    if proxy_list:
                        all_proxies.extend(proxy_list)
                    else:
                        error_count += 1

                    time.sleep(2)

                    # 计算进度百分比
                    current_page = page - start_page + 1
                    total_pages = end_page - start_page + 1
                    percent = current_page * 100 // total_pages
                    # 计算进度条长度
                    completed = current_page * 50 // total_pages
                    remaining = 50 - completed
                    # 处理百分比显示的对齐
                    if percent < 10:
                        padding = "  "
                    elif percent < 100:
                        padding = " "
                    else:
                        padding = ""
                    # 更新进度条
                    print(
                        f"\r{percent}%{padding}|{'█' * completed}{'-' * remaining}| {current_page}/{total_pages}  错误数:{error_count}",
                        end="")
                    sys.stdout.flush()
                print('\n\n[end] 爬取完成!')
            except:
                print("[error] 输入错误，请输入整数")
                return None, None

        elif scraper_choice == "5":
            print('\n[info] 爬取:http://www.ip3366.net/?stype=1')
            print('[start]')

            total_pages = 7
            error_count = 0
            for page in range(1, total_pages + 1):
                proxy_list = self.scrape_html_proxies(f'http://www.ip3366.net/?stype=1&page={page}',
                                                 '<tr>.*?<td>(?P<ip>.*?)</td>.*?<td>(?P<port>.*?)</td>.*?</tr>',
                                                 ['ip', 'port'])
                if proxy_list:
                    all_proxies.extend(proxy_list)
                else:
                    error_count += 1

                time.sleep(1)

                # 计算进度百分比
                percent = page * 100 // total_pages
                # 计算进度条长度
                completed = page * 50 // total_pages
                remaining = 50 - completed
                # 处理百分比显示的对齐
                if percent < 10:
                    padding = "  "
                elif percent < 100:
                    padding = " "
                else:
                    padding = ""
                # 更新进度条
                print(
                    f"\r{percent}%{padding}|{'█' * completed}{'-' * remaining}| {page}/{total_pages}  错误数:{error_count}",
                    end="")
                sys.stdout.flush()
            print('\n\n[end] 爬取完成!')


        elif scraper_choice == "6":
            print('\n[info] 爬取:https://proxypool.scrape.center/random')
            by_type = "http"
            try:
                count = int(input("[input] 爬取个数(整数)：").strip())

                if count < 1:
                    print("[error] 数量必须大于0")
                    return None, None

                print(f"\n[start] 开始爬取 {count} 个代理...")

                # 异步版本
                async def fetch_proxy(session, url, semaphore):
                    async with semaphore:
                        try:
                            async with session.get(url) as response:
                                if response.status == 200:
                                    proxy = await response.text()
                                    print("[ok] 获取到:", proxy)
                                    return proxy.strip()
                        except Exception as e:
                            return None

                async def fetch_proxies_main():
                    semaphore = asyncio.Semaphore(20)
                    timeout = aiohttp.ClientTimeout(total=50)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        tasks = []
                        for _ in range(count):
                            url = 'https://proxypool.scrape.center/random'
                            task = fetch_proxy(session, url, semaphore)
                            tasks.append(task)
                        results = await asyncio.gather(*tasks, return_exceptions=True)
                        return [r for r in results if r and isinstance(r, str) and ':' in r]

                try:
                    proxies = asyncio.run(fetch_proxies_main())
                    if proxies:
                        all_proxies.extend(proxies)
                except Exception as e:
                    print(f"[error] 异步请求失败: {e}")

            except ValueError:
                print("[error] 输入错误")
                return None, None

        elif scraper_choice == '7':
            print("\n[info] 爬取:https://proxy.scdn.io/text.php")
            print('[start]')

            error_count = 0
            url = 'https://proxy.scdn.io/text.php'
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
                'Referer': 'https://proxy.scdn.io/'
            }
            try:
                response = requests.get(url, headers=headers)
                result = response.text.split("\n")
                proxy_list = []
                for proxy in result:
                    if len(result) == 0:
                        print('[failed] 没有代理可以爬取')
                    else:
                        proxy_list.append(proxy.strip())
                if proxy_list:
                    all_proxies.extend(proxy_list)
                else:
                    error_count += 1
                print(f'100%|██████████████████████████████████████████████████| 1/1  错误数:{error_count}')
                print(f"\n[end] 爬取完成！")
            except Exception as e:
                print(f'[error] 爬取失败: {str(e)}')
                return None, None

        elif scraper_choice == '8':
            print('\n[info] 爬取:https://proxyhub.me/zh/cn-http-proxy-list.html')
            print("[start]")

            error_count = 0
            proxy_list = self.scrape_html_proxies("https://proxyhub.me/zh/cn-http-proxy-list.html",
                                             r'<tr>\s*<td>(?P<ip>\d+\.\d+\.\d+\.\d+)</td>\s*<td>(?P<port>\d+)</td>',
                                             ["ip", "port"])
            if proxy_list:
                all_proxies.extend(proxy_list)
            else:
                error_count += 1
            print(f'100%|██████████████████████████████████████████████████| 1/1  错误数:{error_count}')
            print(f"\n[end] 爬取完成！")

            # GitHub选项统一处理 9-18
        elif scraper_choice in GITHUB_PROXY_SOURCES:
            all_proxies, by_type = self.scrape_github_proxies(scraper_choice)

        else:
            print("[info] 退出爬取")
            return None, None

        return filter_proxies(all_proxies), by_type
