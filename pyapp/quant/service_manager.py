import os
import psutil
import threading
import uvicorn
from pyapp.server import app as task_app
from pyapp.proxy_server import create_proxy_app

class ServiceManager:
    """
    服务进程管理器
    负责管理内部 FastAPI 服务实例和外部进程服务
    """
    
    _internal_servers = {}
    
    @classmethod
    def start_service(cls, client_path, ip='0.0.0.0', port=8888):
        """
        启动服务
        :param client_path: 客户端路径 (仅支持外部客户端路径，如同花顺exe路径)
        :param ip: 绑定IP
        :param port: 绑定端口
        :return: (code, msg, data)
        """
        try:
            if not client_path:
                return 400, '客户端路径不能为空', None

            if port in cls._internal_servers:
                if cls._internal_servers[port].started:
                    return 200, '服务已在运行 (Internal)', {'running': True}
                else:
                    del cls._internal_servers[port]
           
            app = create_proxy_app(client_path)
            log_prefix = f'Proxy Server ({client_path})'

            config = uvicorn.Config(app, host=ip, port=port, log_level="info")
            server = uvicorn.Server(config)
            cls._internal_servers[port] = server
            
            def run_server():
                print(f"[{log_prefix}] Starting on {ip}:{port}...")
                server.run()
            
            t = threading.Thread(target=run_server, daemon=True)
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
                server_instance = cls._internal_servers[port]
                server_instance.should_exit = True
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
                server_instance = cls._internal_servers[port]
                if server_instance.started:
                    return 200, 'success', {'running': True}
                else:
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
