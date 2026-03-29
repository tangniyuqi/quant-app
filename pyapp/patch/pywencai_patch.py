#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pywencai 打包环境补丁
修复打包后无法找到 Node.js 和 JS 文件的问题
"""

import os
import sys
import subprocess
import shutil


def get_node_path():
    """获取 Node.js 路径"""
    # 优先使用环境变量
    if os.environ.get('NODE_PATH'):
        return os.environ.get('NODE_PATH')
    
    # 使用 which 查找
    node_path = shutil.which('node')
    if node_path and os.path.isfile(node_path):
        return node_path
    
    # 尝试常见路径
    import platform
    system = platform.system()
    
    if system == 'Windows':
        common_paths = [
            r'C:\Program Files\nodejs\node.exe',
            r'C:\Program Files (x86)\nodejs\node.exe',
            os.path.join(os.environ.get('ProgramFiles', 'C:\Program Files'), r'nodejs\node.exe'),
            os.path.join(os.environ.get('APPDATA', ''), r'npm\node.exe'),
            os.path.join(os.environ.get('LOCALAPPDATA', ''), r'bin\node.exe'),
        ]
    else:  # macOS/Linux
        common_paths = [
            '/opt/homebrew/bin/node',
            '/usr/local/bin/node',
            '/usr/bin/node',
            '/bin/node',
            os.path.expanduser('~/.nvm/versions/node/*/bin/node'),
            os.path.expanduser('~/.local/share/pnpm/node'),
            os.path.expanduser('~/.volta/bin/node'),
        ]
    
    for path in common_paths:
        if os.path.isfile(path):
            return path
    
    return None


def get_js_file_path():
    """获取 hexin-v.bundle.js 文件路径"""
    import pywencai
    
    # 尝试原始路径
    pywencai_dir = os.path.dirname(pywencai.__file__)
    js_file = os.path.join(pywencai_dir, 'hexin-v.bundle.js')
    
    if os.path.exists(js_file):
        return js_file
    
    # 如果是打包环境，尝试 _MEIPASS
    if hasattr(sys, '_MEIPASS'):
        js_file = os.path.join(sys._MEIPASS, 'pywencai', 'hexin-v.bundle.js')
        if os.path.exists(js_file):
            return js_file
    
    return None


def patched_get_token():
    """修补后的 get_token 函数"""
    node_path = get_node_path()
    if not node_path:
        raise RuntimeError('未找到 Node.js，请确保已安装 Node.js')
    
    js_file = get_js_file_path()
    if not js_file:
        raise RuntimeError('未找到 hexin-v.bundle.js 文件')
    
    try:
        result = subprocess.run(
            [node_path, js_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10
        )
        
        if result.returncode != 0:
            error_msg = result.stderr.decode().strip()
            raise RuntimeError(f'Node.js 执行失败: {error_msg}')
        
        return result.stdout.decode().strip()
    except subprocess.TimeoutExpired:
        raise RuntimeError('Node.js 执行超时')
    except Exception as e:
        raise RuntimeError(f'执行 Node.js 时出错: {str(e)}')


def apply_patch():
    """应用补丁到 pywencai"""
    try:
        import pywencai.headers as headers_module
        
        # 替换 get_token 函数
        headers_module.get_token = patched_get_token
        
        return True
    except ImportError:
        return False
