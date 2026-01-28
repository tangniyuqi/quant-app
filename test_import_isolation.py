
import sys
import platform

# 模拟 Windows 环境逻辑（虽然我们不能改变真实的 OS，但我们可以检查导入副作用）
# 我们主要想确认 import pyapp.proxy_server 是否会导入 easytrader

print(f"Initial sys.modules keys count: {len(sys.modules)}")
if 'easytrader' in sys.modules:
    print("WARNING: easytrader is already in sys.modules!")
else:
    print("easytrader is NOT in sys.modules")

try:
    from pyapp import proxy_server
    print("Successfully imported pyapp.proxy_server")
except ImportError as e:
    print(f"ImportError: {e}")
    # 可能是因为缺少某些依赖，比如 pywebview，这在非 GUI 环境下可能报错，但我们主要关注 easytrader
    pass

if 'easytrader' in sys.modules:
    print("FAIL: easytrader was imported by proxy_server!")
    # 打印导入链太难了，但我们可以推断
else:
    print("SUCCESS: easytrader was NOT imported by proxy_server")

if 'pandas' in sys.modules:
    print("INFO: pandas is in sys.modules (this might be okay if other libs use it, but ideally no)")
else:
    print("INFO: pandas is NOT in sys.modules")
