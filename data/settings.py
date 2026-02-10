#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ProxyPool - 高效代理池管理工具
Copyright (C) 2026  李明达

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

# 基础信息
VERSION = "V2026-01-11"
INFO = f"""
******************************************
本项目采用 GNU General Public License v3.0 (GPL v3) 开源协议。
完整协议内容请查看 LICENSE 文件。

project: Proxy-Pool
version: {VERSION}

written by LiMingda <lmd101212@outlook.com>
"""


INTRODUCTION = """
支持http/socks4/socks5

功能介绍:
本程序用于代理管理,有以下几个功能:
- 1 .加载和验证新代理,可从爬虫(自动爬取,根据情况指定类型),本地文件(用于手动添加代理时使用,可以选择代理类型(这样比较快),也可用自动检测(若用自动检测可能较慢))加载,并将通过的代理添加到代理池.新代理使用自动检测类型或指定类型.在验证之前会先将重复代理,错误代理筛除(集合筛选),确保不做无用功.满分100分,新代理只要通过`百度`或`Google`任一验证就98分,错误代理和无效代理0分.支持透明代理检测功能，识别会泄露真实IP的代理.有中断恢复功能,当验证过程被中断时,会自动保存已完成的代理到代理池,未完成的代理保存到中断文件,下次可选择继续验证可以获取代理信息(城市,运营商等),对于已经有ip信息的代理不重复进行获取信息
- 2 .检验和更新代理池内代理的有效性,使用代理池文件中保存的上次结果类型作为验证使用类型,验证是否支持国内和国外,再次验证成功一个(国内/国外)加1分,全成功加2分,无效代理和错误代理减1分,更直观的分辨代理的稳定性.支持透明代理检测功能，识别会泄露真实IP的代理.
- 3 .浏览器使用验证,部分代理没法在浏览器中使用(安全问题),用`playwright`检测出浏览器可用代理.
- 4 .代理安全验证,检验代理安全性
- 5 .提取指定数量的代理,优先提取分数高,稳定的代理,可指定提取类型,支持范围,是否为透明代理,浏览器是否可用
- 6 .查看代理池状态(总代理数量,各种类型代理的分数分布情况,支持范围,浏览器是否可用统计)
- 7 .与部署在github上由actions自动维护的代理池合并,将github精简格式转为本地全面格式
- 8 .API服务,提供开启和调试功能.为了防止一个代理在不同爬虫被多次使用,使用了代理状态,未调用时`idle`,调用获取会使状态变为`busy`,失败会变为`dead`并很快会被清理.
setting.各种设置
help.帮助菜单
"""

# 爬取参数
HEADERS = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0"
}


# 代理池使用模板
PROXY_POOL_USAGE_TEMPLATE = r'''

import requests
import time
import uuid
from typing import Optional, Dict, Any
from contextlib import contextmanager


class ProxyPoolClient:
    """代理池客户端"""

    def __init__(self, api_url: str = "http://localhost:8000"):
        self.api_url = api_url.strip("/")
        self.current_proxy: Optional[str] = None
        self.task_id: Optional[str] = None
        self.last_heartbeat: float = 0

    def acquire_proxy(self,
                      proxy_type: str = "http",
                      support_region: str = "all",
                      min_score: int = 0,
                      exclude_proxies: Optional[list] = None) -> Optional[Dict[str, Any]]:
        """获取代理"""
        try:
            data = {
                "proxy_type": proxy_type,
                "support_region": support_region,
                "min_score": min_score,
                "exclude_proxies": exclude_proxies or [],
                "task_id": str(uuid.uuid4())
            }

            response = requests.post(
                f"{self.api_url}/proxy/acquire",
                json=data,
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()["data"]
                self.current_proxy = result["proxy"]
                self.task_id = result["task_id"]
                self.last_heartbeat = time.time()
                return result

        except requests.RequestException as e:
            print(f"获取代理失败: {e}")

        return None

    def release_proxy(self, success: bool = True, response_time: Optional[float] = None):
        """释放代理"""
        if not self.current_proxy or not self.task_id:
            return False

        try:
            data = {
                "proxy": self.current_proxy,
                "task_id": self.task_id,
                "success": success,
                "response_time": response_time
            }

            response = requests.post(
                f"{self.api_url}/proxy/release",
                json=data,
                timeout=5
            )

            print(response.json())

            if response.status_code == 200:
                self.current_proxy = None
                self.task_id = None
                return True

        except requests.RequestException as e:
            print(f"释放代理失败: {e}")

        return False

    def heartbeat(self) -> bool:
        """发送心跳"""
        if not self.current_proxy or not self.task_id:
            return False

        # 避免频繁发送心跳
        if time.time() - self.last_heartbeat < 60:
            return True

        try:
            data = {
                "proxy": self.current_proxy,
                "task_id": self.task_id
            }

            response = requests.post(
                f"{self.api_url}/proxy/heartbeat",
                json=data,
                timeout=5
            )

            if response.status_code == 200:
                self.last_heartbeat = time.time()
                return True

        except requests.RequestException:
            # 心跳失败不影响主流程
            pass

        return False

    @contextmanager
    def get_proxy(self, **kwargs):
        """使用上下文管理器获取代理"""
        proxy_data = self.acquire_proxy(**kwargs)

        if not proxy_data:
            yield None
            return

        try:
            yield proxy_data["proxy"]
            self.release_proxy(success=True)
        except Exception as e:
            print(f"使用代理时发生错误: {e}")
            self.release_proxy(success=False)
            raise

    def get_stats(self) -> Optional[Dict[str, Any]]:
        """获取统计信息"""
        try:
            response = requests.get(f"{self.api_url}/proxy/stats", timeout=5)
            if response.status_code == 200:
                return response.json()["data"]
        except:
            pass
        return None


# 使用示例
if __name__ == "__main__":
    # 创建客户端
    client = ProxyPoolClient("http://localhost:8000")

    # 示例1：基本使用
    proxy_data = client.acquire_proxy(
        proxy_type="http",
        support_region="china",
        min_score=90
    )

    if proxy_data:
        print(f"获取到代理: {proxy_data['proxy']}")

        # 使用代理进行请求
        try:
            response = requests.get(
                "https://httpbin.org/ip",
                proxies={"http": proxy_data["proxy"], "https": proxy_data["proxy"]},
                timeout=10
            )
            print(f"响应: {response.text}")
            client.release_proxy(success=True, response_time=response.elapsed.total_seconds())
        except Exception as e:
            print(f"请求失败: {e}")
            client.release_proxy(success=False)

    # 示例2：使用上下文管理器（推荐）
    with client.get_proxy(proxy_type="all", min_score=30) as proxy:
        if proxy:
            print(f"使用代理: {proxy}")
            # 在这里执行爬取任务
            # 不需要手动释放代理
            
    # 示例3：查看统计
    stats = client.get_stats()
    if stats:
        print(f"代理池统计: {stats}")
'''


# GitHub 代理源配置字典
GITHUB_PROXY_SOURCES = {
    "9": {
        "name": "databay-labs HTTP",
        "url": "https://raw.githubusercontent.com/databay-labs/free-proxy-list/refs/heads/master/http.txt",
        "type": "http",
        "cleanup": False
    },
    "10": {
        "name": "databay-labs SOCKS5",
        "url": "https://raw.githubusercontent.com/databay-labs/free-proxy-list/refs/heads/master/socks5.txt",
        "type": "socks5",
        "cleanup": False
    },
    "11": {
        "name": "databay-labs HTTPS",
        "url": "https://raw.githubusercontent.com/databay-labs/free-proxy-list/refs/heads/master/https.txt",
        "type": "http",
        "cleanup": False
    },
    "12": {
        "name": "hideip.me HTTP",
        "url": "https://raw.githubusercontent.com/zloi-user/hideip.me/refs/heads/master/http.txt",
        "type": "http",
        "cleanup": True
    },
    "13": {
        "name": "hideip.me HTTPS",
        "url": "https://raw.githubusercontent.com/zloi-user/hideip.me/refs/heads/master/https.txt",
        "type": "http",
        "cleanup": True
    },
    "14": {
        "name": "hideip.me SOCKS4",
        "url": "https://raw.githubusercontent.com/zloi-user/hideip.me/refs/heads/master/socks4.txt",
        "type": "socks4",
        "cleanup": True
    },
    "15": {
        "name": "hideip.me SOCKS5",
        "url": "https://raw.githubusercontent.com/zloi-user/hideip.me/refs/heads/master/socks5.txt",
        "type": "socks5",
        "cleanup": True
    },
    "16": {
        "name": "r00tee HTTPS",
        "url": "https://raw.githubusercontent.com/r00tee/Proxy-List/main/Https.txt",
        "type": "http",
        "cleanup": False
    },
    "17": {
        "name": "r00tee SOCKS4",
        "url": "https://raw.githubusercontent.com/r00tee/Proxy-List/main/Socks4.txt",
        "type": "socks4",
        "cleanup": False
    },
    "18": {
        "name": "r00tee SOCKS5",
        "url": "https://raw.githubusercontent.com/r00tee/Proxy-List/main/Socks5.txt",
        "type": "socks5",
        "cleanup": False
    }
}
# https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/refs/heads/master/http.txt -> 质量很差,暂时不添加
# https://github.com/FifzzSENZE/Master-Proxy.git -> 质量一般,暂时不添加
# https://github.com/dpangestuw/Free-Proxy.git -> 质量一般,暂时不添加
# https://github.com/watchttvv/free-proxy-list.git -> 可以,但比较少
# https://github.com/trio666/proxy-checker.git