
import requests
import time
import os

from core.config import ConfigManager
from data.settings import PROXY_POOL_USAGE_TEMPLATE
from schedulers.api_server import api_main

class UseAPI:
    def __init__(self,config: ConfigManager):
        self.config = config

    # 启动API服务器
    def start_api_server(self, current_host, current_port):
        """启动API服务器"""

        print("[info] 启动代理池API服务器...")
        print(f"[info] 服务将在 http://{current_host}:{current_port} 运行")
        print("[info] 按 Ctrl+C 停止服务")

        try:
            # 运行API服务器
            api_main()
        except KeyboardInterrupt:
            print("\n[info] API服务已停止")
        except Exception as e:
            print(f"[error] 启动API服务失败: {e}")

    # 测试API连接
    def test_api_connection(self, current_host, current_port):
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
    def get_proxy_via_api(self, current_host, current_port):
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
                info = proxy_data["proxy_info"]["info"]
                print(f"类型: {info.get('types', [])}")
                print(f"支持国内: {info.get('support', {}).get('china', False)}")
                print(f"支持国际: {info.get('support', {}).get('international', False)}")

                # 是否释放代理
                release = input("[input] 是否立即释放代理? (y/n): ").lower()
                if release == "y":
                    release_data = {
                        "proxy": proxy_data["proxy"],
                        "task_id": proxy_data["task_id"],
                        "success": True
                    }
                    resp = requests.post(f"http://{current_host}:{current_port}/proxy/release", json=release_data,
                                         timeout=5)
                    if resp.status_code == 200:
                        print(f"[success] 代理已释放,返回{resp}")
                    else:
                        print("[error] 释放失败")
            else:
                print(f"[failed] 获取代理失败: {resp.status_code} - {resp.text}")

        except Exception as e:
            print(f"[error] API调用失败: {e}")

    # 获取API统计
    def get_api_stats(self, current_host, current_port):
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
    def reload_proxy_api(self, current_host, current_port):
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
    def api_usage_template(self):
        """生成API爬虫调用模板代码"""
        template = PROXY_POOL_USAGE_TEMPLATE

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

            if create_choice == "y" or create_choice == "yes":
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

            if not (overwrite_choice == "y" or overwrite_choice == "yes"):
                print("[info] 操作已取消")
                return

        try:
            # 写入模板文件
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(template)

            print(f"[success] API调用模板已生成到: {file_path}")
            print(f"[info] 文件大小: {len(template)} 字节")

            # 显示文件绝对路径
            abs_path = os.path.abspath(file_path)
            print(f"[info] 绝对路径: {abs_path}")

        except Exception as e:
            print(f"[error] 写入文件失败: {e}")
