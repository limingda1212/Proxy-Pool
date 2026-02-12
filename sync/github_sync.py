# -*- coding: utf-8 -*-

import requests
import csv
import json
from datetime import date

from core.config import ConfigManager
from storage.database import DatabaseManager


class GithubSync:
    def __init__(self, config: ConfigManager, database: DatabaseManager):
        self.config = config
        self.database = database

    # 从GitHub下载代理池并合并到本地数据库"
    def download_from_github(self):
        """从GitHub下载代理池并合并到本地数据库"""
        print("\n[start] 开始从GitHub下载代理池...")

        default_url = "https://raw.githubusercontent.com/LiMingda-101212/Proxy-Pool-Actions/refs/heads/main/proxies.csv"
        github_url = self.config.get("github.down_url", default_url)
        # github_url = "https://raw.githubusercontent.com/LiMingda-101212/Proxy-Pool-Actions/refs/heads/main/proxies.csv"

        try:
            # 下载GitHub上的代理池
            response = requests.get(github_url, timeout=30)
            if response.status_code != 200:
                print(f"[failed] 下载失败，状态码: {response.status_code}")
                return

            # 解析GitHub代理池（精简格式）
            content = response.text.strip().split("\n")
            reader = csv.reader(content)

            # 加载现有数据库
            existing_proxies, existing_info = self.database.load_proxies_from_db()

            for row in reader:
                if len(row) < 7:  # 精简格式至少7列
                    continue

                # GitHub精简格式: 类型,proxy:port,分数,China,International,Transparent,DetectedIP
                proxy_type = row[0].strip().lower()
                proxy = row[1].strip()

                try:
                    score = int(row[2])
                    china = row[3].strip().lower() == "true"
                    international = row[4].strip().lower() == "true"
                    transparent = row[5].strip().lower() == "true"
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
            self.database.save_valid_proxies(existing_proxies, existing_info)

        except Exception as e:
            print(f"[error] 下载错误: {str(e)}")

    # 检查GitHub Actions运行状态
    def check_github_actions_status(self) -> bool:
        """检查GitHub Actions运行状态"""
        try:
            # GitHub Actions状态API
            github_repo_api = self.config.get("github.actions_repo_api", "https://api.github.com/repos/LiMingda-101212/Proxy-Pool-Actions")
            status_url = f"{github_repo_api}/actions/runs"

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

    # 上传本地数据库代理池到GitHub
    def upload_to_github(self):
        """上传本地数据库代理池到GitHub - 转换为精简格式"""
        print("\n[start] 开始上传本地代理池到GitHub...")

        # 检查GitHub Actions状态
        print("检查GitHub Actions运行状态...")
        if not self.check_github_actions_status():
            print("[failed] GitHub Actions正在运行，请等待完成后重试")
            return

        print("[success] GitHub Actions未运行，可以上传")

        # 加载本地数据库
        local_proxies, local_info = self.database.load_proxies_from_db()

        if not local_proxies:
            print("[failed] 本地代理池为空，无法上传")
            return

        print(f"准备上传 {len(local_proxies)} 个代理到GitHub（精简格式）")

        with open("data/config.json", "r", encoding="utf-8") as f:
            config_data = json.loads(f.read())
            token = config_data["github"]["token"]

        if not token:
            print("[failed] 未提供Token，上传取消")
            return

        try:
            # GitHub 信息
            github_repo_api = self.config.get("github.actions_repo_api", "https://api.github.com/repos/LiMingda-101212/Proxy-Pool-Actions")
            file_name = self.config.get("github.file_name","proxies.csv")

            # 首先获取文件当前SHA（如果存在）
            api_url = f"{github_repo_api}/contents/{file_name}"
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
                types = info.get("types", ["http"])
                proxy_type = types[0] if types else "http"

                # 获取支持范围
                support = info.get("support", {})
                china = support.get("china", False)
                international = support.get("international", False)

                # 获取透明代理状态
                transparent = info.get("transparent", False)

                # 获取检测IP
                detected_ip = info.get("detected_ip", "unknown")

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
            content_base64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")

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