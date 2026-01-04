
import requests

def get_price_sina(code):
    # Add prefix
    if code.startswith('6'):
        code_full = f"sh{code}"
    elif code.startswith('0') or code.startswith('3'):
        code_full = f"sz{code}"
    elif code.startswith('8') or code.startswith('4'):
        code_full = f"bj{code}"
    else:
        code_full = code

    url = f"http://hq.sinajs.cn/list={code_full}"
    try:
        resp = requests.get(url, timeout=3)
        print(f"URL: {url}")
        print(f"Resp: {resp.text}")
        if "var hq_str_" in resp.text:
            content = resp.text.split('"')[1]
            parts = content.split(',')
            if len(parts) > 3:
                return float(parts[3])
    except Exception as e:
        print(f"Error: {e}")
    return 0.0

if __name__ == "__main__":
    print(f"600000: {get_price_sina('600000')}")
    print(f"000001: {get_price_sina('000001')}")
