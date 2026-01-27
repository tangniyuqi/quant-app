#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Author: Tang Ming
Date: 2025-12-12 17:01:39
LastEditTime: 2025-12-18 20:28:48
Description: 业务层API，供前端JS调用
usage: 在Javascript中调用window.pywebview.api.<methodname>(<parameters>)
'''

import json
import os
import sys
from api.system import System
from pyapp.quant.manager import TaskManager
from pyapp.quant.service_manager import ServiceManager

class QuantAPI:
    '''量化交易API'''
    
    def quant_startClient(self, data):
        """
        启动客户端服务
        :param data: JSON string containing server config
        """
        try:
            server = json.loads(data)
            client_type = server.get('clientType', 'universal_client')
            client_path = server.get('clientPath', '')
            port = int(server.get('port', 8888))
            token = server.get('token', '')
            
            code, msg, data = ServiceManager.start_service(client_type, client_path, port, token)
            result = {'code': code, 'msg': msg}
            if data:
                result['data'] = data
            return result
        except Exception as e:
            return {'code': 500, 'msg': f'启动失败: {str(e)}'}

    def quant_stopClient(self, data):
        '''停止客户端程序'''
        try:
            server = json.loads(data)
            client_path = server.get('clientPath')
            port = int(server.get('port', 8888))

            code, msg = ServiceManager.stop_service(client_path, port)
            return {'code': code, 'msg': msg}

        except Exception as e:
            return {'code': 500, 'msg': f'停止异常: {str(e)}'}

    def quant_checkClientStatus(self, data):
        '''检查客户端程序状态'''
        try:
            server = json.loads(data)
            client_path = server.get('clientPath')
            port = int(server.get('port', 8888))

            code, msg, data = ServiceManager.check_service_status(client_path, port)
            return {'code': code, 'msg': msg, 'data': data}

        except Exception as e:
            # If checking status fails, assume not running or error
            return {'code': 200, 'data': {'running': False}, 'msg': str(e)}

    def quant_startTask(self, data):
        '''启动任务'''
        def log_callback(level, module, message):
            if System._window:
                js = f"window.quant_addConsoleLog({json.dumps(level)}, {json.dumps(module)}, {json.dumps(message)})"
                System._window.evaluate_js(js)

        manager = TaskManager()
        success, msg = manager.start_task(data, log_callback)
        return {'success': success, 'msg': msg}

    def quant_stopTask(self, task_id):
        '''停止任务'''
        manager = TaskManager()
        success, msg = manager.stop_task(task_id)
        return {'success': success, 'msg': msg}

    def quant_getRunningTasks(self):
        '''获取运行中的任务ID列表'''
        manager = TaskManager()
        ids = manager.get_running_tasks()   
        return {'success': True, 'data': ids}

    def quant_refreshAccount(self, data):
        '''刷新账户资金'''
        try:
            manager = TaskManager()
            success, msg = manager.refresh_account(data)
            return {'success': success, 'msg': msg}
        except Exception as e:
            return {'success': False, 'msg': str(e)}