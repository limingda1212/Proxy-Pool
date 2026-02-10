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

from core.config import ConfigManager
from utils.signal_manager import signal_manager
from core.menu import MainMenu


def show_gpl_notice():
    """显示GPL要求的版权声明"""
    print("""
    ProxyPool - 高效代理池管理工具
    Copyright (C) 2026  李明达

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

def main():
    """主函数"""
    show_gpl_notice()
    print("代理池管理系统启动...")

    # 注册信号处理器（必须在任何线程启动前调用）
    signal_manager.register() 

    # 初始化配置
    config = ConfigManager()


    # 启动主菜单
    try:
        menu = MainMenu(config)
        menu.run()
    except KeyboardInterrupt:
        # 这里也会被信号处理器捕获，但作为备份
        print("\n通过KeyboardInterrupt退出")
    finally:
        print("程序结束")


if __name__ == '__main__':
    main()