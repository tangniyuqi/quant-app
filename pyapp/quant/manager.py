# -*- coding: utf-8 -*-
from .strategies.grid import GridStrategy
from .strategies.event import EventStrategy
from .trader import QuantTrader

class TaskManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TaskManager, cls).__new__(cls)
            cls._instance.tasks = {}
        return cls._instance

    def start_task(self, data, log_callback=None):
        task_id = data.get('id')
        strategy_id = data.get('strategy_id')

        if task_id in self.tasks:
            return False, f"当前交易任务({task_id})已经运行中"
        
        if strategy_id == 10001: # 网格策略
            if log_callback:
                log_callback('INFO', 'TaskManager', f"交易任务 {task_id}，正在启动中...")
            strategy = GridStrategy(data, log_callback)
        elif strategy_id == 10006: # 事件驱动AI策略
            if log_callback:
                log_callback('INFO', 'TaskManager', f"交易任务 {task_id}，正在启动事件驱动(AI)策略...")
            strategy = EventStrategy(data, log_callback)
        else:
            if log_callback:
                log_callback('ERROR', 'TaskManager', f"交易任务 {task_id} 启动失败，暂不支持的策略类型")
            return False, f"不支持的策略ID: {strategy_id}" 

        strategy.start()
        
        self.tasks[task_id] = strategy
        return True, f"当前交易任务({task_id})已启动"

    def stop_task(self, task_id):
        if task_id in self.tasks:
            self.tasks[task_id].stop()
            del self.tasks[task_id]
            return True, f"当前交易任务({task_id})已停止"
        return False, f"当前交易任务({task_id})未运行"

    def get_running_tasks(self):
        return list(self.tasks.keys())

    def refresh_account(self, data):
        return QuantTrader.refresh_account(data)
