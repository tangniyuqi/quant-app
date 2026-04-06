#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试问财修复
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_diagnose():
    """测试诊断功能"""
    print("=" * 60)
    print("测试诊断功能")
    print("=" * 60)
    
    try:
        from pyapp.patch.pywencai_patch import diagnose
        result = diagnose()
        
        print("\n诊断结果：")
        print(f"  是否打包环境: {result['is_packaged']}")
        print(f"  _MEIPASS 路径: {result['meipass']}")
        print(f"\n  Node.js 路径: {result['node_path']}")
        print(f"  Node.js 存在: {result['node_exists']}")
        print(f"  Node.js 版本: {result['node_version']}")
        print(f"\n  JS 文件路径: {result['js_file_path']}")
        print(f"  JS 文件存在: {result['js_file_exists']}")
        
        if result['node_exists'] and result['js_file_exists']:
            print("\n✅ 环境配置正常，可以使用问财功能")
        else:
            print("\n❌ 环境配置异常：")
            if not result['node_exists']:
                print("  - Node.js 未找到或不可用")
            if not result['js_file_exists']:
                print("  - hexin-v.bundle.js 文件未找到")
        
        return result
    except Exception as e:
        print(f"\n❌ 诊断失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_api():
    """测试 API 接口"""
    print("\n" + "=" * 60)
    print("测试 API 接口")
    print("=" * 60)
    
    try:
        from api.quant import QuantAPI
        api = QuantAPI()
        
        # 测试诊断接口
        print("\n调用 quant_diagnoseWencai()...")
        result = api.quant_diagnoseWencai()
        print(f"返回: {result}")
        
        # 测试查询接口（使用简单查询）
        print("\n调用 quant_queryWencai()...")
        params = {
            'query': '市值大于100亿',
            'pro': False
        }
        result = api.quant_queryWencai(params)
        
        if result['code'] == 0:
            print(f"✅ 查询成功，返回 {len(result.get('data', []))} 条数据")
        else:
            print(f"❌ 查询失败: {result['msg']}")
        
        return result
    except Exception as e:
        print(f"\n❌ API 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    print("\n问财功能修复测试")
    print("=" * 60)
    
    # 测试诊断
    diagnose_result = test_diagnose()
    
    # 如果环境正常，测试 API
    if diagnose_result and diagnose_result.get('node_exists') and diagnose_result.get('js_file_exists'):
        test_api()
    else:
        print("\n⚠️  环境配置异常，跳过 API 测试")
        print("\n解决方案：")
        print("1. 安装 Node.js: https://nodejs.org/")
        print("2. 确保 Node.js 在系统 PATH 中")
        print("3. 重新运行测试")


if __name__ == '__main__':
    main()
