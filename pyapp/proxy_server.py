import os
import threading
import platform
from fastapi import FastAPI, HTTPException
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

def create_proxy_app(client_path: str):
    """
    创建代理模式的 FastAPI 应用
    直接连接指定的交易客户端，不依赖 TaskManager
    """
    proxy_app = FastAPI(title="Quant Proxy Server", version="1.0")
    
    # 存储 trader 状态
    # 使用 state 存储，避免全局变量污染
    proxy_app.state.user = None
    proxy_app.state.client_path = client_path
    
    # 全局锁，防止多线程并发操作 GUI
    trader_lock = threading.Lock()

    def resolve_client_path(path: str) -> str:
        if not path:
            return path
        if os.path.isdir(path):
            candidates = [
                "xiadan.exe",
                "hexin.exe",
                "Hexin.exe",
                "THS.exe",
                "ths.exe",
            ]
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
            
            # 使用通用客户端连接同花顺
            user = easytrader.use('universal_client')
            # 设置输入策略为 Copy (复制粘贴)，通常比模拟按键更稳定
            user.grid_strategy = grid_strategies.Copy
            
            resolved_path = resolve_client_path(proxy_app.state.client_path)
            proxy_app.state.client_path = resolved_path
            user.connect(resolved_path)
            
            # 启用编辑器的 Type Keys 模式（如果需要）
            if hasattr(user, 'enable_type_keys_for_editor'):
                user.enable_type_keys_for_editor()
                
            proxy_app.state.user = user
            print(f"Successfully connected to client: {proxy_app.state.client_path}")
        except Exception as e:
            print(f"Failed to connect to client: {e}")
            # 不抛出异常，允许服务启动，但在调用接口时报错

    def get_trader():
        if not proxy_app.state.user:
            raise HTTPException(status_code=500, detail="Trader not connected or initialization failed")
        return proxy_app.state.user

    @proxy_app.get("/balance")
    def get_balance():
        """获取账户资金"""
        with trader_lock:
            user = get_trader()
            try:
                return {"code": 200, "data": user.balance, "msg": "success"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

    @proxy_app.get("/position")
    def get_position():
        """获取账户持仓"""
        with trader_lock:
            user = get_trader()
            try:
                return {"code": 200, "data": user.position, "msg": "success"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

    @proxy_app.post("/buy")
    def buy(order: OrderRequest):
        """买入下单"""
        with trader_lock:
            user = get_trader()
            try:
                data = user.buy(
                    security=order.security,
                    price=order.price,
                    amount=order.amount
                )
                return {"code": 200, "data": data, "msg": "下单请求已提交"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"下单失败：{str(e)}")

    @proxy_app.post("/sell")
    def sell(order: OrderRequest):
        """卖出下单"""
        with trader_lock:
            user = get_trader()
            try:
                data = user.sell(
                    security=order.security,
                    price=order.price,
                    amount=order.amount
                )
                return {"code": 200, "data": data, "msg": "下单请求已提交"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"下单失败：{str(e)}")

    return proxy_app
