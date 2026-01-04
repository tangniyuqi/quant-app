
import urllib.request

def get_price_sina_urllib(code):
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
    req = urllib.request.Request(url)
    req.add_header('Referer', 'http://finance.sina.com.cn/')
    
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            data = response.read().decode('gbk') # Sina uses GBK
            print(f"URL: {url}")
            print(f"Resp: {data}")
            if "var hq_str_" in data:
                content = data.split('"')[1]
                parts = content.split(',')
                if len(parts) > 3:
                    return float(parts[3])
    except Exception as e:
        print(f"Error: {e}")
    return 0.0

if __name__ == "__main__":
    print(f"600000: {get_price_sina_urllib('600000')}")
