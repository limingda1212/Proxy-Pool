# -*- coding: utf-8 -*-
# 数据库操作

import sqlite3
import json
import os
from datetime import date
from typing import Dict, Any, Tuple

class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path


    # def load_proxies_from_db(self) -> Tuple[Dict[str, int], Dict[str, Any]]:
    #     """
    #     从SQLite数据库加载代理
    #     :return: 代理分数字典, 代理信息字典
    #     """
    #     proxies = {}
    #     proxy_info = {}
    #
    #     if not os.path.exists(self.db_path):
    #         return proxies, proxy_info
    #
    #     conn = None
    #
    #     try:
    #         conn = sqlite3.connect(self.db_path)
    #         cursor = conn.cursor()
    #
    #         cursor.execute('''
    #         SELECT
    #             proxy, score, types, support_china, support_international,
    #             transparent, detected_ip, city, region, country, loc, org,
    #             postal, timezone, browser_valid, browser_check_date,
    #             browser_response_time, dns_hijacking, ssl_valid,
    #             malicious_content, data_integrity, behavior_analysis,
    #             security_check_date, avg_response_time,
    #             success_rate, last_checked
    #         FROM proxies
    #         ''')
    #
    #         for row in cursor.fetchall():
    #             proxy = row[0]
    #             score = row[1]
    #             types_json = row[2]
    #
    #             # 构造代理信息字典,方便使用
    #             info = {
    #                 "types": json.loads(types_json) if types_json else [],
    #                 "support": {
    #                     "china": bool(row[3]),
    #                     "international": bool(row[4])
    #                 },
    #                 "transparent": bool(row[5]),
    #                 "detected_ip": row[6],
    #                 "location": {
    #                     "city": row[7],
    #                     "region": row[8],
    #                     "country": row[9],
    #                     "loc": row[10],
    #                     "org": row[11],
    #                     "postal": row[12],
    #                     "timezone": row[13]
    #                 },
    #                 "browser": {
    #                     "valid": bool(row[14]),
    #                     "check_date": row[15],
    #                     "response_time": row[16]
    #                 },
    #                 "security": {
    #                     "dns_hijacking": row[17],
    #                     "ssl_valid": row[18],
    #                     "malicious_content": row[19],
    #                     "data_integrity" : row[20],
    #                     "behavior_analysis" : row[21],
    #                     "check_date" : row[22]
    #                 },
    #                 "performance": {
    #                     "avg_response_time": row[23],
    #                     "success_rate": row[24],
    #                     "last_checked": row[25]
    #                 }
    #             }
    #
    #             proxies[proxy] = score
    #             proxy_info[proxy] = info
    #
    #     except Exception as e:
    #         print(f"[error] 从数据库加载代理失败: {e}")
    #     finally:
    #         if conn:
    #             conn.close()
    #
    #     return proxies, proxy_info
    # --- 更新: 字段通过列名获取 优势：无需维护索引顺序，代码更清晰，即使以后新增字段也只需在字典中添加，不会影响现有逻辑 ---
    def load_proxies_from_db(self) -> Tuple[Dict[str, int], Dict[str, Any]]:
        """
        从SQLite数据库加载代理
        :return: 代理分数字典, 代理信息字典
        """
        proxies = {}
        proxy_info = {}

        if not os.path.exists(self.db_path):
            return proxies, proxy_info

        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # 启用行工厂
            cursor = conn.cursor()

            # 使用 SELECT *
            cursor.execute('SELECT * FROM proxies')

            for row in cursor.fetchall():
                proxy = row['proxy']
                score = row['score']
                types_json = row['types']

                # 构造 info 字典，所有字段通过列名获取
                info = {
                    "types": json.loads(types_json) if types_json else [],
                    "support": {
                        "china": bool(row['support_china']),
                        "international": bool(row['support_international'])
                    },
                    "transparent": bool(row['transparent']),
                    "detected_ip": row['detected_ip'],
                    "location": {
                        "city": row['city'],
                        "region": row['region'],
                        "country": row['country'],
                        "loc": row['loc'],
                        "org": row['org'],
                        "postal": row['postal'],
                        "timezone": row['timezone']
                    },
                    "browser": {
                        "valid": bool(row['browser_valid']),
                        "check_date": row['browser_check_date'],
                        "response_time": row['browser_response_time']
                    },
                    "security": {
                        "dns_hijacking": row['dns_hijacking'],
                        "ssl_valid": row['ssl_valid'],
                        "malicious_content": row['malicious_content'],
                        "data_integrity": row['data_integrity'],
                        "behavior_analysis": row['behavior_analysis'],
                        "check_date": row['security_check_date']
                    },
                    "performance": {
                        "avg_response_time": row['avg_response_time'],
                        "success_rate": row['success_rate'],
                        "last_checked": row['last_checked']
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

    def save_valid_proxies(self, proxies: Dict[str, int], proxy_info: Dict[str, Any]):
        """
        保存代理到SQLite数据库
        :param proxies: 代理分数字典 {proxy: score}
        :param proxy_info: 代理信息字典 {proxy: info_dict}
        """
        if not proxies:
            return

        conn = None

        try:
            conn = sqlite3.connect(self.db_path)
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

                # 从 security 字典中提取字段（如果不存在则用默认值）
                dns_hijacking = security.get("dns_hijacking", "unknown")
                ssl_valid = security.get("ssl_valid", "unknown")
                malicious_content = security.get("malicious_content", "unknown")
                data_integrity = security.get("data_integrity", "unknown")
                behavior_analysis = security.get("behavior_analysis", "unknown")
                security_check_date = security.get("check_date", "unknown")

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
                            ssl_valid = ?, malicious_content = ?, data_integrity = ?, behavior_analysis = ?,
                            security_check_date = ?, avg_response_time = ?, success_rate = ?, last_checked = ?,
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
                        dns_hijacking,
                        ssl_valid,
                        malicious_content,
                        data_integrity,
                        behavior_analysis,
                        security_check_date,
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
                            malicious_content, data_integrity, behavior_analysis,
                            security_check_date, avg_response_time,
                            success_rate, last_checked
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        dns_hijacking,
                        ssl_valid,
                        malicious_content,
                        data_integrity,
                        behavior_analysis,
                        security_check_date,
                        performance.get("avg_response_time", 0),
                        performance.get("success_rate", 0.0),
                        performance.get("last_checked", date.today().isoformat())
                    ))
                    inserted_count += 1

            conn.commit()

            if updated_count > 0 or inserted_count > 0:
                print(f"[success] 保存到数据库: 更新/已有 {updated_count} 条, 新增 {inserted_count} 条")

        except Exception as e:
            print(f"[error] 保存代理到数据库失败: {e}")

        finally:
            if conn:
                conn.close()

    def cleanup_zero_score_proxies(self) -> int:
        """
        清理数据库中分数为0的代理

        :return: 清理的代理数量
        """
        if not os.path.exists(self.db_path):
            print(f"[info] 数据库文件不存在: {self.db_path}")
            return 0

        conn = None

        try:
            conn = sqlite3.connect(self.db_path)
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
