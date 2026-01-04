#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os

# 基础路径配置
pyappDir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(pyappDir)
from config.config import Config

# 获取配置项
appName = Config.appName
appVersion = Config.appVersion[1:] if Config.appVersion.startswith('V') else Config.appVersion
appDeveloper = Config.appDeveloper
appBlogs = Config.appBlogs
# 确保 GUID 内部不包含大括号
appISSID = Config.appISSID.strip('{}') 

# 使用相对路径，解决 GitHub Actions 路径不一致问题
relBuildDir = "..\\..\\..\\build"
relLogoPath = "..\\..\\icon\\logo.ico"
relOutputDir = "..\\..\\..\\build_output"

def getIss():
    # 注意：f-string 中，{{ 代表字符 {， }} 代表字符 }
    return f'''
; This file is auto-generated for GitHub Actions
[Setup]
; 修复点：GUID 必须使用双左大括号转义
AppId={{{{{{appISSID}}}
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
Filename: "{{app}}\\{appName}.exe"; Description: "{{cm:LaunchProgram,{appName}}}"; Flags: nowait postinstall skipifsilent
'''

# 写入文件，使用 utf-8-sig 编码以兼容 Inno Setup 中文显示
issDir = os.path.dirname(__file__)
issPath = os.path.join(issDir, 'InnoSetup.iss')
with open(issPath, 'w+', encoding='utf-8-sig') as f:
    f.write(getIss())

print(f"Success: ISS config generated at {issPath}")