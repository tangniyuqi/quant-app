#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 pywencai 在打包环境下的问题
"""

import os
import sys
import subprocess
import shutil

print("=" * 60)
print("pywencai 调试信息")
print("=" * 60)

# 1. 检查 Python 环境
print(f"\n1. Python 版本: {sys.version}")
print(f"   Python 路径: {sys.executable}")
print(f"   是否打包环境: {hasattr(sys, '_MEIPASS')}")
if hasattr(sys, '_MEIPASS'):
    print(f"   _MEIPASS 路径: {sys._MEIPASS}")

# 2. 检查 pywencai 模块
try:
    import pywencai
    print(f"\n2. pywencai 模块:")
    print(f"   安装路径: {pywencai.__file__}")
    pywencai_dir = os.path.dirname(pywencai.__file__)
    print(f"   目录: {pywencai_dir}")
    
    # 列出目录内容
    if os.path.exists(pywencai_dir):
        files = os.listdir(pywencai_dir)
        print(f"   目录内容: {files}")
        
        # 检查关键文件
        js_file = os.path.join(pywencai_dir, 'hexin-v.bundle.js')
        print(f"\n   hexin-v.bundle.js 存在: {os.path.exists(js_file)}")
        if os.path.exists(js_file):
            print(f"   文件大小: {os.path.getsize(js_file)} bytes")
    
    # 如果是打包环境，检查 _MEIPASS 下的文件
    if hasattr(sys, '_MEIPASS'):
        meipass_pywencai = os.path.join(sys._MEIPASS, 'pywencai')
        print(f"\n   _MEIPASS/pywencai 存在: {os.path.exists(meipass_pywencai)}")
        if os.path.exists(meipass_pywencai):
            files = os.listdir(meipass_pywencai)
            print(f"   _MEIPASS/pywencai 内容: {files}")
            
            js_file_meipass = os.path.join(meipass_pywencai, 'hexin-v.bundle.js')
            print(f"   _MEIPASS hexin-v.bundle.js 存在: {os.path.exists(js_file_meipass)}")
            if os.path.exists(js_file_meipass):
                print(f"   文件大小: {os.path.getsize(js_file_meipass)} bytes")
                
except ImportError as e:
    print(f"\n2. pywencai 模块: 未安装 - {e}")

# 3. 检查 Node.js
print(f"\n3. Node.js 环境:")
node_path = shutil.which('node')
print(f"   which node: {node_path}")

if node_path:
    try:
        version = subprocess.check_output([node_path, '-v'], stderr=subprocess.STDOUT).decode().strip()
        print(f"   Node.js 版本: {version}")
    except Exception as e:
        print(f"   Node.js 执行失败: {e}")
else:
    # 尝试常见路径
    common_paths = [
        '/opt/homebrew/bin/node',
        '/usr/local/bin/node',
        '/usr/bin/node',
    ]
    print(f"   尝试常见路径:")
    for path in common_paths:
        exists = os.path.isfile(path)
        print(f"     {path}: {exists}")
        if exists:
            try:
                version = subprocess.check_output([path, '-v'], stderr=subprocess.STDOUT).decode().strip()
                print(f"       版本: {version}")
            except Exception as e:
                print(f"       执行失败: {e}")

# 4. 测试 pywencai.get()
print(f"\n4. 测试 pywencai 查询:")
try:
    import pywencai
    
    # 设置 NODE_PATH
    if not os.environ.get('NODE_PATH'):
        node_path = shutil.which('node')
        if not node_path:
            for path in ['/opt/homebrew/bin/node', '/usr/local/bin/node', '/usr/bin/node']:
                if os.path.isfile(path):
                    node_path = path
                    break
        if node_path:
            os.environ['NODE_PATH'] = node_path
            print(f"   设置 NODE_PATH: {node_path}")
    
    print(f"   执行查询: 市值大于100亿")
    result = pywencai.get(query='市值大于100亿', loop=False)
    
    if result is None:
        print(f"   结果: None (查询失败)")
    else:
        print(f"   结果类型: {type(result)}")
        if hasattr(result, 'shape'):
            print(f"   数据形状: {result.shape}")
        print(f"   查询成功!")
        
except Exception as e:
    print(f"   查询失败: {type(e).__name__}: {e}")
    import traceback
    print(f"\n   详细错误:")
    traceback.print_exc()

print("\n" + "=" * 60)
