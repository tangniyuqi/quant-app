import os
import psutil
import threading
import uvicorn
import platform
from pyapp.server import app as task_app
from pyapp.proxy_server import create_proxy_app

class ServiceManager:
    """
    服务进程管理器
    负责管理内部 FastAPI 服务实例和外部进程服务
    """
    
    _internal_servers = {}
    
    @classmethod
    def start_service(cls, client_type='universal_client', client_path='', port=8888, token=''):
        """
        启动服务
        :param client_type: 客户端类型
        :param client_path: 客户端路径 (仅支持外部客户端路径，如同花顺exe路径)
        :param port: 绑定端口
        :param token: 验证 Token
        :return: (code, msg, data)
        """
        try:
            client_path = client_path or ''
            # 在非 Windows 平台允许空路径（用于 Mock）
            if not client_path and platform.system() == 'Windows':
                return 400, '客户端路径不能为空', None

            if port in cls._internal_servers:
                entry = cls._internal_servers[port]
                server_instance = entry["server"]
                thread_instance = entry.get("thread")
                if server_instance.started and (not thread_instance or thread_instance.is_alive()):
                    return 200, '服务已在运行 (Internal)', {'running': True}
                if thread_instance and thread_instance.is_alive():
                    return 200, '服务正在启动 (Internal)', {'running': True, 'starting': True}
                else:
                    del cls._internal_servers[port]
           
            app = create_proxy_app(client_type, client_path, token)
            log_prefix = f'Proxy Server ({client_path or "mock"})'
            ip = '0.0.0.0'
            config = uvicorn.Config(app, host=ip, port=port, log_level="info")
            server = uvicorn.Server(config)
            
            def run_server():
                print(f"[{log_prefix}] Starting on {ip}:{port}...")
                server.run()
            
            t = threading.Thread(target=run_server, daemon=True)
            cls._internal_servers[port] = {"server": server, "thread": t}
            t.start()
            
            return 200, '服务启动成功', {'running': True}

        except Exception as e:
            return 500, f'启动失败: {str(e)}', None

    @classmethod
    def stop_service(cls, client_path, port=8888):
        """
        停止服务
        :param client_path: 客户端路径
        :param port: 端口
        :return: (code, msg)
        """
        try:
            # 1. 尝试停止内部服务
            if port in cls._internal_servers:
                entry = cls._internal_servers[port]
                server_instance = entry["server"]
                thread_instance = entry.get("thread")
                server_instance.should_exit = True
                
                # 尝试等待线程结束，释放端口
                if thread_instance and thread_instance.is_alive():
                    # 给一点时间让 uvicorn 优雅关闭
                    thread_instance.join(timeout=2.0)
                
                # 无论是否成功 join，都从管理列表移除
                # 如果没完全关闭，再次启动时 uvicorn 会报错端口占用
                del cls._internal_servers[port]
                return 200, '服务已停止'
            
            return 200, '服务未运行或已停止'
        except Exception as e:
            return 500, f'停止异常: {str(e)}'

    @classmethod
    def check_service_status(cls, client_path, port=8888):
        """
        检查服务状态
        :param client_path: 客户端路径
        :param port: 端口
        :return: (code, msg, data)
        """
        try:
            # 1. 检查内部服务状态
            if port in cls._internal_servers:
                entry = cls._internal_servers[port]
                server_instance = entry["server"]
                thread_instance = entry.get("thread")
                if server_instance.started and (not thread_instance or thread_instance.is_alive()):
                    return 200, 'success', {'running': True}
                if thread_instance and thread_instance.is_alive():
                    return 200, 'success', {'running': True, 'starting': True}
                del cls._internal_servers[port]

            return 200, 'success', {'running': False}
        except Exception as e:
            return 200, str(e), {'running': False}

    @staticmethod
    def _is_process_running(client_path, port=None):
        """检查外部进程是否运行"""
        target_script = os.path.basename(client_path)
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info['cmdline']
                if not cmdline:
                    continue
                
                if client_path in cmdline[0] or target_script in cmdline[0]:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return False

    @staticmethod
    def _stop_process(client_path, port=None):
        """停止外部进程"""
        target_script = os.path.basename(client_path)
        stopped_any = False

        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info['cmdline']
                if not cmdline:
                    continue
        
                if client_path in cmdline[0] or target_script in cmdline[0]:
                    proc.terminate()
                    stopped_any = True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        return stopped_any
