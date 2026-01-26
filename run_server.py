import sys
import os

# Add current directory to path so we can import pyapp
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    try:
        from pyapp.server import run_server
        print("Starting Quant App Server on port 8888...")
        run_server()
    except ImportError as e:
        print(f"Error importing server: {e}")
        print("Please ensure you have installed requirements: pip install -r pyapp/requirements.txt")
