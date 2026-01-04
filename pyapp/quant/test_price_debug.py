
import easyquotation

def test_sina():
    print("Testing easyquotation with sina...")
    quotation = easyquotation.use('sina')
    
    # Test with 6 digit code
    code = '000001' # Ping An Bank
    print(f"Fetching {code}...")
    try:
        data = quotation.real(code)
        print(f"Result for {code}: {data}")
    except Exception as e:
        print(f"Error fetching {code}: {e}")

    # Test with prefix
    code_sz = 'sz000001'
    print(f"Fetching {code_sz}...")
    try:
        data = quotation.real(code_sz)
        print(f"Result for {code_sz}: {data}")
    except Exception as e:
        print(f"Error fetching {code_sz}: {e}")

if __name__ == "__main__":
    test_sina()
