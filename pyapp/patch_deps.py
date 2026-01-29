# -*- coding: utf-8 -*-
"""
此脚本用于在 CI/CD 流程中自动替换第三方库的源代码文件。
使用方法：
在 replacements 字典中添加映射关系：
{
    '项目中的源文件路径': '第三方库中的目标文件路径'
}
"""
import os
import shutil
import sys

def patch_easytrader():
    try:
        import easytrader
        package_path = os.path.dirname(easytrader.__file__)
        print(f"Found easytrader at: {package_path}")
    except ImportError:
        print("Error: easytrader not found in the current environment.")
        return

    # 获取项目根目录 (假设此脚本在 pyapp/ 目录下)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(f"Project root: {project_root}")

    # 定义替换规则
    # key: 项目中的源文件 (相对于项目根目录)
    # value: 目标文件 (相对于包根目录)
    replacements = {
        'pyapp/patch/easytrader/clienttrader.py': 'clienttrader.py', 
        'pyapp/patch/easytrader/config/client.py': 'config/client.py', 
    }

    if not replacements:
        print("No replacements configured in pyapp/patch_deps.py.")
        return

    for src_rel, dst_rel in replacements.items():
        src_path = os.path.join(project_root, src_rel)
        dst_path = os.path.join(package_path, dst_rel)

        if not os.path.exists(src_path):
            print(f"Warning: Source file not found: {src_path}")
            continue

        try:
            print(f"Replacing {dst_path} with {src_path} ...")
            shutil.copy2(src_path, dst_path)
            print("Success.")
        except Exception as e:
            print(f"Failed to replace {dst_rel}: {e}")

if __name__ == "__main__":
    print("Starting dependency patching...")
    patch_easytrader()
    print("Dependency patching completed.")
