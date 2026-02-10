#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ProxyPool - 高效代理池管理工具
Copyright (C) 2025  李明达

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

Contact: lmd101212@outlook.com
"""

try:
    import re
    import requests
    import concurrent.futures
    import time
    import os
    import sys
    import csv
    import signal
    from playwright.async_api import async_playwright, ProxySettings
    from datetime import date
    import json
    import asyncio
    import random
    import subprocess
    import sqlite3
    from typing import Dict, Any, Union, Callable, Type
    import aiohttp

    from data import settings
except Exception as import_error:
    print(import_error)
    print("导入依赖库失败,部分功能会失效,请安装依赖")

# 全局变量用于中断处理
current_validation_process = None
interrupted = False

# 爬取参数
HEADERS = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0'
}


# MAIN 中断处理 - 通用中断处理
# 创建中断目录
def create_interrupt_dir():
    """创建中断目录"""
    try:
        os.makedirs(load_settings()["interrupt"]["interrupt_dir"], exist_ok=True)
        return True
    except Exception as e:
        return e

# 保存中断时的代理列表
def save_interrupted_proxies(remaining_proxies, type_or_config, original_count, interrupt_file, from_browser=False):
    """保存中断时的代理列表"""
    create_interrupt_dir()
    with open(interrupt_file, 'w', encoding="utf-8", newline='') as file:
        writer = csv.writer(file)
        if from_browser:
            writer.writerow([json.dumps(type_or_config), original_count])
        else:
            writer.writerow([type_or_config, original_count])  # 第一行保存类型和原始数量
        for proxy in remaining_proxies:
            writer.writerow([proxy])

# 筛选中断记录中的代理，移除数据库中已不存在的代理
def filter_interrupted_proxies(remaining_proxies, original_count):
    """
    筛选中断记录中的代理，移除数据库中已不存在的代理

    :param remaining_proxies: 中断记录中的代理列表
    :param original_count: 原始总数
    :return: (筛选后的代理列表, 有效代理数, 被筛除的代理数)
    """
    if not remaining_proxies:
        return [], 0, 0

    print(f"[info] 开始筛选中断记录中的代理...")
    print(f"  中断记录中的代理数: {len(remaining_proxies)}/{original_count}")

    # 从数据库加载现有代理
    existing_proxies = set()
    db_path = current_config["main"]["db_file"]

    if os.path.exists(db_path):
        conn = None
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT proxy FROM proxies WHERE score > 0")  # 只查询分数大于0的代理
            existing_proxies = {row[0].strip() for row in cursor.fetchall() if row[0]}
            print(f"[info] 数据库中现有有效代理数: {len(existing_proxies)}")
        except sqlite3.Error as e:
            print(f"[warning] 读取数据库代理失败: {e}")
        finally:
            if conn:
                conn.close()
    else:
        print(f"[info] 数据库文件不存在，所有中断代理将被忽略")
        return [], 0, len(remaining_proxies)

    # 筛选代理
    valid_proxies = []
    removed_count = 0

    for proxy in remaining_proxies:
        if proxy in existing_proxies:
            valid_proxies.append(proxy)
        else:
            removed_count += 1
            print(f"[warning] 中断记录中的代理 {proxy} 已不存在于数据库，将被移除")

    # 更新原始数量
    new_original_count = original_count - removed_count

    print(f"[success] 中断记录筛选完成!")
    print(f"  有效代理数: {len(valid_proxies)}/{new_original_count}")
    print(f"  被筛除代理: {removed_count} 个")

    if removed_count > 0 and new_original_count <= 0:
        print("[warning] 中断记录中所有代理都已不存在，中断记录将被删除")
        return [], 0, removed_count

    return valid_proxies, new_original_count, removed_count

# 加载中断的代理列表
def load_interrupted_proxies(interrupt_file):
    """加载中断的代理列表"""
    # 如果没有中断记录
    if not os.path.exists(interrupt_file):
        return None, None, None

    try:
        with open(interrupt_file, 'r', encoding="utf-8") as file:
            reader = csv.reader(file)
            first_row = next(reader, None)
            # 如果无效
            if not first_row or len(first_row) < 2:
                return None, None, None

            type_or_config = first_row[0]
            original_count = int(first_row[1])
            remaining_proxies = [row[0] for row in reader if row]
        # 有效并成功读取
        return remaining_proxies, type_or_config, original_count  # 剩余代理,类型,原始数量
    # 失败
    except:
        return None, None, None

# 删除中断文件
def delete_interrupt_file(interrupt_file):
    """删除中断文件"""
    if os.path.exists(interrupt_file):
        os.remove(interrupt_file)

# 信号处理函数，用于捕获Ctrl+C
def signal_handler(signum, frame):
    """信号处理函数，用于捕获Ctrl+C"""
    global interrupted
    interrupted = True
    print("\n\n[warning] 检测到中断信号，正在保存进度...")

# 设置中断处理器
def setup_interrupt_handler():
    """设置中断处理器"""
    global interrupted
    interrupted = False
    try:
        signal.signal(signal.SIGINT, signal_handler)
        return True
    except Exception as e:
        return e

# 检查是否有中断记录
def check_interrupted_records(interrupt_file):
    """
    检查是否有中断记录（增强版，会筛选已不存在的代理）

    y: 加载中断

    n: 删除中断

    其他: 返回上级菜单

    :return: from_interrupt(False/True), 剩余代理(remaining_proxies/'return'/None), 类型或配置(type_or_config/None), 原始数量(original_count/None)
    """
    remaining_proxies, type_or_config, original_count = load_interrupted_proxies(interrupt_file)
    if remaining_proxies:
        print(f"[info] 发现上次中断记录!")
        print(f"   剩余代理: {len(remaining_proxies)}/{original_count} 个")
        print(f"   验证参数: {type_or_config}")

        # 如果是验证已有代理，需要筛选掉数据库中已不存在的代理
        if type_or_config == "already_have":
            print("[info] 正在检查中断记录中的代理是否仍存在于数据库...")
            filtered_proxies, new_original_count, removed_count = filter_interrupted_proxies(
                remaining_proxies, original_count
            )

            # 更新数据
            remaining_proxies = filtered_proxies
            original_count = new_original_count

            if removed_count > 0:
                # 如果所有代理都被筛除，删除中断文件并返回
                if not remaining_proxies:
                    print("[info] 中断记录中所有代理都已不存在，将删除中断文件")
                    delete_interrupt_file(interrupt_file)
                    return False, None, None, None

        print("\n[choice] 请输入:")
        print("  y: 使用上次记录")
        print("  n: 删除记录并继续")
        print("  其他: 返回上级菜单")

        choice = input("[input] 请选择 (y/n/其他): ").lower().strip()

        if choice == 'y':
            print("[info] 使用上次记录...")
            from_interrupt = True
            return from_interrupt, remaining_proxies, type_or_config, original_count
        elif choice == 'n':
            delete_interrupt_file(interrupt_file)
            print("[info] 已删除中断记录，重新开始...")
            from_interrupt = False
            return from_interrupt, None, None, None
        else:
            print("[info] 返回上级菜单")
            return False, 'return', None, None
    else:
        from_interrupt = False
        return from_interrupt, None, None, None
###


# MAIN 存储层 - 通用加载保存
# 从SQLite数据库加载代理
def load_proxies_from_db(db_path="proxies.db"):
    """
    从SQLite数据库加载代理
    :return: 代理分数字典, 代理信息字典
    """
    proxies = {}
    proxy_info = {}

    if not os.path.exists(db_path):
        return proxies, proxy_info

    conn = None

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('''
        SELECT 
            proxy, score, types, support_china, support_international,
            transparent, detected_ip, city, region, country, loc, org,
            postal, timezone, browser_valid, browser_check_date,
            browser_response_time, dns_hijacking, ssl_valid,
            malicious_content, security_check_date, avg_response_time,
            success_rate, last_checked
        FROM proxies
        ''')

        for row in cursor.fetchall():
            proxy = row[0]
            score = row[1]
            types_json = row[2]

            # 构造代理信息字典,方便使用
            info = {
                "types": json.loads(types_json) if types_json else [],
                "support": {
                    "china": bool(row[3]),
                    "international": bool(row[4])
                },
                "transparent": bool(row[5]),
                "detected_ip": row[6],
                "location": {
                    "city": row[7],
                    "region": row[8],
                    "country": row[9],
                    "loc": row[10],
                    "org": row[11],
                    "postal": row[12],
                    "timezone": row[13]
                },
                "browser": {
                    "valid": bool(row[14]),
                    "check_date": row[15],
                    "response_time": row[16]
                },
                "security": {
                    "dns_hijacking": row[17],
                    "ssl_valid": row[18],
                    "malicious_content": row[19],
                    "check_date": row[20]
                },
                "performance": {
                    "avg_response_time": row[21],
                    "success_rate": row[22],
                    "last_checked": row[23]
                }
            }

            proxies[proxy] = score
            proxy_info[proxy] = info

    except Exception as e:
        print(f"[error] 从数据库加载代理失败: {e}")
    finally:
        if conn:
            conn.close()

    return proxies, proxy_info

# 保存代理到SQLite数据库
def save_valid_proxies(proxies, proxy_info, db_path="proxies.db"):
    """
    保存代理到SQLite数据库
    :param proxies: 代理分数字典 {proxy: score}
    :param proxy_info: 代理信息字典 {proxy: info_dict}
    :param db_path: 数据库路径
    """
    if not proxies:
        return

    conn = None

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        updated_count = 0
        inserted_count = 0

        for proxy, score in proxies.items():
            if score <= 0:
                continue

            info = proxy_info.get(proxy, {})

            # 准备数据
            types_json = json.dumps(info.get("types", []), ensure_ascii=False)
            support = info.get("support", {})
            transparent = 1 if info.get("transparent") else 0
            detected_ip = info.get("detected_ip", "unknown")

            location = info.get("location", {})
            browser = info.get("browser", {})
            security = info.get("security", {})
            performance = info.get("performance", {})

            # 检查代理是否已存在
            cursor.execute("SELECT 1 FROM proxies WHERE proxy = ?", (proxy,))
            exists = cursor.fetchone()

            if exists:
                # 更新现有记录
                cursor.execute('''
                UPDATE proxies SET
                    score = ?, types = ?, support_china = ?, support_international = ?,
                    transparent = ?, detected_ip = ?, city = ?, region = ?, country = ?,
                    loc = ?, org = ?, postal = ?, timezone = ?, browser_valid = ?,
                    browser_check_date = ?, browser_response_time = ?, dns_hijacking = ?,
                    ssl_valid = ?, malicious_content = ?, security_check_date = ?,
                    avg_response_time = ?, success_rate = ?, last_checked = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE proxy = ?
                ''', (
                    score, types_json,
                    1 if support.get("china") else 0,
                    1 if support.get("international") else 0,
                    transparent, detected_ip,
                    location.get("city", "unknown"),
                    location.get("region", "unknown"),
                    location.get("country", "unknown"),
                    location.get("loc", "unknown"),
                    location.get("org", "unknown"),
                    location.get("postal", "unknown"),
                    location.get("timezone", "unknown"),
                    1 if browser.get("valid") else 0,
                    browser.get("check_date", "unknown"),
                    browser.get("response_time", -1),
                    security.get("dns_hijacking", "unknown"),
                    security.get("ssl_valid", "unknown"),
                    security.get("malicious_content", "unknown"),
                    security.get("check_date", "unknown"),
                    performance.get("avg_response_time", 0),
                    performance.get("success_rate", 0.0),
                    performance.get("last_checked", date.today().isoformat()),
                    proxy
                ))
                updated_count += 1
            else:
                # 插入新记录
                cursor.execute('''
                INSERT INTO proxies (
                    proxy, score, types, support_china, support_international,
                    transparent, detected_ip, city, region, country, loc, org,
                    postal, timezone, browser_valid, browser_check_date,
                    browser_response_time, dns_hijacking, ssl_valid,
                    malicious_content, security_check_date, avg_response_time,
                    success_rate, last_checked
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    proxy, score, types_json,
                    1 if support.get("china") else 0,
                    1 if support.get("international") else 0,
                    transparent, detected_ip,
                    location.get("city", "unknown"),
                    location.get("region", "unknown"),
                    location.get("country", "unknown"),
                    location.get("loc", "unknown"),
                    location.get("org", "unknown"),
                    location.get("postal", "unknown"),
                    location.get("timezone", "unknown"),
                    1 if browser.get("valid") else 0,
                    browser.get("check_date", "unknown"),
                    browser.get("response_time", -1),
                    security.get("dns_hijacking", "unknown"),
                    security.get("ssl_valid", "unknown"),
                    security.get("malicious_content", "unknown"),
                    security.get("check_date", "unknown"),
                    performance.get("avg_response_time", 0),
                    performance.get("success_rate", 0.0),
                    performance.get("last_checked", date.today().isoformat())
                ))
                inserted_count += 1

        conn.commit()

        if updated_count > 0 or inserted_count > 0:
            print(f"[success] 保存到数据库: 更新 {updated_count} 条, 新增 {inserted_count} 条")

    except Exception as e:
        print(f"[error] 保存代理到数据库失败: {e}")

    finally:
        if conn:
            conn.close()

# 清理数据库中分数为0的代理
def cleanup_zero_score_proxies(db_path="proxies.db"):
    """
    清理数据库中分数为0的代理

    :param db_path: 数据库文件路径
    :return: 清理的代理数量
    """
    if not os.path.exists(db_path):
        print(f"[info] 数据库文件不存在: {db_path}")
        return 0

    conn = None

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 先查询0分代理数量
        cursor.execute("SELECT COUNT(*) FROM proxies WHERE score <= 0")
        zero_score_count = cursor.fetchone()[0]

        if zero_score_count == 0:
            print("[info] 数据库中没有0分代理")
            conn.close()
            return 0

        print(f"[info] 发现 {zero_score_count} 个0分代理，开始清理...")

        # 获取要删除的代理列表（用于日志）
        cursor.execute("SELECT proxy FROM proxies WHERE score <= 0")
        dead_proxies = [row[0] for row in cursor.fetchall()]

        # 从proxies表删除0分代理
        cursor.execute("DELETE FROM proxies WHERE score <= 0")

        # 从proxy_status表删除对应的状态记录
        cursor.execute("DELETE FROM proxy_status WHERE proxy IN (SELECT proxy FROM proxies WHERE score <= 0)")

        # 从proxy_usage表删除对应的使用记录（如果存在）
        try:
            cursor.execute("DELETE FROM proxy_usage WHERE proxy IN (SELECT proxy FROM proxies WHERE score <= 0)")
        except:
            pass  # 表可能不存在，忽略错误

        deleted_count = cursor.rowcount
        conn.commit()

        # 输出日志（只显示前10个，避免日志过长）
        if dead_proxies:
            print(f"[success] 已清理 {deleted_count} 个0分代理")
            if len(dead_proxies) <= 10:
                print(f"[info] 清理的代理: {', '.join(dead_proxies[:10])}")
            else:
                print(f"[info] 清理了 {deleted_count} 个代理，前10个: {', '.join(dead_proxies[:10])}...")

        return deleted_count

    except sqlite3.Error as e:
        print(f"[error] 清理0分代理失败: {e}")
        return 0
    except Exception as e:
        print(f"[error] 清理0分代理时发生未知错误: {e}")
        return 0
    finally:
        if conn:
            conn.close()

# 清理0分代理菜单
def cleanup_zero_score_menu():
    """清理0分代理菜单"""
    print("\n[warning] === 清理0分代理 ===")
    print("注意: 此操作将永久删除数据库中所有分数<=0的代理")
    print("     这些代理通常是无效或已经失败的代理")

    confirm = input("[input] 确认清理? (输入 'y' 确认): ").strip().lower()

    if confirm != 'y':
        print("[info] 操作取消")
        return

    db_path = current_config["main"]["db_file"]
    print(f"[info] 开始清理数据库: {db_path}")

    # 调用清理函数
    cleaned_count = cleanup_zero_score_proxies(db_path)

    if cleaned_count > 0:
        print(f"[success] 成功清理 {cleaned_count} 个0分代理")
    else:
        print("[info] 没有找到0分代理")
###


# MAIN 采集层 - 爬取代理
# 通用网页爬取解析器
def scrape_html_proxies(url: str, regex_pattern: str, capture_groups: list):
    """
    :param url: 请求地址
    :param regex_pattern: re解析式，用于解析爬取结果
    :param capture_groups: 要返回的re中的值，[IpName, Port]
    :return: [proxy: port]
    """
    extracted_data = []
    encoding = "utf-8"
    try:
        response = requests.get(url=url, headers=HEADERS, timeout=current_config["main"]["timeout_cn"])
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
            print(f"\n[failed] 爬取失败,状态码{response.status_code}")   # 前面的\n防止与进度条混在一行
            return []

    except Exception as e:
        print(f"\n[error] 爬取错误: {str(e)}")
        return []

#  通用github爬取解析器
def scrape_github_proxies(choice: str):
    """
    从 GitHub raw 文件爬取代理
    处理 GitHub 代理源的通用函数
    :param choice: 用户选择的编号
    :return: 代理列表, 代理类型
    """
    source = settings.GITHUB_PROXY_SOURCES.get(choice)
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

# 爬取网页代理
def crawl_proxies():
    """爬取免费代理（添加中断恢复检查）"""
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
    by_type = ''  # 通过指定类型验证,默认为否

    if scraper_choice == "1":
        print('\n[info] 爬取:https://proxy5.net/cn/free-proxy/china')
        print('[start]')

        error_count = 0
        '''
        <tr>.*?<td><strong>(?P<ip>.*?)</strong></td>.*?<td>(?P<port>.*?)</td>.*?</tr>
        '''
        proxy_list = scrape_html_proxies('https://proxy5.net/cn/free-proxy/china',
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

            proxy_list = scrape_html_proxies(url, "<tr>.*?<td>(?P<ip>.*?)</td>.*?<td>(?P<port>.*?)</td>.*?</tr>",
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
        proxy_list = scrape_html_proxies("https://cn.freevpnnode.com/",
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

                proxy_list = scrape_html_proxies(f"https://www.kuaidaili.com/free/inha/{page}/",
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
            proxy_list = scrape_html_proxies(f'http://www.ip3366.net/?stype=1&page={page}',
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
        proxy_list = scrape_html_proxies("https://proxyhub.me/zh/cn-http-proxy-list.html",
                                    r'<tr>\s*<td>(?P<ip>\d+\.\d+\.\d+\.\d+)</td>\s*<td>(?P<port>\d+)</td>',
                                    ["ip", "port"])
        if proxy_list:
            all_proxies.extend(proxy_list)
        else:
            error_count += 1
        print(f'100%|██████████████████████████████████████████████████| 1/1  错误数:{error_count}')
        print(f"\n[end] 爬取完成！")

        # GitHub选项统一处理 9-18
    elif scraper_choice in settings.GITHUB_PROXY_SOURCES:
        all_proxies,by_type = scrape_github_proxies(scraper_choice)

    else:
        print("[info] 退出爬取")
        return None, None

    return filter_proxies(all_proxies), by_type

# 调用 - 加载并验证菜单
def validate_new_proxies_menu():
    """加载并验证菜单"""
    new_proxies = None
    by_type = False

    print('''[choice] === 加载并验证代理 ===
    来自:
        1: 来自爬虫爬取
        2: 来自本地文件(proxy,port)

        输入其他: 返回上级菜单
    ''')
    from_choice = input('[input] 选择:').strip()

    if from_choice == '1':
        interrupt_file = os.path.join(current_config["interrupt"]["interrupt_dir"],
                                      current_config["interrupt"]["interrupt_file_crawl"])
        # 先查找中断恢复
        from_interrupt, remaining_proxies, type_or_config, original_count = check_interrupted_records(interrupt_file)
        if (from_interrupt == False) and (remaining_proxies == "return"):  # 返回上级菜单
            return

        elif from_interrupt and remaining_proxies:  # 来自中断恢复,且有剩余
            new_proxies = remaining_proxies
            by_type = type_or_config

        elif (from_interrupt == False) and (remaining_proxies is None):  # 重新爬取
            new_proxies, by_type = crawl_proxies()

        if new_proxies:  # 如果有新代理
            if by_type:  # 如果指定类型
                validate_new_proxies(new_proxies, by_type, from_interrupt)
            else:  # 没有指定类型
                validate_new_proxies(new_proxies, "auto", from_interrupt)
        else:
            print("[failed] 没有新代理")

    elif from_choice == '2':
        interrupt_file = os.path.join(current_config["interrupt"]["interrupt_dir"],
                                      current_config["interrupt"]["interrupt_file_load"])
        # 先查找中断恢复
        from_interrupt, remaining_proxies, type_or_config, original_count = check_interrupted_records(interrupt_file)
        if (from_interrupt == False) and (remaining_proxies == "return"):  # 返回上级菜单
            return

        elif from_interrupt and remaining_proxies:  # 来自中断恢复,且有剩余
            validate_new_proxies(remaining_proxies, type_or_config, from_interrupt=True, source="load")

        elif (from_interrupt == False) and (remaining_proxies is None):  # 重新加载
            selected_type = 'auto'

            try:
                filename = input('[input] 文件名(路径): ')
                if not os.path.exists(filename):
                    print("[failed] 文件不存在")
                    return

                # 选择代理类型
                print("\n[choice] 选择代理类型:")
                print("1. http/https")
                print("2. socks4")
                print("3. socks5")
                print("4. 自动检测")
                print("输入其他: 使用默认值http")
                type_choice = input("[input] 请选择(1-4): ").strip()

                type_map = {
                    "1": "http",
                    "2": "socks4",
                    "3": "socks5",
                    "4": "auto"
                }

                selected_type = type_map.get(type_choice, "http")
                print(f"[input] 使用类型: {selected_type}")

                data = []
                with open(filename, 'r', encoding='utf-8') as file:
                    reader = csv.reader(file)
                    for row in reader:
                        if len(row) >= 2:
                            # 支持 ip,port 格式
                            ip = row[0].strip()
                            port = row[1].strip()
                            if ip and port:
                                data.append(f"{ip}:{port}")
                        elif len(row) == 1 and ':' in row[0]:
                            # 支持 ip:port 格式
                            data.append(row[0].strip())

                if not data:
                    print("[failed] 文件中没有找到有效的代理")
                    return

                print(f"[info] 从文件加载了 {len(data)} 个代理")

                # 与当前代理池比较,筛选去重
                new_proxies = filter_proxies(data)

            except Exception as e:
                print(f'[error] 出错了: {str(e)}')

            if new_proxies:
                if selected_type != "auto":
                    # 使用指定类型验证
                    validate_new_proxies(new_proxies, selected_type, source="load")
                else:
                    # 使用自动检测
                    validate_new_proxies(new_proxies, "auto", source="load")
            else:
                print("[failed] 没有新代理需要验证")

    else:
        print('[info] 返回上级菜单')
        return
###


# MAIN 验证层1 - 基础代理验证(可用/协议/透明/范围/信息)
# 验证IP地址格式是否有效
def is_valid_ip(ip):
    """
    验证IP地址格式是否有效

    :param ip: IP地址字符串
    :return: 是否有效
    """
    import socket
    try:
        # 检查IPv4格式
        socket.inet_pton(socket.AF_INET, ip)
        return True
    except socket.error:
        try:
            # 检查IPv6格式
            socket.inet_pton(socket.AF_INET6, ip)
            return True
        except socket.error:
            return False

# 设置代理
def set_up_proxy(proxy, proxy_type="http"):
    r"""
    设置代理

    if proxy_type == "http":
        proxies_config = {
            "http": f"http://{proxy}",
            "https": f"http://{proxy}"
        }
    elif proxy_type == "socks4":
        proxies_config = {
            "http": f"socks4://{proxy}",
            "https": f"socks4://{proxy}"
        }
    elif proxy_type == "socks5":
        proxies_config = {
            "http": f"socks5://{proxy}",
            "https": f"socks5://{proxy}"
        }
    else:
        proxies_config = {
            "http": f"http://{proxy}",
            "https": f"http://{proxy}"
        }

    :param proxy: 代理地址
    :param proxy_type: 代理类型
    :return: proxy_ip_info
    """

    if proxy_type == "http":
        proxies_config = {
            "http": f"http://{proxy}",
            "https": f"http://{proxy}"
        }
    elif proxy_type == "socks4":
        proxies_config = {
            "http": f"socks4://{proxy}",
            "https": f"socks4://{proxy}"
        }
    elif proxy_type == "socks5":
        proxies_config = {
            "http": f"socks5://{proxy}",
            "https": f"socks5://{proxy}"
        }
    else:
        proxies_config = {
            "http": f"http://{proxy}",
            "https": f"http://{proxy}"
        }

    return proxies_config

# 获取自己的公网IP地址
def get_own_ip(max_retries=6, retry_delay=2):
    """
    获取自己的公网IP地址

    :param max_retries: 最大重试次数
    :param retry_delay: 重试延迟(秒)
    :return: IP地址字符串，失败返回None
    """
    services = current_config["main"]["test_url_transparent"]
    timeout = current_config["main"]["timeout_transparent"]

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
                    ip = ip_data.get('origin')
                else:
                    # 其他服务返回纯字符串
                    ip = response.text.strip()

                # 验证IP格式
                if ip and is_valid_ip(ip):
                    print(f"[success] 成功获取本机IP: {ip}")
                    # 尝试保存本次获取,方便下次获取失败时可以使用本次的
                    current_config["main"]["own_ip"] = ip
                    save_settings(current_config)

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
def get_ip_info(proxy, proxy_type="http"):
    """
    获取单个代理信息

    :param proxy: 代理地址
    :param proxy_type: 代理类型
    :return: proxy_ip_info/unkown
    """
    try:
        # 设置代理
        proxies_config = set_up_proxy(proxy, proxy_type)

        # 使用ipinfo服务
        url = current_config["main"]["test_url_info"]

        # 使用代理访问检测网站
        response = requests.get(
            url,
            proxies=proxies_config,
            timeout=current_config["main"]["timeout_ipinfo"]
        )

        if response.status_code == 200:
            # 返回JSON格式
            proxy_ip_info = response.json()

            return proxy_ip_info
        else:
            return "unknown"

    except:
        return "unknown"

# 检测单个代理是否为透明代理
def check_transparent_proxy(proxy, proxy_type="http", own_ip=None):
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
        urls = current_config["main"]["test_url_transparent"]
        # 随机挑选一个
        url = random.choice(urls)

        # 使用代理访问检测网站
        response = requests.get(
            url,
            proxies=proxies_config,
            timeout=current_config["main"]["timeout_transparent"]
        )

        if response.status_code == 200:
            if url == "https://httpbin.org/ip":
                # httpbin返回JSON格式
                ip_data = response.json()
                ip = ip_data.get('origin')
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

# 检查单个代理IP对单个URL的可用性(支持HTTP和SOCKS)
def check_proxy_single(proxy, test_url, timeout, retries=1, proxy_type="auto"):
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

                # if 200 <= response.status_code < 400:   # 接受200-400,较宽松
                if response.status_code == 200:  # 只接受200,严格
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

# 检查单个代理的综合验证(调用check_proxy_single和check_transparent_proxy),双重验证代理
def check_proxy_dual(proxy, already_have_info, proxy_type="auto",avg_response_time=-1,success_rate=0.5):
    """
    同时验证百度(国内)和Google(国际)，可选透明代理检测

    :param proxy: 被检测的单个代理
    :param already_have_info: 是否已有信息
    :param proxy_type: 代理类型
    :param avg_response_time: 代理平均响应时间
    :param success_rate: 代理平均响应成功率
    :return: 代理信息
    """
    new_ip_info: Dict[str, Any] = {   # 初始化时为unknown或False,: Dict[str, Any]用于去掉pycharm的黄色提示
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
    cn_success, cn_response_time, detected_type_cn = check_proxy_single(
        proxy, current_config["main"]["test_url_cn"], current_config["main"]["timeout_cn"], 1, proxy_type
    )

    # 验证国际网站
    intl_success, intl_response_time, detected_type_intl = check_proxy_single(
        proxy, current_config["main"]["test_url_intl"], current_config["main"]["timeout_intl"], 1, proxy_type
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
            # 随便加一个,毕竟都已排除unknown且两个相等
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
    if (current_config["main"]["check_transparent"].lower() == "true") and (cn_success or intl_success):
        for type_ in new_ip_info["types"]:
            own_ip =  current_config["main"]["own_ip"]
            check_status, transparent, detected_ip = check_transparent_proxy(proxy, type_,own_ip)
            if check_status:   # 当检查成功时
                is_transparent = transparent
                break   # 在有多种类型时,只要一次成功就不用继续了,防止做无用功
    # 添加透明检测结果
    new_ip_info["transparent"] = is_transparent
    new_ip_info["detected_ip"] = detected_ip

    # 其他信息获取(只在代理有效,没有信息且需要检测时进行)
    other_info = {}
    if (current_config["main"]["get_ip_info"].lower() == "true") and (cn_success or intl_success) and (
            already_have_info[proxy] == 0):
        # 获取ip其他信息
        for type_ in new_ip_info["types"]:
            info = get_ip_info(proxy, type_)
            if info != "unknown":
                other_info = info
                break   # 在有多种类型时,只要一次成功就不用继续了,防止做无用功
        # 添加服务器信息
        new_ip_info["location"]["city"] = other_info.get("city","unknown")
        new_ip_info["location"]["region"] = other_info.get("region", "unknown")
        new_ip_info["location"]["country"] = other_info.get("country", "unknown")
        new_ip_info["location"]["loc"] = other_info.get("loc", "unknown")
        new_ip_info["location"]["org"] = other_info.get("org", "unknown")
        new_ip_info["location"]["postal"] = other_info.get("postal", "unknown")
        new_ip_info["location"]["timezone"] = other_info.get("timezone", "unknown")

    elif (current_config["main"]["get_ip_info"].lower() == "true") and (cn_success or intl_success) and (
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
def check_proxies_batch(proxies, already_have_info, proxy_types,avg_response_time_dict=None,success_rate_dict=None, max_workers=50, check_type="new"):
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
    global interrupted

    updated_proxies = {}
    updated_info = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_proxy = {}
        for proxy in proxies:
            if interrupted:
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
                success_rate = 0.5   # 初始化时0.5
                avg_response_time = -1 # 初始化时-1 - 即没有测过

            future = executor.submit(check_proxy_dual, proxy, already_have_info,proxy_type, avg_response_time, success_rate)
            future_to_proxy[future] = proxy

        for future in concurrent.futures.as_completed(future_to_proxy):
            if interrupted:
                # 取消所有未完成的任务
                for f in future_to_proxy:
                    f.cancel()
                break

            proxy = future_to_proxy[future]
            try:
                new_ip_info = future.result()

                # 计算分数和更新逻辑
                current_score = proxies.get(proxy, 0)

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
                            f"✅[success] {proxy} | type:{new_ip_info["types"]} | China:{'pass' if new_ip_info["support"]["china"] else 'fail'} | International:{'pass' if new_ip_info["support"]["international"] else 'fail'} | get_info:{get_info}{transparent_warning}")
                    else:
                        updated_proxies[proxy] = 0
                        print(f"❌[failed] {proxy}")
                else:
                    # 已有代理：根据测试结果调整分数
                    if new_ip_info["support"]["china"] and new_ip_info["support"]["international"]:
                        # 两次都通过，加2分
                        updated_proxies[proxy] = min(current_score + 2, current_config["main"]["max_score"])
                        transparent_warning = " | [warning] transparent" if new_ip_info["transparent"] else ""
                        print(
                            f"✅[success] {proxy} | type:{new_ip_info["types"]} | China:pass | International:pass | score:{current_score}->{updated_proxies[proxy]} | get_info:{get_info}{transparent_warning}")
                    elif new_ip_info["support"]["china"] or new_ip_info["support"]["international"]:
                        # 只通过一个，加1分
                        updated_proxies[proxy] = min(current_score + 1, current_config["main"]["max_score"])
                        status = "China:pass | International:fail" if new_ip_info["support"]["china"] else "China:fail | International:pass"
                        transparent_warning = " | [warning] transparent" if new_ip_info["transparent"] else ""
                        print(
                            f"✅[success] {proxy} | type:{new_ip_info["types"]} | {status} | score: {current_score}->{updated_proxies[proxy]} | get_info:{get_info}{transparent_warning}")
                    else:
                        # 两个都不通过，减1分
                        updated_proxies[proxy] = max(0, current_score - 1)
                        print(
                            f"❌[failed] {proxy} | type:{new_ip_info["types"]} | China:fail | International:fail | score:{current_score}->{updated_proxies[proxy]}")

                # 记录
                updated_info[proxy] = new_ip_info

            except Exception as e:
                if not interrupted:  # 只有不是中断引起的异常才打印
                    print(f"❌[error] {proxy} - {str(e)}")

                if check_type == "existing" and proxy in proxies:
                    updated_proxies[proxy] = max(0, proxies[proxy] - 1)
                else:
                    updated_proxies[proxy] = 0

                # 创建默认的错误信息
                updated_info[proxy] = {
                    "types": [],
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

# 从获取代理中去掉无效的、重复的
def filter_proxies(all_proxies):
    """
    从新获取代理中去掉无效的、重复的（数据库版本）

    使用集合进行查找，时间复杂度O(1)

    :param all_proxies: 新代理列表
    :return: 筛选后的代理列表
    """
    if not all_proxies:
        print("[info] 没有代理需要筛选")
        return []

    print(f"[info] 开始筛选 {len(all_proxies)} 个代理...")

    # 加载现有代理池（从数据库读取，使用集合提高查找效率）
    existing_proxies_set = set()
    db_path = current_config["main"]["db_file"]  # 数据库文件路径

    # 从数据库查询已有代理
    if os.path.exists(db_path):
        conn = None
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            # 代理存储在proxies表的proxy字段中
            cursor.execute("SELECT proxy FROM proxies")
            # 提取所有代理字符串到集合
            existing_proxies_set = {row[0].strip() for row in cursor.fetchall() if row[0]}
            print(f"[info] 从数据库加载了 {len(existing_proxies_set)} 个已有代理")
        except sqlite3.Error as e:
            print(f"[warning] 读取数据库代理失败: {e}")
        finally:
            if conn:
                conn.close()  # 确保连接关闭
    else:
        print(f"[info] 数据库文件不存在，视为无已有代理")

    # 使用集合进行去重和验证（这部分逻辑与原函数一致）
    seen_proxies = set()
    new_proxies_set = set()
    duplicate_count = 0
    invalid_count = 0
    format_error_count = 0

    for proxy in all_proxies:
        if not proxy or not isinstance(proxy, str):
            invalid_count += 1
            continue

        proxy = proxy.strip()

        # 检查当前批次内的重复
        if proxy in seen_proxies:
            duplicate_count += 1
            continue
        seen_proxies.add(proxy)

        # 验证代理格式（ip:port）
        if not is_valid_proxy_format(proxy):
            format_error_count += 1
            continue

        # 检查是否已存在于数据库中
        if proxy in existing_proxies_set:
            duplicate_count += 1
            continue

        # 检查是否在新代理集合中重复
        if proxy in new_proxies_set:
            duplicate_count += 1
            continue

        new_proxies_set.add(proxy)

    # 转换为列表返回
    new_proxies = list(new_proxies_set)

    print(f"[success] 筛选完成!")
    print(f"  有效新代理: {len(new_proxies)}")
    print(f"  重复代理: {duplicate_count}")
    print(f"  格式错误: {format_error_count}")
    print(f"  无效代理: {invalid_count}")

    return new_proxies

# 验证代理格式是否有效
def is_valid_proxy_format(proxy):
    """
    验证代理格式是否有效

    :param proxy: 代理字符串 (ip:port)
    :return: 是否有效
    """
    # if not proxy or ':' not in proxy:
    if (not proxy) or (':' not in proxy) or (len(proxy) > 30) or (len(proxy) < 9):
        return False

    try:
        ip, port = proxy.split(':', 1)

        # 验证IP格式
        if not is_valid_ip(ip):
            return False

        # 验证端口格式
        port_num = int(port)
        if not (1 <= port_num <= 65535):
            return False

        return True

    except (ValueError, AttributeError):
        return False

# 调用 - 验证代理
def validate_new_proxies(new_proxies, proxy_type="auto", from_interrupt=False, source="crawl"):
    """验证新代理（支持中断恢复和透明代理检测）"""
    global interrupted

    if not new_proxies:
        print("[failed] 没有代理需要验证")
        return

    # PERF: 初始化本机ip,用于透明代理检测(防止每个验证都重新获取,这样一轮一次)
    if current_config["main"]["check_transparent"].lower() == "true":
        get_own_ip()
        print("[info] 启用透明代理检测")

    # 根据来源选择中断文件(爬取中断/加载中断)
    interrupt_file_name = current_config["interrupt"]["interrupt_file_crawl"] if source == "crawl" else \
    current_config["interrupt"]["interrupt_file_load"]
    interrupt_file = os.path.join(current_config["interrupt"]["interrupt_dir"], interrupt_file_name)
    original_count = len(new_proxies)
    print(f"[start] 共加载 {original_count} 个新代理，使用{proxy_type}类型开始双重测试...")

    # 保存初始状态到中断文件（如果不是从中断恢复的）
    if not from_interrupt:
        save_interrupted_proxies(new_proxies, proxy_type, original_count, interrupt_file)
        print(f"[file] 已创建中断恢复文件: {interrupt_file_name}")

    # 新代理初始分数为0
    new_proxies_dict = {proxy: 0 for proxy in new_proxies}
    new_types_dict = {proxy: proxy_type for proxy in new_proxies}
    # 都没有信息
    already_have_info = {proxy: 0 for proxy in new_proxies}

    try:
        updated_proxies, updated_info = check_proxies_batch(
            new_proxies_dict, already_have_info, new_types_dict, None ,None,current_config["main"]["max_workers"], check_type="new"
        )

        if interrupted:
            # 计算剩余未验证的代理
            verified_proxies = set(updated_proxies.keys())
            remaining_proxies = [proxy for proxy in new_proxies if proxy not in verified_proxies]

            # 保存已验证的代理到代理池


            existing_proxies, existing_info = load_proxies_from_db(current_config["main"]["db_file"])
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

            save_valid_proxies(existing_proxies, existing_info,current_config["main"]["db_file"])

            # 更新中断文件
            if remaining_proxies:
                save_interrupted_proxies(remaining_proxies, proxy_type, original_count, interrupt_file)
                print(
                    f"\n[pause] 验证已中断！已保存 {len(verified_proxies)} 个代理到代理池，剩余 {len(remaining_proxies)} 个代理待验证")
                print(f"[file] 中断文件已更新: {interrupt_file_name}")
            else:
                delete_interrupt_file(interrupt_file)
                print(f"\n[success] 验证完成！所有代理已验证并保存")

            interrupted = False
            return

        # 正常完成验证
        # 合并到现有代理池
        existing_proxies,existing_info = load_proxies_from_db(current_config["main"]["db_file"])
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

        save_valid_proxies(existing_proxies, existing_info,current_config["main"]["db_file"])

        # 删除中断文件
        delete_interrupt_file(interrupt_file)

        # 统计结果
        success_count = sum(1 for score in updated_proxies.values() if score == 98)
        china_only = sum(1 for proxy in updated_proxies if updated_info[proxy]["support"]["china"] and not updated_info[proxy]["support"]["international"])
        intl_only = sum(1 for proxy in updated_proxies if not updated_info[proxy]["support"]["china"] and updated_info[proxy]["support"]["international"])
        both_support = sum(1 for proxy in updated_proxies if updated_info[proxy]["support"]["china"] and updated_info[proxy]["support"]["international"])
        transparent_count = sum(1 for proxy in updated_proxies if updated_info[proxy]["transparent"])

        print(f"\n[success] 验证完成!")
        print(f"成功代理: {success_count}/{original_count}")
        print(f"仅支持国内: {china_only} | 仅支持国际: {intl_only} | 双支持: {both_support}")
        print(f"透明代理: {transparent_count} 个")
        print(f"代理池已更新至: {current_config["main"]["db_file"]}")

    except Exception as e:
        if not interrupted:
            print(f"[error] 验证过程中发生错误: {str(e)}")

# 调用 - 加载验证已有代理池中的代理
def validate_existing_proxies():
    """验证已有代理池中的代理（支持中断恢复和透明代理检测）"""
    global interrupted

    proxies_to_validate = None

    interrupt_file = os.path.join(current_config["interrupt"]["interrupt_dir"],
                                  current_config["interrupt"]["interrupt_file_existing"])

    # 首先检查是否有中断记录
    from_interrupt, remaining_proxies, type_or_config, original_count = check_interrupted_records(interrupt_file)
    if (from_interrupt == False) and (remaining_proxies == "return"):  # 返回上级菜单
        return

    elif from_interrupt and remaining_proxies:  # 选择恢复,且有剩余
        proxies_to_validate = remaining_proxies
        original_count = original_count   # 选择更新后的数量

    elif (from_interrupt == False) and (remaining_proxies is None):  # 选择不恢复
        delete_interrupt_file(interrupt_file)
        proxies_to_validate = None  # 重新加载所有代理

    print(f"[info] 开始验证已有代理，文件：{current_config["main"]["db_file"]}...")

    # PERF: 初始化本机ip,用于透明代理检测(防止每个验证都重新获取,这样一轮一次)
    if current_config["main"]["check_transparent"].lower() == "true":
        get_own_ip()
        print("[info] 启用透明代理检测")

    # 加载代理池
    all_proxies, proxy_info = load_proxies_from_db(current_config["main"]["db_file"])

    if proxies_to_validate is None:
        # 重新验证所有代理
        proxies_to_validate = list(all_proxies.keys())
        original_count = len(proxies_to_validate)

    if not proxies_to_validate:
        print("[failed] 没有代理需要验证")
        return

    print(f"[start] 共加载 {len(proxies_to_validate)} 个代理，开始测试...")

    # 保存初始状态到中断文件
    save_interrupted_proxies(
        proxies_to_validate, "already_have", original_count, interrupt_file
    )
    print(f"[file] 已创建中断恢复文件: {current_config["interrupt"]["interrupt_file_existing"]}")

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
                avg_response_time_dict[proxy] = proxy_info[proxy].get("performance", {}).get("avg_response_time", -1)
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

        updated_proxies, updated_info = check_proxies_batch(
            proxies_dict, already_have_info,types_dict,avg_response_time_dict,success_rate_dict, current_config["main"]["max_workers"], "existing"
        )

        # 中断
        if interrupted:
            # 计算剩余未验证的代理
            verified_proxies = set(updated_proxies.keys())
            remaining_proxies = [proxy for proxy in proxies_to_validate if proxy not in verified_proxies]

            # 更新已验证的代理分数和支持范围
            for proxy, score in updated_proxies.items():
                all_proxies[proxy] = score
                if updated_info[proxy]["types"]:   # 有type即表示代理可用,只有可用才修改
                    proxy_info[proxy]["types"] = list(set(proxy_info[proxy]["types"] + updated_info[proxy]["types"]))   # 添加新的类型,并去重
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
            save_valid_proxies(all_proxies, proxy_info,current_config["main"]["db_file"])

            # 更新中断文件
            if remaining_proxies:
                save_interrupted_proxies(remaining_proxies, "already_have", original_count, interrupt_file)
                print(
                    f"\n[pause] 验证已中断！已更新 {len(verified_proxies)} 个代理，剩余 {len(remaining_proxies)} 个代理待验证")
                print(f"[file] 中断文件已更新: {current_config["interrupt"]["interrupt_file_existing"]}")
            else:
                delete_interrupt_file(interrupt_file)
                print(f"\n[success] 验证完成！所有代理已更新")

            interrupted = False
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
        save_valid_proxies(all_proxies, proxy_info,current_config["main"]["db_file"])

        # 删除中断文件
        delete_interrupt_file(interrupt_file)

        # 最终统计
        final_count = sum(1 for score in updated_proxies.values() if score > 0)
        china_only = sum(1 for proxy in proxies_to_validate if updated_info[proxy]["support"]["china"] and not updated_info[proxy]["support"]["international"])
        intl_only = sum(1 for proxy in proxies_to_validate if not updated_info[proxy]["support"]["china"] and updated_info[proxy]["support"]["international"])
        both_support = sum(1 for proxy in proxies_to_validate if updated_info[proxy]["support"]["china"] and updated_info[proxy]["support"]["international"])
        transparent_count = sum(1 for proxy in proxies_to_validate if updated_info[proxy]["transparent"])

        print(f"\n[success] 验证完成! 剩余有效代理: {final_count}/{original_count}")
        print(f"仅支持国内: {china_only} | 仅支持国际: {intl_only} | 双支持: {both_support}")
        print(f"[warning]  透明代理: {transparent_count} 个")
        print(f"已移除 {original_count - final_count} 个无效代理")

    except Exception as e:
        if not interrupted:
            print(f"[error] 验证过程中发生错误: {str(e)}")
###


# MAIN 验证层2 - 使用浏览器驱动库实现浏览器可用代理检查
# 使用Playwright验证单个代理的浏览器可用性
def check_proxy_with_browser_single(proxy, proxy_type="http", test_url="https://httpbin.org/ip", timeout=15000):
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
                    '--headless=new',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding'
                ]

                # 启动浏览器
                browser = await p.chromium.launch(args=browser_args)

                # 配置代理
                proxy_config = ProxySettings(
                    server =  f"{proxy_type}://{proxy}"
                )

                context = await browser.new_context(proxy=proxy_config)
                page = await context.new_page()

                # 设置超时
                page.set_default_timeout(timeout)

                # 开始计时
                start_time = time.time()

                # 访问测试页面
                response = await page.goto(test_url, wait_until='domcontentloaded')

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
def validate_proxies_with_browser(proxies, proxy_types, config, from_interrupt=False):
    """
    批量验证代理的浏览器可用性
    """
    global interrupted

    if not proxies:
        print("[failed] 没有代理需要浏览器验证")
        return {}

    original_count = len(proxies)
    max_concurrent = config.get('max_concurrent', 3)
    test_url = current_config["main"]["test_url_browser"]

    print(f"[start] 开始浏览器验证，共 {original_count} 个代理，并发数: {max_concurrent}")
    print("这可能需要一些时间，请耐心等待...")

    interrupt_file = os.path.join(current_config["interrupt"]["interrupt_dir"],
                                  current_config["interrupt"]["interrupt_file_browser"])
    # 保存中断文件（如果不是从中断恢复的）
    if not from_interrupt:
        save_interrupted_proxies(proxies, config, original_count, interrupt_file=interrupt_file, from_browser=True)
        print(f"[file] 已创建浏览器验证中断恢复文件: {current_config['interrupt']['interrupt_file_browser']}")

    results = {}
    completed = 0

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            future_to_proxy = {}

            for proxy in proxies:
                if interrupted:
                    break

                proxy_type = proxy_types.get(proxy, "http")
                future = executor.submit(
                    check_proxy_with_browser_single,
                    proxy, proxy_type, test_url
                )
                future_to_proxy[future] = proxy

            for future in concurrent.futures.as_completed(future_to_proxy):
                if interrupted:
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
                            'browser_valid': True,
                            'browser_check_date': date.today().isoformat(),
                            'browser_response_time': response_time
                        }
                        # 成功时显示响应时间，格式化为整数
                        time_ms = f"({int(response_time)}ms)" if response_time else ""
                        print(f"[{completed:3d}/{original_count}] ✅ {proxy:25s} {time_ms}")
                    else:
                        results[proxy] = {
                            'browser_valid': False,
                            'browser_check_date': date.today().isoformat(),
                            'browser_error': error
                        }
                        # 失败时提取关键错误信息，压缩到一行
                        error_summary = extract_error_summary(error)
                        print(f"[{completed:3d}/{original_count}] ❌ {proxy:25s} {error_summary}")

                except Exception as e:
                    results[proxy] = {
                        'browser_valid': False,
                        'browser_check_date': date.today().isoformat(),
                        'browser_error': str(e)
                    }
                    error_msg = str(e)[:50] + "..." if len(str(e)) > 50 else str(e)
                    print(f"[{completed:3d}/{original_count}] ❌ {proxy:25s} 异常: {error_msg}")

        if interrupted:
            # 处理中断情况
            verified_proxies = set(results.keys())
            remaining_proxies = [proxy for proxy in proxies if proxy not in verified_proxies]

            if remaining_proxies:
                save_interrupted_proxies(remaining_proxies, config, original_count, interrupt_file=interrupt_file,
                                         from_browser=True)
                print(
                    f"\n[pause] 浏览器验证已中断！已验证 {len(verified_proxies)} 个代理，剩余 {len(remaining_proxies)} 个代理待验证")
                print(f"[file] 中断文件已更新: {current_config['interrupt']['interrupt_file_browser']}")
            else:
                delete_interrupt_file(interrupt_file)
                print(f"\n[success] 浏览器验证完成！所有代理已验证")

            interrupted = False
            return results

        # 正常完成验证
        delete_interrupt_file(interrupt_file)

        # 统计结果
        success_count = sum(1 for result in results.values() if result.get('browser_valid'))
        target_success = config.get('target_success')

        print(f"\n[end] 浏览器验证完成!")
        print(f"[success] 成功: {success_count}/{original_count}")

        if target_success:
            if success_count >= target_success:
                print(f"[success] 达到目标成功数量: {success_count}/{target_success}")
            else:
                print(f"[warning] 未达到目标成功数量: {success_count}/{target_success}")

        return results

    except Exception as e:
        if not interrupted:
            print(f"[error] 浏览器验证过程中发生错误: {str(e)}")
        return results

# 从验证错误信息中提取关键部分，压缩为单行显示
def extract_error_summary(error_message):
    """
    从错误信息中提取关键部分，压缩为单行显示
    """
    if not error_message:
        return "未知错误"

    # 如果错误信息是字符串，按换行分割
    if isinstance(error_message, str):
        lines = error_message.strip().split('\n')

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
def layered_browser_validation(config=None, from_interrupt=False, proxies_to_validate=None):
    """
    分层浏览器验证
    """
    if config is None:
        config = {}

    # 如果未提供 proxies_to_validate，使用空列表
    if proxies_to_validate is None:
        proxies_to_validate = []

    # 加载代理池
    all_proxies, all_proxy_info = load_proxies_from_db(current_config["main"]["db_file"])

    if not all_proxies:
        print("[failed] 代理池为空")
        return None

    # 如果不是从中断恢复，需要筛选代理
    if not from_interrupt:
        filtered_proxies = []
        for proxy, score in all_proxies.items():
            # 分数筛选
            min_score = config.get('min_score', 80)
            if score < min_score:
                continue

            # 类型筛选
            allowed_types = config.get('proxy_types', ['http', 'socks4', 'socks5'])
            proxy_info = all_proxy_info.get(proxy, {})
            proxy_types_list = proxy_info.get('types', [])
            if not any(t in allowed_types for t in proxy_types_list):
                continue

            # 国内支持筛选
            china_req = config.get('china_support')
            if china_req is not None and proxy_info.get('support', {}).get('china', False) != china_req:
                continue

            # 国际支持筛选
            intl_req = config.get('international_support')
            if intl_req is not None and proxy_info.get('support', {}).get('international', False) != intl_req:
                continue

            # 透明代理筛选
            transparent_req = config.get('transparent_only')
            if transparent_req is not None and proxy_info.get('transparent', False) != transparent_req:
                continue

            # 浏览器验证状态筛选
            browser_status = config.get('browser_status')
            if browser_status is not None:
                browser_info = proxy_info.get('browser', {})
                browser_valid = browser_info.get('valid')

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
        max_proxies = config.get('max_proxies', 50)
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
        types = proxy_info.get('types', [])
        filtered_types[proxy] = types[0] if types else "http"

    # 进行浏览器验证
    browser_results = validate_proxies_with_browser(
        proxies_to_validate, filtered_types, config, from_interrupt=from_interrupt
    )

    # 更新代理池
    if browser_results:
        update_proxy_browser_status(browser_results)
        print("[success] 代理池浏览器验证状态已更新")

    return browser_results

# 更新代理池中的浏览器验证状态
def update_proxy_browser_status(browser_results):
    """更新代理池中的浏览器验证状态"""
    # 加载现有代理池
    existing_proxies, existing_info = load_proxies_from_db(current_config["main"]["db_file"])

    # 更新浏览器验证状态
    for proxy, result in browser_results.items():
        if proxy in existing_info:
            # 确保browser字段存在
            if 'browser' not in existing_info[proxy]:
                existing_info[proxy]['browser'] = {}

            existing_info[proxy]['browser']['valid'] = result.get('browser_valid', False)
            existing_info[proxy]['browser']['check_date'] = result.get('browser_check_date', 'unknown')
            if result.get('browser_valid'):
                existing_info[proxy]['browser']['response_time'] = result.get('browser_response_time', -1)

    # 保存更新后的代理池
    save_valid_proxies(existing_proxies, existing_info, current_config["main"]["db_file"])

# 调用 - 浏览器验证菜单
def browser_validation_menu():
    """浏览器验证菜单"""
    global interrupted

    # 首先检查是否有浏览器验证中断记录
    interrupt_file = os.path.join(current_config["interrupt"]["interrupt_dir"],
                                  current_config["interrupt"]["interrupt_file_browser"])

    # 注意：浏览器验证的type_or_config是JSON字符串，不是"already_have"等
    # 所以我们需要先尝试解析，如果是验证已有代理才进行筛选
    remaining_proxies, type_or_config, original_count = load_interrupted_proxies(interrupt_file)

    if remaining_proxies:
        print(f"[info] 发现上次浏览器验证中断记录!")
        print(f"   剩余代理: {len(remaining_proxies)}/{original_count} 个")

        # 尝试解析type_or_config，判断是否是验证已有代理
        try:
            json.loads(type_or_config)
            # 如果是验证已有代理，进行筛选
            print("[info] 正在检查中断记录中的代理是否仍存在于数据库...")
            filtered_proxies, new_original_count, removed_count = filter_interrupted_proxies(
                remaining_proxies, original_count
            )

            # 更新数据
            remaining_proxies = filtered_proxies

            if removed_count > 0:
                # 如果所有代理都被筛除，删除中断文件并返回
                if not remaining_proxies:
                    print("[info] 中断记录中所有代理都已不存在，将删除中断文件")
                    delete_interrupt_file(interrupt_file)
                    return
        except (json.JSONDecodeError, TypeError):
            # 如果不是JSON格式，说明是其他类型的中断，不进行筛选
            pass

        print("\n[choice] 请输入:")
        print("  y: 使用上次记录")
        print("  n: 删除记录并继续")
        print("  其他: 返回上级菜单")

        choice = input("[input] 请选择 (y/n/其他): ").lower().strip()

        if choice == 'y':
            print("[info] 使用上次记录...")
            config = json.loads(type_or_config) if type_or_config else {}
            proxies_to_validate = remaining_proxies
            layered_browser_validation(config=config, from_interrupt=True, proxies_to_validate=proxies_to_validate)
            return
        elif choice == 'n':
            delete_interrupt_file(interrupt_file)
            print("[info] 已删除中断记录，重新开始...")
        else:
            print('[info] 返回上级菜单')
            return
    else:
        # 重新筛选验证
        print("\n[choice] === 浏览器验证 ===")
        print("1. 筛选并验证代理")
        print("2. 重新验证浏览器失败的代理")
        print("其它: 返回上级菜单")

        choice = input("[input] 请选择 (1-2): ").strip()

        if choice == "1":
            custom_layered_validation()
        elif choice == "2":
            revalidate_failed_proxies()
        else:
            print('[info] 返回上级菜单')
            return

# 模式1:调用 - 自定义分层验证
def custom_layered_validation():
    """自定义分层验证"""
    print("\n[info]  自定义分层验证")

    try:
        # 基本配置
        min_score = int(input("[input] 最低分数 (默认95): ") or "95")
        max_proxies = int(input("[input] 最大验证数量 (默认100): ") or "100")
        target_success = int(input("[input] 目标成功数量 (默认10): ") or "10")
        max_concurrent = int(input("[input] 并发数 (默认3): ") or "3")

        # 类型筛选
        print("\n[choice] 选择代理类型:")
        print("1. HTTP/HTTPS")
        print("2. SOCKS5")
        print("3. SOCKS4")
        print("4. 全部类型")
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
        print("1. 仅支持国内")
        print("2. 仅支持国际")
        print("3. 支持国内外")
        print("4. 不限制")
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
        print("1. 仅验证透明代理")
        print("2. 仅验证非透明代理")
        print("3. 不限制")
        transparent_choice = input("[input] 请选择 (1-3): ").strip()

        transparent_only = None
        if transparent_choice == "1":
            transparent_only = True
        elif transparent_choice == "2":
            transparent_only = False
        # 3 不限制

        # 浏览器验证状态筛选
        print("\n[choice] 选择浏览器验证状态:")
        print("1. 仅验证浏览器验证失败的代理")
        print("2. 仅验证浏览器验证成功的代理")
        print("3. 仅验证未进行浏览器验证的代理")
        print("4. 不限制")
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
            'min_score': min_score,
            'max_proxies': max_proxies,
            'target_success': target_success,
            'max_concurrent': max_concurrent,
            'proxy_types': proxy_types,
            'china_support': china_support,
            'international_support': international_support,
            'transparent_only': transparent_only,
            'browser_status': browser_status
        }

        layered_browser_validation(config)

    except ValueError:
        print("[error] 输入无效")

# 模式2:调用 - 重新验证浏览器失败的代理
def revalidate_failed_proxies():
    """重新验证浏览器失败的代理"""
    print("\n[info] 重新验证浏览器失败的代理")

    # 加载代理池
    proxies, proxy_info = load_proxies_from_db(current_config["main"]["db_file"])

    # 找出浏览器验证失败的代理
    failed_proxies = []
    for proxy, info in proxy_info.items():
        browser = info.get('browser', {})
        # 检查浏览器验证状态，明确为False才重新验证
        if browser.get('valid') is False:
            failed_proxies.append(proxy)

    if not failed_proxies:
        print("[pass] 没有找到浏览器验证失败的代理")
        return

    print(f"[info] 找到 {len(failed_proxies)} 个浏览器验证失败的代理")

    config = {'max_concurrent': 5}

    try:
        if len(failed_proxies) <= 50:
            print("[info] 代理数量较少，默认全部验证")
            proxies_to_retry = failed_proxies
        else:
            count = int(input('[input] 验证数量: '))
            if count > len(failed_proxies):
                print(f'[warning] 只有{len(failed_proxies)}个失败代理，将验证全部')
                proxies_to_retry = failed_proxies
            else:
                # 限制数量，按分数排序取较高的
                scored_proxies = [(proxy, proxies.get(proxy, 0)) for proxy in failed_proxies]
                scored_proxies.sort(key=lambda x: x[1], reverse=True)
                proxies_to_retry = [proxy for proxy, score in scored_proxies[:count]]
                print(f"[info] 将验证分数最高的 {count} 个失败代理")
    except ValueError:
        print('[error] 输入错误，请输入有效数字')
        return
    except Exception as e:
        print(f'[error] 处理输入时出错: {str(e)}')
        return

    # 获取代理类型（使用第一个类型）
    retry_types = {}
    for proxy in proxies_to_retry:
        info = proxy_info.get(proxy, {})
        types = info.get('types', [])
        retry_types[proxy] = types[0] if types else "http"

    # 重新验证
    browser_results = validate_proxies_with_browser(proxies_to_retry, retry_types, config)

    # 更新状态
    if browser_results:
        update_proxy_browser_status(browser_results)
    else:
        print("[warning] 没有获取到浏览器验证结果")

    # 统计结果
    success_count = sum(1 for result in browser_results.values() if result.get('browser_valid'))
    print(f"\n[end] 重新验证完成!")
    print(f"[success] 成功: {success_count}/{len(proxies_to_retry)}")

    # 显示详细结果
    if success_count > 0:
        print("\n[info] 重新验证成功的代理:")
        for proxy, result in browser_results.items():
            if result.get('browser_valid'):
                response_time = result.get('browser_response_time', '未知')
                print(f"  ✓ {proxy} - 响应时间: {response_time}ms")
###


# MAIN 验证层3 - 代理安全验证
# 统一安全验证请求
def perform_security_requests(proxy, proxy_type="http"):
    """统一执行安全验证所需的请求，避免重复请求"""
    security_responses = {}

    try:
        proxies_config = {
            "http": f"{proxy_type}://{proxy}",
            "https": f"{proxy_type}://{proxy}"
        }

        # 执行所有必要的请求
        test_urls = current_config["main"]["test_urls_safety"]

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
                                            timeout=current_config["main"]["timeout_safety"])
                    security_responses[key] = (response, None)
            except Exception as e:
                security_responses[key] = (None, f"请求失败: {str(e)}")

        return security_responses

    except Exception as e:
        return {"error": f"统一请求失败: {str(e)}"}

# 检测代理是否注入恶意内容
def check_malicious_content(security_responses):
    """检测代理是否注入恶意内容"""
    try:
        # 检查常见恶意内容模式
        malicious_patterns = [
            r'<script[^>]*src=[\"\']?[^>]*\.min\.js',  # 可疑脚本
            r'eval\(',  # eval函数
            r'document\.write',  # 动态写入
            r'<iframe',  # 可疑iframe
            r'javascript:',  # JS协议
        ]

        # 检查HTML响应
        html_response, _ = security_responses.get("html", (None, None))
        if html_response and hasattr(html_response, 'text'):
            for pattern in malicious_patterns:
                if re.search(pattern, html_response.text, re.IGNORECASE):
                    return False, "检测到恶意内容注入"

        # 检查JSON响应
        json_response, _ = security_responses.get("json", (None, None))
        if json_response and hasattr(json_response, 'text'):
            for pattern in malicious_patterns:
                if re.search(pattern, json_response.text, re.IGNORECASE):
                    return False, "检测到恶意内容注入"

        return True, "内容安全"

    except Exception as e:
        return False, f"内容检测失败: {str(e)}"

# 验证SSL证书安全性
def check_ssl_security(security_responses):
    """验证SSL证书安全性"""
    try:
        https_response, _ = security_responses.get("https", (None, None))

        if https_response is None:
            return False, "HTTPS请求失败"

        # 检查证书信息
        if hasattr(https_response.connection, 'socket'):
            cert = https_response.connection.socket.getpeercert()
            # 验证证书有效期
            not_after = cert.get('notAfter', '')
            # 可以添加更多证书检查逻辑

        return True, "SSL证书验证通过"

    except requests.exceptions.SSLError:
        return False, "SSL证书验证失败 - 可能存在中间人攻击"
    except Exception as e:
        return False, f"SSL检查失败: {str(e)}"

# 检测DNS劫持
def check_dns_hijacking(security_responses):
    """检测DNS劫持"""
    try:
        # 测试已知IP的域名
        test_domains = {
            "httpbin.org": "54.227.38.221",  # 需要更新为实际IP
        }

        # 通过IP测试响应检查DNS解析
        ip_response, _ = security_responses.get("ip_test", (None, None))
        if ip_response and hasattr(ip_response, 'text'):
            # 检查返回的IP是否包含在响应中
            response_data = ip_response.json()
            actual_ip = response_data.get('origin', '')

            for domain, expected_ip in test_domains.items():
                if expected_ip not in actual_ip:
                    return False, f"DNS劫持检测: {domain} 解析异常"

        return True, "DNS解析正常"

    except Exception as e:
        return False, f"DNS检查失败: {str(e)}"

# 检测代理是否篡改数据
def check_data_tampering(security_responses):
    """检测代理是否篡改数据"""
    try:
        # 测试已知固定响应的API
        base64_response, _ = security_responses.get("base64", (None, None))

        if base64_response and hasattr(base64_response, 'text'):
            expected_content = "Hello World"
            if base64_response.text.strip() != expected_content:
                return False, "数据被篡改"

        return True, "数据完整性验证通过"

    except Exception as e:
        return False, f"数据完整性检查失败: {str(e)}"

# 检测可疑代理行为
def check_suspicious_behavior(security_responses):
    """检测可疑代理行为"""
    suspicious_indicators = []

    try:
        # 检查响应头
        headers_response, _ = security_responses.get("headers", (None, None))
        if headers_response and hasattr(headers_response, 'headers'):
            headers = headers_response.headers

            # 检查可疑响应头
            suspicious_headers = [
                'X-Proxy-Modified',
                'X-Forwarded-By',
                'Via'  # 某些代理会添加Via头
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
def comprehensive_security_check(proxy, proxy_type="http"):
    """综合安全性验证 - 统一请求流程"""
    # 执行统一请求
    security_responses = perform_security_requests(proxy, proxy_type)

    if "error" in security_responses:
        return False, 0, [security_responses["error"]]

    # 使用统一响应数据进行各项检查
    security_results = {
        "malicious_content": check_malicious_content(security_responses),
        "ssl_security": check_ssl_security(security_responses),
        "dns_security": check_dns_hijacking(security_responses),
        "data_integrity": check_data_tampering(security_responses),
        "behavior_analysis": check_suspicious_behavior(security_responses)
    }

    # 计算安全评分
    passed_checks = sum(1 for result in security_results.values() if result[0])
    total_checks = len(security_results)
    security_score = (passed_checks / total_checks) * 100

    # 收集失败原因
    failures = [f"{name}: {reason}" for name, (passed, reason) in security_results.items() if not passed]

    return security_score >= 80, security_score, failures
###


# MAIN 调度层 - 手动筛选提取代理
# 依照条件提取
def extract_proxies_by_type(num, proxy_type="all", china_support=None, international_support=None,transparent_only=None, browser_only=None):
    """
    按类型和支持范围提取指定数量的代理，优先提取分高的
    """
    proxies, proxy_info = load_proxies_from_db(current_config["main"]["db_file"])

    # 按类型,支持范围,透明代理,浏览器可用筛选
    filtered_proxies = {}
    for proxy, score in proxies.items():
        info = proxy_info.get(proxy, {})

        # 类型筛选
        if proxy_type != "all":
            proxy_types = info.get('types', [])
            if proxy_type not in proxy_types:
                continue

        # 中国支持筛选
        if china_support is not None and info.get('support', {}).get('china', False) != china_support:
            continue

        # 国际支持筛选
        if international_support is not None and info.get('support', {}).get('international',
                                                                             False) != international_support:
            continue

        # 透明代理筛选
        if transparent_only is not None and info.get('transparent', False) != transparent_only:
            continue

        # 浏览器可用筛选
        if browser_only is not None:
            browser_status = info.get('browser', {}).get('valid', False)
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
        actual_type = info.get('types', ['http'])[0] if info.get('types') else 'http'
        china = info.get('support', {}).get('china', False)
        international = info.get('support', {}).get('international', False)
        transparent = info.get('transparent', False)
        browser_valid = info.get('browser', {}).get('valid', False)

        result.append({
            'proxy': f"{actual_type}://{proxy}",
            'score': score,
            'china': china,
            'international': international,
            'transparent': transparent,
            'browser_valid': browser_valid
        })

    return result

# 调用 - 传入条件
def extract_proxies_menu():
    """提取代理菜单（支持按类型、支持范围和透明代理筛选）"""
    try:
        count = int(input("[input] 请输入要提取的代理数量: ").strip())
        if count <= 0:
            print("[failed] 数量必须大于0")
            return

        # 选择代理类型
        print("\n[choice] 选择代理类型:")
        print("1. http/https")
        print("2. socks4")
        print("3. socks5")
        print("4. 全部类型")
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
        print("1. 仅支持国内")
        print("2. 仅支持国际")
        print("3. 支持国内外")
        print("4. 不限制支持范围")
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
        print("1. 仅提取透明代理")
        print("2. 仅提取非透明代理")
        print("3. 不限制")
        transparent_choice = input("[input] 请选择(1-3): ").strip()

        transparent_only = None
        if transparent_choice == "1":
            transparent_only = True
        elif transparent_choice == "2":
            transparent_only = False
        # 3 和其他情况不限制

        # 浏览器可用筛选
        print("\n[choice] 选择浏览器可用代理筛选:")
        print("1. 仅提取浏览器可用代理")
        print("2. 仅提取浏览器不可用代理")
        print("3. 不限制")
        browser_choice = input("[input] 请选择(1-3): ").strip()

        browser_only = None
        if browser_choice == '1':
            browser_only = True
        elif browser_choice == '2':
            browser_only = False
        # 3 和其他情况不限制

        proxies = extract_proxies_by_type(count, proxy_type, china_support, international_support, transparent_only,
                                          browser_only)
        if not proxies:
            print("[warning] 代理池中没有符合条件的代理")
            return

        if len(proxies) < count:
            print(f"[warning] 只有 {len(proxies)} 个符合条件代理，少于请求的 {count} 个")

        print(f"\n[success] 提取的代理列表({proxy_type}):")
        for i, proxy_info in enumerate(proxies, 1):
            support_desc = []
            if proxy_info['china']:
                support_desc.append("国内")
            if proxy_info['international']:
                support_desc.append("国际")
            support_str = "|".join(support_desc) if support_desc else "无"
            transparent_str = "[warning]透明" if proxy_info['transparent'] else "匿名"
            print(f"{i}. {proxy_info['proxy']} | 分数:{proxy_info['score']} | 支持:{support_str} | {transparent_str}")

        save_choice = input("[input] 是否保存到文件? (y/n): ").lower().strip()
        if save_choice == "y":
            filename = input("[input] 请输入文件名(默认proxies.csv): ") or "proxies.csv"
            with open(filename, "w", encoding="utf-8") as file:
                for proxy_info in proxies:
                    file.write(f"{proxy_info['proxy']}\n")
            print(f"[success] 已保存到 {filename}")
    except ValueError:
        print("[error] 请输入有效的数字")
###


# MAIN 调度层 - 显示代理池状态
# 显示代理池状态(按类型、分数、支持范围和透明代理等统计)
def show_proxy_pool_status():
    """显示代理池状态"""
    proxies, proxy_info = load_proxies_from_db(current_config["main"]["db_file"])
    total = len(proxies)

    if total == 0:
        print("[failed] 代理池为空")
        return

    # 获取每行显示的项目数
    items_per_row = current_config["main"].get("number_of_items_per_row", 5)

    # 按类型分组
    type_groups = {}
    for proxy, score in proxies.items():
        info = proxy_info.get(proxy, {})
        proxy_types = info.get('types', ['unknown'])
        # 确保proxy_types是列表
        if not isinstance(proxy_types, list):
            print(f"[warning] 代理 {proxy} 的types字段不是列表: {proxy_types}")
            proxy_types = ['unknown']
        for proxy_type in proxy_types:
            if proxy_type not in type_groups:
                type_groups[proxy_type] = []
            type_groups[proxy_type].append((proxy, score, info))

    print(f"\n[info] 代理池状态 ({current_config['main']['db_file']}):")
    print(f"总代理数量: {total}")
    print(f"每行显示项目数: {items_per_row}")

    # 支持范围统计
    china_only = 0
    intl_only = 0
    both_support = 0
    no_support = 0

    for proxy, info in proxy_info.items():
        support = info.get('support', {})
        china = support.get('china', False)
        international = support.get('international', False)

        if china and not international:
            china_only += 1
        elif not china and international:
            intl_only += 1
        elif china and international:
            both_support += 1
        else:
            no_support += 1

    # 透明代理统计
    transparent_count = sum(1 for info in proxy_info.values() if info.get('transparent', False))
    anonymous_count = total - transparent_count

    # 浏览器验证统计
    browser_valid_count = 0
    browser_invalid_count = 0
    browser_unknown_count = 0

    for info in proxy_info.values():
        browser = info.get('browser', {})
        if browser.get('valid') is True:
            browser_valid_count += 1
        elif browser.get('valid') is False:
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
        f"验证失败: {browser_invalid_count}个",
        f"未验证/未知: {browser_unknown_count}个"
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

    print('=' * 40)
    print(f'总计: {total} 个代理')
###


# MAIN 调度层 - API服务
# 启动API服务器
def start_api_server(current_host,current_port):
    """启动API服务器"""

    print("[info] 启动代理池API服务器...")
    print(f"[info] 服务将在 http://{current_host}:{current_port} 运行")
    print("[info] 按 Ctrl+C 停止服务")

    try:
        # 使用当前Python解释器运行API服务器
        subprocess.run([sys.executable, "api.py"])
    except KeyboardInterrupt:
        print("\n[info] API服务已停止")
    except Exception as e:
        print(f"[error] 启动API服务失败: {e}")

# 测试API连接
def test_api_connection(current_host,current_port):
    """测试API连接"""
    try:
        response = requests.get(f"http://{current_host}:{current_port}/health", timeout=5)
        if response.status_code == 200:
            print("[success] API服务连接正常")
            data = response.json()
            print(f"状态: {data.get('status')}")
            print(f"加载代理数: {data.get('proxies_loaded', 0)}")
        else:
            print(f"[failed] API连接异常: {response.status_code}")
    except Exception as e:
        print(f"[error] 连接失败: {e}")

# 通过API获取代理
def get_proxy_via_api(current_host,current_port):
    """通过API获取代理"""
    try:

        # 获取用户输入
        proxy_type = input("[input] 代理类型 (默认http): ") or "http"
        min_score = input("[input] 最低分数 (默认0): ") or "0"

        # 调用API
        data = {
            "proxy_type": proxy_type,
            "min_score": int(min_score),
            "task_id": f"manual_{int(time.time())}"
        }

        resp = requests.post(f"http://{current_host}:{current_port}/proxy/acquire", json=data, timeout=10)

        if resp.status_code == 200:
            proxy_data = resp.json()["data"]
            print(f"[success] 获取到代理: {proxy_data['proxy']}")
            print(f"分数: {proxy_data['proxy_info']['score']}")
            print(f"任务ID: {proxy_data['task_id']}")

            # 显示代理信息
            info = proxy_data['proxy_info']['info']
            print(f"类型: {info.get('types', [])}")
            print(f"支持国内: {info.get('support', {}).get('china', False)}")
            print(f"支持国际: {info.get('support', {}).get('international', False)}")

            # 是否释放代理
            release = input("[input] 是否立即释放代理? (y/n): ").lower()
            if release == 'y':
                release_data = {
                    "proxy": proxy_data["proxy"],
                    "task_id": proxy_data["task_id"],
                    "success": True
                }
                resp = requests.post(f"http://{current_host}:{current_port}/proxy/release", json=release_data, timeout=5)
                if resp.status_code == 200:
                    print(f"[success] 代理已释放,返回{resp}")
                else:
                    print("[error] 释放失败")
        else:
            print(f"[failed] 获取代理失败: {resp.status_code} - {resp.text}")

    except Exception as e:
        print(f"[error] API调用失败: {e}")

# 获取API统计
def get_api_stats(current_host,current_port):
    """获取API统计"""
    try:
        response = requests.get(f"http://{current_host}:{current_port}/proxy/stats", timeout=5)
        if response.status_code == 200:
            data = response.json()["data"]
            print(f"\n[info] 代理池统计:")
            print(f"总代理数: {data.get('total', 0)}")
            print(f"空闲代理: {data.get('idle', 0)}")
            print(f"占用代理: {data.get('busy', 0)}")
            print(f"死亡代理: {data.get('dead', 0)}")
            print(f"最后更新: {data.get('last_updated', '未知')}")
        else:
            print(f"[failed] 获取统计失败: {response.status_code}")
    except Exception as e:
        print(f"[error] 获取统计失败: {e}")

# 让api重新加载代理池
def reload_proxy_api(current_host,current_port):
    """让api重新加载代理池"""
    try:
        response = requests.get(f"http://{current_host}:{current_port}/proxy/reload", timeout=5)
        if response.status_code == 200:
            print(response.json()["message"])

        else:
            print(f"[failed] 请求失败: {response.status_code}")
    except Exception as e:
        print(f"[error] 失败: {e}")

# 生成api爬虫调用模板代码(.py)
def api_usage_template():
    """生成API爬虫调用模板代码"""
    template = settings.PROXY_POOL_USAGE_TEMPLATE

    # 获取保存路径
    print("[info] 请输入要保存的文件路径（例如：./api_client.py 或 ./clients/proxy_api.py）：")
    file_path = input("[input] 文件路径: ").strip()

    if not file_path:
        print("[warn] 未指定文件路径，操作已取消")
        return

    # 获取目录路径
    dir_path = os.path.dirname(file_path)

    # 检查目录是否存在
    if dir_path and not os.path.exists(dir_path):
        print(f"[warn] 目录不存在: {dir_path}")
        create_choice = input("[input] 是否创建目录? (y/n): ").strip().lower()

        if create_choice == 'y' or create_choice == 'yes':
            try:
                os.makedirs(dir_path, exist_ok=True)
                print(f"[success] 目录已创建: {dir_path}")
            except Exception as e:
                print(f"[error] 创建目录失败: {e}")
                return
        else:
            print("[info] 操作已取消")
            return

    # 检查文件是否存在
    if os.path.exists(file_path):
        print(f"[warn] 文件已存在: {file_path}")
        overwrite_choice = input("[input] 是否覆盖? (y/n): ").strip().lower()

        if not (overwrite_choice == 'y' or overwrite_choice == 'yes'):
            print("[info] 操作已取消")
            return

    try:
        # 写入模板文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(template)

        print(f"[success] API调用模板已生成到: {file_path}")
        print(f"[info] 文件大小: {len(template)} 字节")

        # 显示文件绝对路径
        abs_path = os.path.abspath(file_path)
        print(f"[info] 绝对路径: {abs_path}")

    except Exception as e:
        print(f"[error] 写入文件失败: {e}")


# 调用 - 集成菜单
def api_integration_menu():
    """API集成菜单"""
    print("""\n[choice] === API集成功能 ===
    1: 启动代理池API服务
    2: 测试API连接
    3: 通过API获取代理
    4: 查看API统计
    5: 让api重新加载代理池
    6: 生成api爬虫调用模板代码(.py)
    其他: 返回上级菜单
    """)

    choice = input("[input] 请选择:").strip()

    current_host = current_config.get("api",{"host":"0.0.0.0"}).get("host","0.0.0.0")
    current_port = current_config.get("api",{"port":8000}).get("port",8000)

    if choice == "1":
        start_api_server(current_host,current_port)
    elif choice == "2":
        test_api_connection(current_host,current_port)
    elif choice == "3":
        get_proxy_via_api(current_host,current_port)
    elif choice == "4":
        get_api_stats(current_host,current_port)
    elif choice == "5":
        reload_proxy_api(current_host,current_port)
    elif choice == "6":
        api_usage_template()
    else:
        return
###


# MAIN 同步层 - 与github同步代理池
# 从GitHub下载代理池并合并到本地数据库
def download_from_github():
    """从GitHub下载代理池并合并到本地数据库"""
    print("\n[start] 开始从GitHub下载代理池...")

    github_url = "https://raw.githubusercontent.com/LiMingda-101212/Proxy-Pool-Actions/refs/heads/main/proxies.csv"

    try:
        # 下载GitHub上的代理池
        response = requests.get(github_url, timeout=30)
        if response.status_code != 200:
            print(f"[failed] 下载失败，状态码: {response.status_code}")
            return

        # 解析GitHub代理池（精简格式）
        content = response.text.strip().split('\n')
        reader = csv.reader(content)

        # 加载现有数据库
        existing_proxies, existing_info = load_proxies_from_db(current_config["main"]["db_file"])

        for row in reader:
            if len(row) < 7:  # 精简格式至少7列
                continue

            # GitHub精简格式: 类型,proxy:port,分数,China,International,Transparent,DetectedIP
            proxy_type = row[0].strip().lower()
            proxy = row[1].strip()

            try:
                score = int(row[2])
                china = row[3].strip().lower() == 'true'
                international = row[4].strip().lower() == 'true'
                transparent = row[5].strip().lower() == 'true'
                detected_ip = row[6].strip() if len(row) > 6 else "unknown"

                # 构建info字典
                info = existing_info.get(proxy, {})

                # 更新types（合并去重）
                current_types = info.get("types", [])
                if proxy_type not in current_types:
                    current_types.append(proxy_type)
                info["types"] = current_types

                # 更新支持范围（以GitHub数据为主）
                info["support"] = {
                    "china": china,
                    "international": international
                }

                # 更新透明代理和检测IP
                info["transparent"] = transparent
                info["detected_ip"] = detected_ip

                # 确保其他字段存在
                if "location" not in info:
                    info["location"] = {
                        "city": "unknown", "region": "unknown",
                        "country": "unknown", "loc": "unknown",
                        "org": "unknown", "postal": "unknown",
                        "timezone": "unknown"
                    }

                if "browser" not in info:
                    info["browser"] = {
                        "valid": False,
                        "check_date": "unknown",
                        "response_time": -1
                    }

                if "security" not in info:
                    info["security"] = {
                        "dns_hijacking": "unknown",
                        "ssl_valid": "unknown",
                        "malicious_content": "unknown",
                        "check_date": "unknown"
                    }

                if "performance" not in info:
                    info["performance"] = {
                        "avg_response_time": 5,
                        "success_rate": max(0.3, score / 100),
                        "last_checked": date.today().isoformat()
                    }
                else:
                    # 保持成功率，但使用GitHub的分数计算权重
                    info["performance"]["success_rate"] = max(
                        0.3,
                        (info["performance"]["success_rate"] * 0.7 + (score / 100) * 0.3)
                    )

                # 更新代理池
                existing_proxies[proxy] = score
                existing_info[proxy] = info

            except Exception as e:
                print(f"[error] 解析GitHub代理失败: {proxy} - {str(e)}")
                continue

        # 保存到数据库
        save_valid_proxies(existing_proxies, existing_info)

    except Exception as e:
        print(f"[error] 下载错误: {str(e)}")

# 检查GitHub Actions运行状态
def check_github_actions_status():
    """检查GitHub Actions运行状态"""
    try:
        # GitHub Actions状态API
        status_url = "https://api.github.com/repos/LiMingda-101212/Proxy-Pool-Actions/actions/runs"

        response = requests.get(status_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("workflow_runs"):
                latest_run = data["workflow_runs"][0]
                status = latest_run.get("status", "unknown")
                conclusion = latest_run.get("conclusion", "unknown")

                print(f"GitHub Actions状态: {status}")
                print(f"执行结果: {conclusion}")

                # 如果正在运行或等待中，返回False
                if status in ["in_progress", "queued", "pending"]:
                    return False
                else:
                    return True
        return True
    except Exception as e:
        print(f"[warning] 检查GitHub Actions状态失败: {str(e)}")
        # 如果检查失败，默认允许上传
        return True

# 上传本地代理池数据库到GitHub
def upload_to_github():
    """上传本地数据库代理池到GitHub - 转换为精简格式"""
    print("\n[start] 开始上传本地代理池到GitHub...")

    # 检查GitHub Actions状态
    print("检查GitHub Actions运行状态...")
    if not check_github_actions_status():
        print("[failed] GitHub Actions正在运行，请等待完成后重试")
        return

    print("[success] GitHub Actions未运行，可以上传")

    # 加载本地数据库
    local_proxies, local_info = load_proxies_from_db(current_config["main"]["db_file"])

    if not local_proxies:
        print("[failed] 本地代理池为空，无法上传")
        return

    print(f"准备上传 {len(local_proxies)} 个代理到GitHub（精简格式）")

    with open('data/config.json', "r", encoding='utf-8') as f:
        config_data = json.loads(f.read())
        token = config_data["github"]["token"]

    if not token:
        print("[failed] 未提供Token，上传取消")
        return

    try:
        # GitHub API信息
        repo_owner = "LiMingda-101212"
        repo_name = "Proxy-Pool-Actions"
        file_path = "proxies.csv"

        # 首先获取文件当前SHA（如果存在）
        api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }

        # 检查文件是否存在
        response = requests.get(api_url, headers=headers, timeout=10)
        sha = None
        if response.status_code == 200:
            sha = response.json().get("sha")
            print("[success] 找到现有文件，将更新")
        else:
            print("[success] 未找到现有文件，将创建新文件")

        # 准备文件内容 - 转换为GitHub精简格式
        import io
        output = io.StringIO()
        writer = csv.writer(output)

        # 写入CSV内容 - 使用GitHub精简格式
        for proxy, score in local_proxies.items():
            if score <= 0:
                continue

            info = local_info.get(proxy, {})

            # 获取类型（使用第一个类型）
            types = info.get("types", ['http'])
            proxy_type = types[0] if types else 'http'

            # 获取支持范围
            support = info.get("support", {})
            china = support.get("china", False)
            international = support.get("international", False)

            # 获取透明代理状态
            transparent = info.get("transparent", False)

            # 获取检测IP
            detected_ip = info.get("detected_ip", 'unknown')

            # 转换为GitHub精简格式
            # 格式：类型,proxy:port,分数,China,International,Transparent,DetectedIP
            writer.writerow([
                proxy_type,
                proxy,
                score,
                str(china).lower(),
                str(international).lower(),
                str(transparent).lower(),
                detected_ip
            ])

        content = output.getvalue()

        # 正确进行Base64编码
        import base64
        content_base64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')

        # 上传文件
        data = {
            "message": f"Update proxies pool - {len(local_proxies)} proxies",
            "content": content_base64
        }

        if sha:
            data["sha"] = sha

        print("正在上传文件到GitHub...")
        response = requests.put(api_url, headers=headers, json=data, timeout=30)

        if response.status_code in [200, 201]:
            print(f"[success] 上传成功! 已上传 {len(local_proxies)} 个代理（精简格式）")

            # 显示上传详情
            result = response.json()
            commit_sha = result.get("commit", {}).get("sha", "unknown")
            print(f"提交SHA: {commit_sha[:8]}...")

        else:
            error_msg = response.json().get("message", "未知错误")
            print(f"[failed] 上传失败: {error_msg}")
            print(f"状态码: {response.status_code}")

    except Exception as e:
        print(f"[error] 上传失败: {str(e)}")
        import traceback
        traceback.print_exc()

# 调用 - 主控制板
def synchronous_proxy_pool_menu():
    """同步代理池功能 - 与GitHub仓库同步"""
    print("""\n[choice] === 代理池同步功能 ===
    1: 从GitHub下载代理池(合并到本地)
    2: 上传本地代理池到GitHub

    输入其他: 返回上级菜单
    """)

    choice = input("[input] 请选择: ").strip()

    if choice == "1":
        download_from_github()
    elif choice == "2":
        # 再次确认
        print("[info] 再次确认")
        upload = input("[input] 输入任意内容以继续,不输入则取消:")
        if len(upload) == 0:
            print("[info] 取消上传")
        else:
            upload_to_github()

    else:
        return
###


###### 上方为代理池主要逻辑,下方为其它功能


# MAIN 帮助菜单
def show_help():
    """帮助菜单"""
    print("[info] === 帮助菜单 ===")
    print(f"""
{settings.INFO}

支持http/socks4/socks5

功能介绍:
本程序用于代理管理,有以下几个功能:
1.加载和验证新代理,可从爬虫(自动),本地文件(用于手动添加代理时使用,可以选择代理类型(这样比较快),也可用自动检测(若用自动检测可能较慢))加载,并将通过的代理添加到代理池数据库(SQLite).新代理使用自动检测类型或指定类型.在验证之前会先将重复代理,错误代理筛除,确保不做无用功.满分100分,新代理只要通过百度或Google任一验证就98分,错误代理和无效代理0分(会被0分清除函数清除).支持透明代理检测功能，识别会泄露真实IP的代理.有中断恢复功能,当验证过程被中断时,会自动保存已完成的代理到代理池,未完成的代理保存到中断文件,下次可选择继续验证

2.检验和更新代理池内代理的有效性,使用代理池中的Type作为类型,最后两个分别是是否支持国内和国外,再次验证成功一个(国内/国外)加1分,全成功加2分,无效代理和错误代理减1分,更直观的分辨代理的稳定性.支持透明代理检测功能，识别会泄露真实IP的代理.有中断恢复功能,当验证过程被中断时,会自动保存已完成的代理到代理池,未完成的代理保存到中断文件,下次可选择继续验证

3.浏览器验证功能，使用Playwright验证代理在真实浏览器环境中的可用性,有中断恢复功能

4.代理安全验证 - 开发中

5.提取指定数量的代理,优先提取分数高,稳定的代理,可指定提取类型,支持范围,是否为透明代理,浏览器是否可用

6.查看代理池状态(总代理数量,各种类型代理的分数分布情况,透明代理,支持范围,浏览器是否可用统计)

7.与部署在github上由actions自动维护的代理池合并,主要字段以github为主

8.api服务,便于各种爬虫调用

9.清理代理池数据库中的0分代理

setting.各种设置

help.帮助菜单

代理池({current_config["main"]["db_file"]})

    """)

    wait = input('[input] 回车继续:')
###


# MAIN 设置
# 加载设置
def load_settings():
    """加载设置"""
    try:
        with open("data/config.json", "r", encoding="utf-8") as f:
            config = json.loads(f.read())
        return config
    except FileNotFoundError:
        print("[error] 配置文件不存在: data/config.json")
        return None
    except json.JSONDecodeError:
        print("[error] 配置文件格式错误")
        return None
    except Exception as e:
        print(f"[error] 加载配置时出错: {e}")
        return None

# 保存设置
def save_settings(config):
    """保存设置"""
    try:
        with open("data/config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print("[success] 配置已保存!")
        return True
    except Exception as e:
        print(f"[error] 保存配置时出错: {e}")
        return False

# 通用输入函数
def get_input(prompt: str, current_value: Any,input_type: Type = str,validation: Callable[[Any], bool] = None) -> Any:
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
                if user_input.lower() in ['true', '1', 'yes', 'y']:
                    value = True
                elif user_input.lower() in ['false', '0', 'no', 'n']:
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
def edit_main_settings(config):
    """编辑主要设置"""
    print(f"""[info] 当前设置:
        1:透明代理检查:{"开启" if config["main"]["check_transparent"].lower() == "true" else "关闭"}
        2:获取IP信息:{"开启" if config["main"]["get_ip_info"].lower() == "true" else "关闭"}
        3:高分代理范围不低于:{config["main"]["high_score_agency_scope"]}
        4:国内测试URL:{config["main"]["test_url_cn"]}
        5:国际测试URL:{config["main"]["test_url_intl"]}
        6:国内测试超时:{config["main"]["timeout_cn"]}秒
        7:国际测试超时:{config["main"]["timeout_intl"]}秒
        8:透明代理测试超时:{config["main"]["timeout_transparent"]}秒
        9:IP信息获取超时:{config["main"]["timeout_ipinfo"]}秒
        10:最大并发数:{config["main"]["max_workers"]}
        11:输出数据库:{config["main"]["db_file"]}
        12:最大分数:{config["main"]["max_score"]}
        13:代理池状态每行显示各分数段数量:{config["main"]["number_of_items_per_row"]}
    """)

    edit_choice = input("[input] 修改项目序号(回车不修改):")

    if not edit_choice:
        return False

    try:
        if edit_choice == "1":
            # 切换透明代理检查
            current_value = config["main"]["check_transparent"].lower() == "true"
            new_value = not current_value
            config["main"]["check_transparent"] = str(new_value)
            print(f"[success] 透明代理检查已{'开启' if new_value else '关闭'}")

        elif edit_choice == "2":
            # 切换获取IP信息
            current_value = config["main"]["get_ip_info"].lower() == "true"
            new_value = not current_value
            config["main"]["get_ip_info"] = str(new_value)
            print(f"[success] 获取IP信息已{'开启' if new_value else '关闭'}")

        elif edit_choice == "3":
            # 修改高分代理范围
            def validate_scope(value):
                if 0 <= value <= 100:
                    return True
                print("[failed] 请输入0-100之间的数字")
                return False

            new_scope = get_input("请输入新的高分代理范围",
                                  config['main']['high_score_agency_scope'],
                                  int, validate_scope)
            config["main"]["high_score_agency_scope"] = new_scope
            print(f"[success] 高分代理范围已设置为: {new_scope}")

        elif edit_choice == "4":
            # 修改国内测试URL
            new_url = get_input("请输入新的国内测试URL", config["main"]["test_url_cn"])
            config["main"]["test_url_cn"] = new_url
            print(f"[success] 国内测试URL已设置为: {new_url}")

        elif edit_choice == "5":
            # 修改国际测试URL
            new_url = get_input("请输入新的国际测试URL", config["main"]["test_url_intl"])
            config["main"]["test_url_intl"] = new_url
            print(f"[success] 国际测试URL已设置为: {new_url}")

        elif edit_choice == "6":
            # 修改国内测试超时
            new_timeout = get_input("请输入新的国内测试超时时间(秒)",
                                    config['main']['timeout_cn'], int)
            config["main"]["timeout_cn"] = new_timeout
            print(f"[success] 国内测试超时已设置为: {new_timeout}秒")

        elif edit_choice == "7":
            # 修改国际测试超时
            new_timeout = get_input("请输入新的国际测试超时时间(秒)",
                                    config['main']['timeout_intl'], int)
            config["main"]["timeout_intl"] = new_timeout
            print(f"[success] 国际测试超时已设置为: {new_timeout}秒")

        elif edit_choice == "8":
            # 修改透明代理测试超时
            new_timeout = get_input("请输入新的透明代理测试超时时间(秒)",
                                    config['main']['timeout_transparent'], int)
            config["main"]["timeout_transparent"] = new_timeout
            print(f"[success] 透明代理测试超时已设置为: {new_timeout}秒")

        elif edit_choice == "9":
            # 修改IP信息获取超时
            new_timeout = get_input("请输入新的IP信息获取超时时间(秒)",
                                    config['main']['timeout_ipinfo'], int)
            config["main"]["timeout_ipinfo"] = new_timeout
            print(f"[success] IP信息获取超时已设置为: {new_timeout}秒")

        elif edit_choice == "10":
            # 修改最大并发数
            new_workers = get_input("请输入新的最大并发数",
                                    config['main']['max_workers'], int)
            config["main"]["max_workers"] = new_workers
            print(f"[success] 最大并发数已设置为: {new_workers}")

        elif edit_choice == "11":
            # 修改输出数据库路径
            new_path = get_input("请输入新的输出数据库(SQLite)路径", config["main"]["db_file"])
            config["main"]["db_file"] = new_path
            print(f"[success] 输出路径已设置为: {new_path}")

        elif edit_choice == "12":
            # 修改最大分数
            new_score = get_input("请输入新的最大分数",
                                  config['main']['max_score'], int)
            config["main"]["max_score"] = new_score
            print(f"[success] 最大分数已设置为: {new_score}")

        elif edit_choice == "13":
            # 修改每行显示项目数
            def validate_items_per_row(value):
                if 1 <= value <= 20:
                    return True
                print("[failed] 请输入1-20之间的数字")
                return False

            new_items = get_input("请输入每行显示的项目数",
                                  config['main']['number_of_items_per_row'],
                                  int, validate_items_per_row)
            config["main"]["number_of_items_per_row"] = new_items
            print(f"[success] 每行显示项目数已设置为: {new_items}")

        else:
            print("[info] 无效的选择，返回上级菜单")
            return False

        return True

    except Exception as e:
        print(f"[error] 修改配置时出错: {e}")
        return False

# 编辑中断设置
def edit_interrupt_settings(config):
    """编辑中断设置"""
    print(f"""[info] 中断设置:
        1:中断文件目录:{config["interrupt"]["interrupt_dir"]}
        2:爬取验证中断文件:{config["interrupt"]["interrupt_file_crawl"]}
        3:本地文件加载中断文件:{config["interrupt"]["interrupt_file_load"]}
        4:更新代理池中断文件:{config["interrupt"]["interrupt_file_existing"]}
        5:安全性验证中断文件:{config["interrupt"]["interrupt_file_safety"]}
        6:浏览器验证中断文件:{config["interrupt"]["interrupt_file_browser"]}
    """)

    edit_choice = input("[input] 修改项目序号(回车不修改):")

    if not edit_choice:
        return False

    try:
        if edit_choice == "1":
            new_dir = get_input("请输入新的中断文件目录", config['interrupt']['interrupt_dir'])
            config["interrupt"]["interrupt_dir"] = new_dir
            print(f"[success] 中断文件目录已设置为: {new_dir}")

        elif edit_choice == "2":
            new_file = get_input("请输入新的爬取验证中断文件名",
                                 config['interrupt']['interrupt_file_crawl'])
            config["interrupt"]["interrupt_file_crawl"] = new_file
            print(f"[success] 爬取验证中断文件名已设置为: {new_file}")

        elif edit_choice == "3":
            new_file = get_input("请输入新的本地文件加载中断文件名",
                                 config['interrupt']['interrupt_file_load'])
            config["interrupt"]["interrupt_file_load"] = new_file
            print(f"[success] 本地文件加载中断文件名已设置为: {new_file}")

        elif edit_choice == "4":
            new_file = get_input("请输入新的更新代理池中断文件名",
                                 config['interrupt']['interrupt_file_existing'])
            config["interrupt"]["interrupt_file_existing"] = new_file
            print(f"[success] 更新代理池中断文件名已设置为: {new_file}")

        elif edit_choice == "5":
            new_file = get_input("请输入新的安全性验证中断文件名",
                                 config['interrupt']['interrupt_file_safety'])
            config["interrupt"]["interrupt_file_safety"] = new_file
            print(f"[success] 安全性验证中断文件名已设置为: {new_file}")

        elif edit_choice == "6":
            new_file = get_input("请输入新的浏览器验证中断文件名",
                                 config['interrupt']['interrupt_file_browser'])
            config["interrupt"]["interrupt_file_browser"] = new_file
            print(f"[success] 浏览器验证中断文件名已设置为: {new_file}")

        else:
            print("[info] 无效的选择，返回上级菜单")
            return False

        return True

    except Exception as e:
        print(f"[error] 修改中断设置时出错: {e}")
        return False

# 编辑GitHub设置
def edit_github_settings(config):
    """编辑GitHub设置"""
    print(f"""[info] GitHub同步设置:
        1: GitHub Token: {config["github"]["token"][0:15] + ("*" * (len(config["github"]["token"])-15)) if config["github"]["token"] else "未设置"}
    """)

    edit_choice = input("[input] 修改项目序号(回车不修改):")

    if not edit_choice:
        return False

    try:
        if edit_choice == "1":
            current_token = config["github"]["token"]
            masked_token = "*" * len(current_token) if current_token else "未设置"
            new_token = input(f"[input] 请输入新的GitHub Token(当前:{masked_token}): ").strip()
            if new_token:
                config["github"]["token"] = new_token
                print("[success] GitHub Token已更新")
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
def edit_api_settings(config):
    """编辑API设置"""
    print(f"""[info] API设置:
        1: host: {config["api"]["host"]}
        2: port: {config["api"]["port"]}
    """)
    edit_choice = input("[input] 修改项目序号(回车不修改):")

    if not edit_choice:
        return False

    try:
        if edit_choice == "1":
            current_host = config["api"]["host"]
            new_host = input(f"[input] 请输入新的API host(当前:{current_host}): ").strip()
            if new_host:
                config["api"]["host"] = new_host
                print("[success] host已更新")
            else:
                print("[info] 未修改host")

        elif edit_choice == "2":
            try:
                current_port = config["api"]["port"]
                new_host = input(f"[input] 请输入新的API port(当前:{current_port}): ").strip()
                if new_host and ((int(new_host) > 0) and (int(new_host) < 65535 )):
                    config["api"]["port"] = int(new_host)
                    print("[success] port已更新")
                else:
                    print("[info] 未修改port,请输入有效端口数字")
            except:
                print("[error] 输入有效数字")

        else:
            print("[info] 无效的选择，返回上级菜单")
            return False

        return True

    except Exception as e:
        print(f"[error] 修改api设置时出错: {e}")
        return False

# 调用 - 更改和查看设置
def setting():
    """更改和查看设置"""
    config = load_settings()
    if config is None:
        return

    while True:
        print("""[info] === 更改和查看设置 ===
        类别:
            1:主要设置
            2:中断设置
            3:github同步设置
            4:API设置
            其他:返回上级菜单
        """)
        class_choice = input("[input] 类别选择(1/2/3/4):").strip()

        if class_choice == "1":
            if edit_main_settings(config):
                save_settings(config)
        elif class_choice == "2":
            if edit_interrupt_settings(config):
                save_settings(config)
        elif class_choice == "3":
            if edit_github_settings(config):
                save_settings(config)
        elif class_choice == "4":
            if edit_api_settings(config):
                save_settings(config)
        else:
            print("[info] 返回上级菜单")
            break
###


# MAIN 初始化函数
def initialize():
    """初始化函数"""
    print("[info] 初始化中...")
    print("----------")
    try:
        # 创建中断目录
        result = create_interrupt_dir()
        print("[success] 创建中断目录成功" if result == True else f"[failed] 创建中断目录失败|{result}")

        # 设置信号处理器
        result = setup_interrupt_handler()
        print("[success] 设置信号处理器成功" if result == True else f"[failed] 设置信号处理器失败|{result}")

    except Exception as e:
        print(f"[error] 初始化失败: {e}")

    print("----------\n")
###

# MAIN GPL 要求
def show_gpl_notice():
    """显示GPL要求的版权声明"""
    print("""
    ProxyPool - 高效代理池管理工具
    Copyright (C) 2025  李明达

    本程序是自由软件：您可以根据自由软件基金会发布的
    GNU通用公共许可证第三版或（您选择的）任何更高版本
    重新分发和/或修改它。

    本程序分发的目的是希望它有用，但没有任何担保；
    甚至没有适销性或特定用途适用性的隐含担保。
    有关更多详细信息，请参阅GNU通用公共许可证。

    您应该已经随本程序收到了GNU通用公共许可证的副本。
    如果没有，请访问 <https://www.gnu.org/licenses/>。
    """)

    # GPL建议添加的交互命令提示
    print("\n输入 'show w' 查看保修信息")
    print("输入 'show c' 查看再分发条件")

def show_warranty():
    """显示保修信息（GPL要求）"""
    print("""
    本程序不提供任何担保，在法律允许的最大范围内。
    详细条款请参考GNU通用公共许可证第15、16条。
    """)

def show_conditions():
    """显示再分发条件（GPL要求）"""
    print("""
    您可以自由地再分发本程序，但必须遵守以下条件：
    1. 保留原始版权声明和许可证信息
    2. 提供完整的源代码
    3. 修改后的版本必须以相同许可证发布
    完整条款请查看GNU通用公共许可证。
    """)


if __name__ == '__main__':
    show_gpl_notice()

    # 初始化
    initialize()

    while True:
        current_config = load_settings()
        print(f"""[choice] 功能:
        1: 加载并验证新代理 (成功后添加到代理池)
        2: 检验并更新已有代理 (更新代理池代理分数)
        3: 浏览器使用验证 (检测出浏览器可用代理)
        4: 代理安全验证 (检验代理安全性) - 开发中
        5: 筛选并提取代理
        6: 查看代理池状态
        7: 同步代理池 (与GitHub Actions同步)
        8: API服务
        9: 清理数据库中的0分代理

        setting: 设置
        help: 帮助文档
        show w: 保修信息
        show c: 再分发条件
        输入其他: 退出
        """)

        function_choice = input("[input] 选择：").strip()

        if function_choice == "1":
            # 新代理获取模块+检测模块
            validate_new_proxies_menu()

        elif function_choice == "2":
            # 已有代理检测模块
            validate_existing_proxies()

        elif function_choice == "3":
            # 代理浏览器可用检测模块
            browser_validation_menu()

        elif function_choice == "4":
            # 代理安全检测模块
            pass

        elif function_choice == "5":
            # 手动提取模块
            extract_proxies_menu()

        elif function_choice == "6":
            # 代理池状态模块
            show_proxy_pool_status()

        elif function_choice == "7":
            # 云端同步模块
            synchronous_proxy_pool_menu()

        elif function_choice == "8":
            # API集成模块
            api_integration_menu()

        elif function_choice == "9":
            # 清理0分代理模块
            cleanup_zero_score_menu()

        elif function_choice.lower().strip() == 'help':
            # 帮助模块
            show_help()

        elif function_choice.lower().strip() == 'setting':
            # 设置模块
            setting()

        elif function_choice.lower().strip() == 'show w':
            # 保修信息
            show_warranty()

        elif function_choice.lower().strip() == 'show c':
            # 再分发条件
            show_conditions()

        else:
            print('[exit] 退出')
            break