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

import json
import asyncio
import threading
import time
import random
from datetime import datetime
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import sqlite3
from contextlib import asynccontextmanager,contextmanager
import logging
import os

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# === 数据结构定义 ===

class DatabaseManager:
    """数据库管理器"""

    def __init__(self, db_path="proxies.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """初始化数据库（如果不存在）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 确保代理状态表存在
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS proxy_status (
            proxy TEXT PRIMARY KEY,
            status TEXT DEFAULT 'idle',
            task_id TEXT,
            acquire_time REAL,
            heartbeat_time REAL
        )
        ''')

        conn.commit()
        conn.close()

    @contextmanager
    def get_connection(self):
        """获取数据库连接（上下文管理器）"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 返回字典格式
        try:
            yield conn
        finally:
            conn.close()

# 代理状态
class ProxyStatus(BaseModel):
    proxy: str
    status: str  # idle, busy, dead
    task_id: Optional[str] = None
    acquire_time: Optional[float] = None
    heartbeat_time: Optional[float] = None

# 代理信息
class ProxyInfo(BaseModel):
    proxy: str
    score: int
    info: Dict[str, Any]

# 获取请求
class AcquireRequest(BaseModel):
    proxy_type: Optional[str] = "http"  # http, https, socks4, socks5, all
    support_region: Optional[str] = None  # china, international, all
    min_score: int = 0
    exclude_proxies: Optional[List[str]] = None
    task_id: Optional[str] = None

# 释放请求
class ReleaseRequest(BaseModel):
    proxy: str
    task_id: str
    success: bool = True
    response_time: Optional[float] = None

# 健康检查请求
class HealthCheckRequest(BaseModel):
    proxy: str
    task_id: str
# ===      ===

class ProxyPoolManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db_manager = DatabaseManager(db_path)

        self.proxies: Dict[str, Dict] = {}  # 代理信息缓存
        self.status: Dict[str, ProxyStatus] = {}  # 代理状态缓存
        self.lock = threading.RLock()

        # 索引结构
        self.type_index: Dict[str, List[str]] = {}
        self.region_index: Dict[str, List[str]] = {}
        self.score_index: List[tuple] = []  # (score, proxy)

        # 统计数据
        self.stats = {
            "total": 0,
            "idle": 0,
            "busy": 0,
            "dead": 0,
            "last_updated": None
        }

        # 启动时加载数据
        self.load_proxies()

    def load_proxies(self):
        """从数据库加载代理数据"""
        with self.lock:
            try:
                with self.db_manager.get_connection() as conn:
                    cursor = conn.cursor()

                    # 加载代理信息
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
                        proxy = row['proxy']
                        score = row['score']

                        # 构建info字典
                        info = {
                            "types": json.loads(row['types']) if row['types'] else [],
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
                                "check_date": row['security_check_date']
                            },
                            "performance": {
                                "avg_response_time": row['avg_response_time'],
                                "success_rate": row['success_rate'],
                                "last_checked": row['last_checked']
                            }
                        }

                        # 存储代理信息
                        self.proxies[proxy] = {
                            "score": score,
                            "info": info
                        }

                        # 初始化状态（从数据库或默认）
                        cursor.execute(
                            "SELECT status, task_id, acquire_time, heartbeat_time FROM proxy_status WHERE proxy = ?",
                            (proxy,)
                        )
                        status_row = cursor.fetchone()

                        if status_row:
                            self.status[proxy] = ProxyStatus(
                                proxy=proxy,
                                status=status_row['status'],
                                task_id=status_row['task_id'],
                                acquire_time=status_row['acquire_time'],
                                heartbeat_time=status_row['heartbeat_time']
                            )
                        else:
                            self.status[proxy] = ProxyStatus(
                                proxy=proxy,
                                status="idle"
                            )

                        # 构建索引
                        proxy_types = info.get("types", [])
                        for ptype in proxy_types:
                            if ptype not in self.type_index:
                                self.type_index[ptype] = []
                            self.type_index[ptype].append(proxy)

                        # 构建地区索引
                        support = info.get("support", {})
                        if support.get("china"):
                            if "china" not in self.region_index:
                                self.region_index["china"] = []
                            self.region_index["china"].append(proxy)
                        if support.get("international"):
                            if "international" not in self.region_index:
                                self.region_index["international"] = []
                            self.region_index["international"].append(proxy)

                        # 构建分数索引
                        self.score_index.append((score, proxy))

                    # 按分数排序
                    self.score_index.sort(reverse=True)

                    # 更新统计
                    self.stats["total"] = len(self.proxies)
                    self.stats["idle"] = sum(1 for s in self.status.values() if s.status == "idle")
                    self.stats["busy"] = sum(1 for s in self.status.values() if s.status == "busy")
                    self.stats["dead"] = sum(1 for s in self.status.values() if s.status == "dead")
                    self.stats["last_updated"] = datetime.now().isoformat()

                    logger.info(f"成功加载 {len(self.proxies)} 个代理")

            except Exception as e:
                logger.error(f"加载代理数据失败: {e}")

    async def save_proxy_update(self, proxy: str, score_delta: int = 0,response_time: Optional[float] = None):
        """异步保存代理更新到数据库"""
        with self.lock:
            try:
                with self.db_manager.get_connection() as conn:
                    cursor = conn.cursor()

                    # 获取当前代理信息
                    cursor.execute(
                        "SELECT score, types, support_china, support_international, "
                        "transparent, detected_ip, city, region, country, loc, org, "
                        "postal, timezone, browser_valid, browser_check_date, "
                        "browser_response_time, dns_hijacking, ssl_valid, "
                        "malicious_content, security_check_date, avg_response_time, "
                        "success_rate, last_checked FROM proxies WHERE proxy = ?",
                        (proxy,)
                    )
                    row = cursor.fetchone()

                    if not row:
                        logger.warning(f"代理 {proxy} 不存在于数据库中")
                        return

                    # 更新分数
                    current_score = row['score']
                    new_score = max(0, min(100, current_score + score_delta))

                    # 更新成功率
                    current_success = row['success_rate']
                    if score_delta > 0:
                        new_success = min(1.0, round(current_success + 0.1, 2))
                    else:
                        new_success = max(0.0, round(current_success - 0.1, 2))

                    logger.info(f"代理 {proxy} 成功率 {current_success:.2f} -> {new_success:.2f}")

                    # 更新平均响应时间（如果有response_time）
                    current_avg = row['avg_response_time']
                    if response_time is not None:
                        new_avg = (current_avg * 0.7 + response_time * 0.3)
                    else:
                        new_avg = current_avg

                    # 更新数据库
                    cursor.execute('''
                    UPDATE proxies SET
                        score = ?,
                        avg_response_time = ?,
                        success_rate = ?,
                        last_checked = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE proxy = ?
                    ''', (
                        new_score,
                        round(new_avg, 3),
                        new_success,
                        datetime.now().strftime("%Y-%m-%d"),
                        proxy
                    ))

                    conn.commit()

                    # 更新内存缓存
                    if proxy in self.proxies:
                        self.proxies[proxy]["score"] = new_score
                        self.proxies[proxy]["info"]["performance"]["avg_response_time"] = round(new_avg, 3)
                        self.proxies[proxy]["info"]["performance"]["success_rate"] = new_success
                        self.proxies[proxy]["info"]["performance"]["last_checked"] = datetime.now().strftime("%Y-%m-%d")

                    # 更新分数索引
                    self.score_index = [(score, p) for score, p in self.score_index if p != proxy]
                    self.score_index.append((new_score, proxy))
                    self.score_index.sort(reverse=True)

            except Exception as e:
                logger.error(f"保存代理 {proxy} 更新失败: {e}")

    def acquire_proxy(self, request: AcquireRequest) -> Optional[Dict[str, Any]]:
        """获取一个代理"""
        with self.lock:
            # 生成任务ID
            if not request.task_id:
                request.task_id = f"task_{int(time.time())}_{random.randint(1000, 9999)}"

            # 筛选符合条件的代理
            candidates = []

            for proxy in self.proxies:
                status = self.status.get(proxy)
                if not status or status.status != "idle":
                    continue

                # 检查排除列表
                if request.exclude_proxies and proxy in request.exclude_proxies:
                    continue

                # 检查分数
                proxy_data = self.proxies[proxy]
                if proxy_data["score"] < request.min_score:
                    continue

                # 检查类型
                if request.proxy_type != "all":
                    proxy_types = proxy_data["info"].get("types", [])
                    if request.proxy_type not in proxy_types:
                        continue

                # 检查地区
                if request.support_region and request.support_region != "all":
                    support = proxy_data["info"].get("support", {})
                    if not support.get(request.support_region):
                        continue

                candidates.append((proxy_data["score"], proxy))

            if not candidates:
                return None

            # 按分数排序并选择最高分的代理
            candidates.sort(reverse=True)
            selected_proxy = candidates[0][1]

            # 更新状态
            self.status[selected_proxy].status = "busy"
            self.status[selected_proxy].task_id = request.task_id
            self.status[selected_proxy].acquire_time = time.time()
            self.status[selected_proxy].heartbeat_time = time.time()

            # 更新统计
            self.stats["idle"] -= 1
            self.stats["busy"] += 1

            return {
                "proxy": selected_proxy,
                "task_id": request.task_id,
                "proxy_info": self.proxies[selected_proxy]
            }

    def release_proxy(self, proxy: str, task_id: str, success: bool = True):
        """释放代理并更新状态"""
        with self.lock:
            if proxy not in self.status:
                return False

            status = self.status[proxy]

            # 检查任务ID是否匹配
            if status.task_id != task_id:
                logger.warning(f"任务ID不匹配: 预期 {status.task_id}, 实际 {task_id}")
                # 但还是释放，防止代理被永久占用

            # 更新状态
            old_status = status.status
            status.status = "idle" if success else "dead"
            status.task_id = None
            status.acquire_time = None

            # 更新统计
            if old_status == "busy":
                self.stats["busy"] -= 1
                if success:
                    self.stats["idle"] += 1
                else:
                    self.stats["dead"] += 1

            # 保存状态到数据库
            try:
                with self.db_manager.get_connection() as conn:
                    cursor = conn.cursor()
                    if success:
                        cursor.execute('''
                        INSERT OR REPLACE INTO proxy_status (proxy, status, task_id, acquire_time, heartbeat_time)
                        VALUES (?, 'idle', NULL, NULL, NULL)
                        ''', (proxy,))
                    else:
                        cursor.execute('''
                        INSERT OR REPLACE INTO proxy_status (proxy, status, task_id, acquire_time, heartbeat_time)
                        VALUES (?, 'dead', NULL, NULL, NULL)
                        ''', (proxy,))
                    conn.commit()
            except Exception as e:
                logger.error(f"保存代理状态失败: {e}")

            return True

    def heartbeat(self, proxy: str, task_id: str) -> bool:
        """更新心跳"""
        with self.lock:
            if proxy not in self.status:
                return False

            status = self.status[proxy]
            if status.task_id != task_id:
                return False

            status.heartbeat_time = time.time()

            # 保存心跳到数据库
            try:
                with self.db_manager.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                    UPDATE proxy_status SET heartbeat_time = ? WHERE proxy = ?
                    ''', (status.heartbeat_time, proxy))
                    conn.commit()
            except Exception as e:
                logger.error(f"保存心跳失败: {e}")

            return True

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self.lock:
            return {
                **self.stats,
                "timestamp": datetime.now().isoformat(),
                "memory_usage": len(str(self.proxies)) + len(str(self.status))
            }

    def cleanup_dead_proxies(self):
        """清理死亡代理"""
        with self.lock:
            dead_proxies = []
            for proxy, status in self.status.items():
                if status.status == "dead":
                    dead_proxies.append(proxy)

            for proxy in dead_proxies:
                # 从数据库中删除 -> 不从数据库删除了,太浪费了
                # try:
                #     with self.db_manager.get_connection() as conn:
                #         cursor = conn.cursor()
                #         cursor.execute("DELETE FROM proxies WHERE proxy = ?", (proxy,))
                #         cursor.execute("DELETE FROM proxy_status WHERE proxy = ?", (proxy,))
                #         conn.commit()
                # except Exception as e:
                #     logger.error(f"从数据库删除代理 {proxy} 失败: {e}")

                # 从内存缓存中删除
                if proxy in self.proxies:
                    del self.proxies[proxy]
                if proxy in self.status:
                    del self.status[proxy]

                # 从索引中移除
                for index in [self.type_index, self.region_index]:
                    for key in index:
                        if proxy in index[key]:
                            index[key].remove(proxy)

                # 从分数索引中移除
                self.score_index = [(score, p) for score, p in self.score_index if p != proxy]

            self.stats["total"] = len(self.proxies)
            self.stats["dead"] = 0

            logger.info(f"清理了 {len(dead_proxies)} 个死亡代理")
            return len(dead_proxies)

    def cleanup_zero_score_proxies(self):
        """清理数据库中分数为0的代理"""
        with self.lock:
            try:
                with self.db_manager.get_connection() as conn:
                    cursor = conn.cursor()

                    # 查询0分代理数量
                    cursor.execute("SELECT COUNT(*) FROM proxies WHERE score <= 0")
                    zero_score_count = cursor.fetchone()[0]

                    if zero_score_count == 0:
                        logger.info("数据库中没有0分代理")
                        return 0

                    logger.info(f"发现 {zero_score_count} 个0分代理，开始清理...")

                    # 获取要删除的代理列表
                    cursor.execute("SELECT proxy FROM proxies WHERE score <= 0")
                    dead_proxies = [row['proxy'] for row in cursor.fetchall()]

                    # 删除0分代理
                    cursor.execute("DELETE FROM proxies WHERE score <= 0")
                    deleted_count = cursor.rowcount

                    # 删除对应的状态记录
                    cursor.execute(
                        "DELETE FROM proxy_status WHERE score <= 0 OR proxy NOT IN (SELECT proxy FROM proxies)")

                    conn.commit()

                    # 更新内存缓存
                    for proxy in dead_proxies:
                        if proxy in self.proxies:
                            del self.proxies[proxy]
                        if proxy in self.status:
                            del self.status[proxy]

                        # 从索引中移除
                        for index in [self.type_index, self.region_index]:
                            for key in index:
                                if proxy in index[key]:
                                    index[key].remove(proxy)

                        # 从分数索引中移除
                        self.score_index = [(score, p) for score, p in self.score_index if p != proxy]

                    # 更新统计
                    self.stats["total"] = len(self.proxies)

                    logger.info(f"清理了 {deleted_count} 个0分代理")
                    return deleted_count

            except Exception as e:
                logger.error(f"清理0分代理失败: {e}")
                return 0

    def get_proxy_info(self, proxy: str) -> Optional[Dict[str, Any]]:
        """获取代理详细信息"""
        with self.lock:
            if proxy not in self.proxies:
                return None

            proxy_data = self.proxies[proxy]
            status = self.status.get(proxy)

            return {
                "proxy": proxy,
                "score": proxy_data["score"],
                "info": proxy_data["info"],
                "status": status.status if status else "unknown",
                "task_id": status.task_id if status else None,
                "acquire_time": status.acquire_time if status else None,
                "heartbeat_time": status.heartbeat_time if status else None
            }

    def reload_proxies(self):
        """重新加载代理"""
        with self.lock:
            # 清空缓存
            self.proxies.clear()
            self.status.clear()
            self.type_index.clear()
            self.score_index.clear()
            self.region_index["china"].clear()
            self.region_index["international"].clear()

            # 重新加载
            self.load_proxies()
            return True

# 全局代理池实例
proxy_pool: Optional[ProxyPoolManager] = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global proxy_pool

    db_path = os.path.join(BASE_DIR, "proxies.db")

    # 启动时
    proxy_pool = ProxyPoolManager(db_path)

    # 启动后台任务
    background_tasks = asyncio.create_task(run_background_tasks())

    yield

    # 关闭时
    background_tasks.cancel()
    try:
        await background_tasks
    except asyncio.CancelledError:
        pass


# 在 api.py 的 run_background_tasks 函数中修改
async def run_background_tasks():
    """运行后台任务"""
    cleanup_counter = 0

    while True:
        try:
            await asyncio.sleep(300)  # 每5分钟执行一次

            if not proxy_pool:
                continue

            # 每次执行清理超时占用
            timeout_threshold = time.time() - 1800  # 30分钟
            released_count = 0

            with proxy_pool.lock:
                for proxy, status in proxy_pool.status.items():
                    if (status.status == "busy" and
                            status.heartbeat_time and
                            status.heartbeat_time < timeout_threshold):
                        logger.warning(f"代理 {proxy} 超时，自动释放")
                        proxy_pool.release_proxy(proxy, status.task_id or "timeout", success=False)
                        released_count += 1

            if released_count > 0:
                logger.info(f"自动释放了 {released_count} 个超时代理")

            # 每6次（30分钟）清理一次死亡代理
            if cleanup_counter % 6 == 0:
                dead_cleaned = proxy_pool.cleanup_dead_proxies()
                if dead_cleaned > 0:
                    logger.info(f"清理了 {dead_cleaned} 个死亡代理")

            # 每12次（1小时）清理一次0分代理
            if cleanup_counter % 12 == 0:
                zero_cleaned = proxy_pool.cleanup_zero_score_proxies()
                if zero_cleaned > 0:
                    logger.info(f"清理了 {zero_cleaned} 个0分代理")

            # 增加计数器
            cleanup_counter += 1
            # 防止计数器过大
            if cleanup_counter > 10000:
                cleanup_counter = 0

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"后台任务异常: {e}")
            await asyncio.sleep(60)


# 创建FastAPI应用
app = FastAPI(title="代理池API", lifespan=lifespan)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# API路由
@app.get("/", response_class=HTMLResponse)
async def root():
    """从文件加载管理界面"""
    # 定义HTML文件路径
    html_file = "data/web/index.html"
    html_file_path = os.path.join(os.path.dirname(__file__), html_file)

    # 检查文件是否存在
    if not os.path.exists(html_file_path):
        # 返回备用简单界面（防止文件缺失）
        return HTMLResponse(content=f"""
            <html>
                <body>
                    <h1>代理池管理面板</h1>
                    <p>网页文件缺失，请检查 {html_file} 是否存在</p>
                </body>
            </html>
        """, status_code=500)

    # 读取HTML文件内容
    try:
        with open(html_file_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except Exception as e:
        return HTMLResponse(content=f"""
            <html>
                <body>
                    <h1>加载失败</h1>
                    <p>错误信息: {str(e)}</p>
                </body>
            </html>
        """, status_code=500)


@app.post("/proxy/acquire")
async def acquire_proxy(request: AcquireRequest, background_tasks: BackgroundTasks):
    """获取代理"""
    if not proxy_pool:
        raise HTTPException(status_code=503, detail="代理池未初始化")

    result = proxy_pool.acquire_proxy(request)
    if not result:
        raise HTTPException(status_code=404, detail="没有可用的代理")

    return {
        "code": 200,
        "message": "成功获取代理",
        "data": result
    }


@app.post("/proxy/release")
async def release_proxy(request: ReleaseRequest, background_tasks: BackgroundTasks):
    """释放代理"""
    if not proxy_pool:
        raise HTTPException(status_code=503, detail="代理池未初始化")

    # 先更新内存状态
    success = proxy_pool.release_proxy(
        proxy=request.proxy,
        task_id=request.task_id,
        success=request.success
    )

    if not success:
        raise HTTPException(status_code=400, detail="代理释放失败")

    # 异步更新CSV文件
    score_delta = 2 if request.success else -1
    background_tasks.add_task(
        proxy_pool.save_proxy_update,
        request.proxy,
        score_delta,
        request.response_time
    )

    return {
        "code": 200,
        "message": "代理已释放",
        "data": {
            "proxy": request.proxy,
            "success": request.success
        }
    }


@app.post("/proxy/heartbeat")
async def proxy_heartbeat(request: HealthCheckRequest):
    """代理心跳"""
    if not proxy_pool:
        raise HTTPException(status_code=503, detail="代理池未初始化")

    success = proxy_pool.heartbeat(
        proxy=request.proxy,
        task_id=request.task_id
    )

    if not success:
        raise HTTPException(status_code=400, detail="心跳更新失败")

    return {
        "code": 200,
        "message": "心跳已更新",
        "data": {
            "proxy": request.proxy,
            "heartbeat_time": time.time()
        }
    }


@app.get("/proxy/stats")
async def get_proxy_stats():
    """获取代理池统计"""
    if not proxy_pool:
        raise HTTPException(status_code=503, detail="代理池未初始化")

    stats = proxy_pool.get_stats()
    return {
        "code": 200,
        "message": "成功获取统计信息",
        "data": stats
    }


@app.get("/proxy/info_{proxy}")   # 前面的info_是为了防止与其他url混了,例如stats被识别为{proxy}
async def get_proxy_info(proxy: str):
    """获取代理详细信息"""
    if not proxy_pool:
        raise HTTPException(status_code=503, detail="代理池未初始化")

    info = proxy_pool.get_proxy_info(proxy)
    if not info:
        raise HTTPException(status_code=404, detail="代理不存在")

    return {
        "code": 200,
        "message": "成功获取代理信息",
        "data": info
    }


@app.get("/proxy/reload")
async def reload_proxies():
    """重新加载代理池"""
    if not proxy_pool:
        raise HTTPException(status_code=503, detail="代理池未初始化")

    success = proxy_pool.reload_proxies()

    return {
        "code": 200 if success else 500,
        "message": "代理池已重新加载" if success else "重新加载失败",
        "data": {
            "success": success,
            "total": proxy_pool.stats["total"]
        }
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "proxies_loaded": proxy_pool.stats["total"] if proxy_pool else 0
    }

def load_settings():
    """加载端口"""
    try:
        with open("data/config.json", "r", encoding="utf-8") as f:
            config = json.loads(f.read())
        return config.get("api",{"host":"0.0.0.0"}).get("host","0.0.0.0"), config.get("api",{"port":8000}).get("port",8000)
    except:
        return "0.0.0.0", 8000


if __name__ == "__main__":
    """
    Uvicorn 是一个基于 asyncio 开发的轻量级高效 ASGI（Asynchronous Server Gateway Interface）服务器，
    底层依赖 uvloop 和 httptools，能够显著提升 Python 异步 Web 应用的性能。它支持 HTTP/1.1、WebSocket、
    Pub/Sub 广播，并计划支持 HTTP/2，常与 FastAPI、Starlette 等框架搭配使用。
    """
    print("爬虫API接口程序")
    host,port = load_settings()
    print(f"http://{host}:{port}")

    uvicorn.run(
        "api:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )