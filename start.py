#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动安装依赖并启动服务器"""

import subprocess
import sys
import os

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    req_file = os.path.join(script_dir, "requirements.txt")

    # 自动安装依赖
    print("检查并安装依赖...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", req_file],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("依赖安装完成")
    except subprocess.CalledProcessError:
        print("依赖安装失败，尝试直接安装...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "flask", "requests"])
            print("依赖安装完成")
        except subprocess.CalledProcessError as e:
            print(f"依赖安装失败: {e}")
            print("请手动运行: pip install -r requirements.txt")
            sys.exit(1)

    # 启动服务器
    server_file = os.path.join(script_dir, "server.py")
    os.execv(sys.executable, [sys.executable, server_file])


if __name__ == "__main__":
    main()
