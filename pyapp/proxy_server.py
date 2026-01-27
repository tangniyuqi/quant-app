import os
import threading
import platform
from fastapi import FastAPI, HTTPException, Header, Depends, Query
from pyapp.server import OrderRequest

class MockTrader:
    """Mock Trader for macOS/Linux development"""
    def __init__(self):
        self.balance = [
            {'asset_balance': 100000.0, 'current_balance': 50000.0, 'market_value': 50000.0}
        ]
        self.position = [
            {'stock_code': '000001', 'stock_name': '平安银行', 'market_value': 10000.0, 'current_amount': 1000, 'enable_amount': 1000}
        ]

    def buy(self, security, price, amount):
        return {'message': f'Mock buy {security} price={price} amount={amount}'}

    def sell(self, security, price, amount):
        return {'message': f'Mock sell {security} price={price} amount={amount}'}

def create_proxy_app(client_type: str = 'universal_client', client_path: str = '', token: str = ''):
    """
    创建代理模式的 FastAPI 应用 直接连接指定的交易客户端，不依赖 TaskManager
    :param client_type: 支持的客户端类型 (如 'universal_client', 'ths', 'tdx', 'xq' 等)
    :param client_path: 客户端安装路径
    :param token: 验证 Token
    """
    proxy_app = FastAPI(title="Quant Proxy Server", version="1.0")
    
    # 存储 trader 状态
    # 使用 state 存储，避免全局变量污染
    proxy_app.state.user = None
    proxy_app.state.client_type = client_type
    proxy_app.state.client_path = client_path
    proxy_app.state.token = token
    
    # 全局锁，防止多线程并发操作 GUI
    server_lock = threading.Lock()

    def resolve_client_path(path: str, client_type: str) -> str:
        if not path:
            return path
        if os.path.isdir(path):
            candidates = []
            if client_type in ['ths', 'universal_client']:
                candidates.extend(["xiadan.exe", "hexin.exe", "ths.exe"])
            if client_type in ['tdx', 'universal_client']:
                candidates.extend(["TdxW.exe"])
            
            for name in candidates:
                p = os.path.join(path, name)
                if os.path.exists(p):
                    return p
        return path

    @proxy_app.on_event("startup")
    async def startup_event():
        # 如果是 macOS 或 Linux，使用 Mock 模式，避免 Xlib 依赖错误
        if platform.system() in ['Darwin', 'Linux']:
            print(f"Detected {platform.system()}, using MockTrader for development.")
            proxy_app.state.user = MockTrader()
            return

        try:
            import easytrader
            from easytrader import grid_strategies
            from . import client_patch

            user = easytrader.use(proxy_app.state.client_type)
            user.grid_strategy = grid_strategies.Copy, proxy_app.state.client_type
            proxy_app.state.client_path = resolve_client_path(proxy_app.state.client_path)
            user.connect(proxy_app.state.client_path)
            user.enable_type_keys_for_editor()
            # user.grid_strategy = grid_strategies.Xls
            # user.grid_strategy_instance.tmp_folder = r'C:\Temp'
            # user.return_response = True # 是否返回成交回报
            # user.prepare("同花顺安装路径", username="账户", password="密码") # 若需自动登录

            proxy_app.state.user = user
            print(f"Successfully connected to client: {proxy_app.state.client_path}")
        except Exception as e:
            print(f"Failed to connect to client: {e}")
            # 不抛出异常，允许服务启动，但在调用接口时报错

    def get_user():
        if not proxy_app.state.user:
            raise HTTPException(status_code=500, detail="Trader not connected or initialization failed")
        return proxy_app.state.user

    async def verify_token(x_token: str = Header(None), token: str = Query(None)):
        """
        验证请求头中的 X-Token 或 URL 参数中的 token
        """
        if not proxy_app.state.token:
            return
        
        input_token = x_token or token
        
        if input_token != proxy_app.state.token:
            raise HTTPException(status_code=401, detail="Invalid Token")

    @proxy_app.get("/balance", dependencies=[Depends(verify_token)])
    def get_balance():
        """获取账户资金"""
        with server_lock:
            user = get_user()
            try:
                return {"code": 200, "data": user.balance, "msg": "success"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

    @proxy_app.get("/position", dependencies=[Depends(verify_token)])
    def get_position():
        """获取账户持仓"""
        with server_lock:
            user = get_trader()
            try:
                return {"code": 200, "data": user.position, "msg": "success"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

    @proxy_app.post("/buy", dependencies=[Depends(verify_token)])
    def buy(order: OrderRequest):
        """买入下单"""
        with server_lock:
            user = get_trader()
            try:
                data = user.buy(
                    security=order.security,
                    price=order.price,
                    amount=order.amount
                )
                return {"code": 200, "data": data, "msg": "success"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

    @proxy_app.post("/sell", dependencies=[Depends(verify_token)])
    def sell(order: OrderRequest):
        """卖出下单"""
        with server_lock:
            user = get_trader()
            try:
                data = user.sell(
                    security=order.security,
                    price=order.price,
                    amount=order.amount
                )
                return {"code": 200, "data": data, "msg": "success"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

    return proxy_app
