from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from pyapp.quant.manager import TaskManager

app = FastAPI(title="Quant App Server", version="1.0")

class TaskRequest(BaseModel):
    id: str
    strategy_id: int
    task: Dict[str, Any]
    account: Optional[Dict[str, Any]] = None
    backend_url: Optional[str] = None
    token: Optional[str] = None

class OrderRequest(BaseModel):
    security: str
    price: float
    amount: int

@app.get("/tasks")
def get_tasks():
    """获取所有运行中的任务ID"""
    manager = TaskManager()
    return {"code": 200, "data": manager.get_running_tasks(), "msg": "success"}

@app.post("/task/start")
def start_task(task: TaskRequest):
    """启动任务"""
    manager = TaskManager()
    data = task.dict()
    
    # 简单的日志回调，输出到控制台
    def log_callback(level, module, message):
        print(f"[{level}] {module}: {message}")

    success, msg = manager.start_task(data, log_callback)
    if success:
        return {"code": 200, "msg": msg}
    else:
        raise HTTPException(status_code=400, detail=msg)

@app.post("/task/stop")
def stop_task(task_id: str = Body(..., embed=True)):
    """停止任务"""
    manager = TaskManager()
    success, msg = manager.stop_task(task_id)
    if success:
        return {"code": 200, "msg": msg}
    else:
        raise HTTPException(status_code=400, detail=msg)

@app.get("/task/{task_id}/balance")
def get_task_balance(task_id: str):
    """获取指定任务的账户资金"""
    manager = TaskManager()
    if task_id not in manager.tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    strategy = manager.tasks[task_id]
    if hasattr(strategy, 'trader'):
         return {"code": 200, "data": strategy.trader.get_balance(), "msg": "success"}
    return {"code": 400, "msg": "Strategy has no trader"}

@app.get("/task/{task_id}/position")
def get_task_position(task_id: str):
    """获取指定任务的账户持仓"""
    manager = TaskManager()
    if task_id not in manager.tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    strategy = manager.tasks[task_id]
    if hasattr(strategy, 'trader') and strategy.trader.user:
         try:
             # easytrader的原生持仓接口
             pos = strategy.trader.user.position
             return {"code": 200, "data": pos, "msg": "success"}
         except Exception as e:
             raise HTTPException(status_code=500, detail=str(e))
    return {"code": 400, "msg": "Strategy has no trader or not connected"}

@app.post("/task/{task_id}/buy")
def buy(task_id: str, order: OrderRequest):
    """买入下单接口"""
    manager = TaskManager()
    if task_id not in manager.tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    strategy = manager.tasks[task_id]
    if hasattr(strategy, 'trader') and strategy.trader.user:
        try:
            data = strategy.trader.user.buy(
                security=order.security,
                price=order.price,
                amount=order.amount
            )
            return {"code": 200, "data": data, "msg": "下单请求已提交"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"下单失败：{str(e)}")
    return {"code": 400, "msg": "Strategy has no trader or not connected"}

@app.post("/task/{task_id}/sell")
def sell(task_id: str, order: OrderRequest):
    """卖出下单接口"""
    manager = TaskManager()
    if task_id not in manager.tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    strategy = manager.tasks[task_id]
    if hasattr(strategy, 'trader') and strategy.trader.user:
        try:
            data = strategy.trader.user.sell(
                security=order.security,
                price=order.price,
                amount=order.amount
            )
            return {"code": 200, "data": data, "msg": "下单请求已提交"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"下单失败：{str(e)}")
    return {"code": 400, "msg": "Strategy has no trader or not connected"}

if __name__ == "__main__":
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser(description="Quant App Server")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8888, help="Port to bind")
    args = parser.parse_args()
    
    uvicorn.run(app, host=args.host, port=args.port)
