# -*- coding: utf-8 -*-
import os
import sys
import importlib
import requests
import logging

# 配置日志
logger = logging.getLogger(__name__)

class StrategyLoader:
    def __init__(self, strategies_dir=None):
        if strategies_dir is None:
            # 默认为当前目录下的 strategies 子目录
            self.strategies_dir = os.path.join(os.path.dirname(__file__), 'strategies')
        else:
            self.strategies_dir = strategies_dir

    def save_strategy_code(self, module_name, code_content):
        """
        直接保存策略代码到文件
        :param module_name: 策略模块名 (例如 'grid', 'event')
        :param code_content: 策略代码字符串
        :return: (bool, message)
        """
        if not code_content:
            return False, "未提供代码内容"
            
        try:
            # 确保目录存在
            if not os.path.exists(self.strategies_dir):
                os.makedirs(self.strategies_dir)
                
            file_path = os.path.join(self.strategies_dir, f"{module_name}.py")
            
            # 简单的校验：检查是否包含基本的类定义
            if f"class " not in code_content:
                return False, "代码内容似乎无效（未找到class定义）"

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(code_content)
                
            return True, "更新成功"
        except Exception as e:
            return False, f"保存异常: {str(e)}"

    def update_strategy_file(self, module_name, url):
        """
        从指定 URL 下载并更新策略文件
        :param module_name: 策略模块名 (例如 'grid', 'event')
        :param url: 下载地址
        :return: (bool, message)
        """
        if not url:
            return False, "未提供下载地址"
            
        try:
            # 确保目录存在
            if not os.path.exists(self.strategies_dir):
                os.makedirs(self.strategies_dir)
                
            file_path = os.path.join(self.strategies_dir, f"{module_name}.py")
            
            # 下载文件
            # 设置超时时间，避免卡死
            response = requests.get(url, timeout=15)
            if response.status_code != 200:
                return False, f"下载失败，状态码: {response.status_code}"
            
            # 写入文件
            content = response.text
            # 简单的校验：检查是否包含基本的类定义
            if f"class " not in content:
                return False, "下载的内容似乎不是有效的Python代码"

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
            return True, "更新成功"
        except Exception as e:
            return False, f"更新异常: {str(e)}"

    def load_strategy_class(self, module_name, class_name):
        """
        动态加载策略类
        :param module_name: 模块名 (例如 'grid')
        :param class_name: 类名 (例如 'GridStrategy')
        :return: class or None
        """
        try:
            # 构造完整的包路径
            # 假设 strategies 目录在 pyapp.quant.strategies
            full_module_name = f"pyapp.quant.strategies.{module_name}"
            
            # 检查模块是否已经加载
            if full_module_name in sys.modules:
                try:
                    # 如果已加载，强制重载以应用最新的代码更改
                    importlib.reload(sys.modules[full_module_name])
                except Exception as e:
                    logger.error(f"重载模块 {full_module_name} 失败: {e}")
                    # 如果重载失败，尝试先移除再重新导入
                    del sys.modules[full_module_name]
                    importlib.import_module(full_module_name)
            else:
                # 首次加载
                importlib.import_module(full_module_name)
            
            # 获取模块对象
            module = sys.modules.get(full_module_name)
            if not module:
                logger.error(f"无法找到模块: {full_module_name}")
                return None
                
            # 获取类对象
            strategy_class = getattr(module, class_name, None)
            if not strategy_class:
                logger.error(f"在模块 {full_module_name} 中未找到类 {class_name}")
                return None
                
            return strategy_class
            
        except ImportError as e:
            logger.error(f"导入模块失败 {module_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"加载策略类异常: {e}")
            return None

# 全局单例
loader = StrategyLoader()
