#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os

# 路径处理
pyappDir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(pyappDir)
from config.config import Config

# 获取配置信息
appName = Config.appName
appVersion = Config.appVersion[1:] if Config.appVersion.startswith('V') else Config.appVersion
appDeveloper = Config.appDeveloper
appBlogs = Config.appBlogs
# 核心修复：确保 GUID 格式正确 
appISSID = Config.appISSID.strip('{}') 

# 相对路径适配 
relBuildDir = "..\\..\\..\\build"
relLogoPath = "..\\..\\icon\\logo.ico"
relOutputDir = "..\\..\\..\\build_output"

def getIss():
    return f'''
[Setup]
; 核心修复：使用双左花括号转义 
AppId={{{{{appISSID}}}}
AppName={appName}
AppVersion={appVersion}
AppPublisher={appDeveloper}
AppPublisherURL={appBlogs}
DefaultDirName={{autopf}}\\{appName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={relOutputDir}
OutputBaseFilename={appName}-V{appVersion}_Windows
SetupIconFile={relLogoPath}
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"; Flags: unchecked

[Files]
Source: "{relBuildDir}\\*"; DestDir: "{{app}}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{{autoprograms}}\\{appName}"; Filename: "{{app}}\\{appName}.exe"
Name: "{{autodesktop}}\\{appName}"; Filename: "{{app}}\\{appName}.exe"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\{appName}.exe"; Description: "{{cm:LaunchProgram,{appName}}}}"; Flags: nowait postinstall skipifsilent
'''

issDir = os.path.dirname(__file__)
issPath = os.path.join(issDir, 'InnoSetup.iss')

# 核心修复：使用 utf-8-sig 编码写入文件 
with open(issPath, 'w+', encoding='utf-8-sig') as f:
    f.write(getIss())

# 核心修复：使用纯英文打印输出，避免控制台编码错误 
print(f"Success: ISS config generated at {issPath}")