
 # 设置 Node.js 路径（用于打包后的环境）
            if not os.environ.get('NODE_PATH'):
                node_path = shutil.which('node')
                if not node_path:
                    system = platform.system()
                    
                    if system == 'Windows':
                        common_paths = [
                            r'C:\Program Files\nodejs\node.exe',
                            r'C:\Program Files (x86)\nodejs\node.exe',
                            os.path.join(os.environ.get('ProgramFiles', 'C:\Program Files'), r'nodejs\node.exe'),
                            os.path.join(os.environ.get('APPDATA', ''), r'npm\node.exe'),
                            os.path.join(os.environ.get('LOCALAPPDATA', ''), r'bin\node.exe'),
                        ]
                    else:  # macOS/Linux
                        common_paths = [
                            '/opt/homebrew/bin/node',
                            '/usr/local/bin/node',
                            '/usr/bin/node',
                            '/bin/node',
                            os.path.expanduser('~/.nvm/versions/node/*/bin/node'),
                            os.path.expanduser('~/.local/share/pnpm/node'),
                            os.path.expanduser('~/.volta/bin/node'),
                        ]
                    
                    for path in common_paths:
                        if os.path.isfile(path):
                            node_path = path
                            break
                
                if node_path and os.path.isfile(node_path):
                    try:
                        version = subprocess.check_output([node_path, '-v'], stderr=subprocess.STDOUT).decode()
                        os.environ['NODE_PATH'] = node_path
                    except Exception as e:
                        return {'code': 500, 'msg': f'检测到Node.js，但无法正常运行: {str(e)}'}
                else:
                    return {'code': 500, 'msg': '未检测到Node.js，安装最新稳定版后重试'}