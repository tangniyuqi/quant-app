#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os

# 获取配置信息
pyappDir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(pyappDir)
from config.config import Config

appName = Config.appName
appVersion = Config.appVersion[1:] if Config.appVersion.startswith('V') else Config.appVersion
appDeveloper = Config.appDeveloper
appBlogs = Config.appBlogs
# 确保 GUID 内部不包含大括号，方便后续统一转义
appISSID = Config.appISSID.strip('{}') 

# 相对路径适配 (适配 GitHub Actions 环境)
relBuildDir = "..\\..\\..\\build"
relLogoPath = "..\\..\\icon\\logo.ico"
relOutputDir = "..\\..\\..\\build_output"

def getIss():
    # 注意：在 Python f-string 中：
    # {{ 渲染为 {
    # {{{{ 渲染为 {{ (Inno Setup 用于表示纯文本 { 的转义符)
    return f'''
[Setup]
; 修复 Inno Setup GUID 识别问题
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
Name: "desktopicon"; Description: "{{{{cm:CreateDesktopIcon}}"; GroupDescription: "{{{{cm:AdditionalIcons}}"; Flags: unchecked

[Files]
Source: "{relBuildDir}\\*"; DestDir: "{{{{app}}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{{{{autoprograms}}\\{appName}"; Filename: "{{{{app}}\\{appName}.exe"
Name: "{{{{autodesktop}}\\{appName}"; Filename: "{{{{app}}\\{appName}.exe"; Tasks: desktopicon

[Run]
Filename: "{{{{app}}\\{appName}.exe"; Description: "{{{{cm:LaunchProgram,{appName}}}"; Flags: nowait postinstall skipifsilent
'''

# 写入文件，使用 utf-8-sig 编码以兼容 Inno Setup 中文显示
issDir = os.path.dirname(__file__)
issPath = os.path.join(issDir, 'InnoSetup.iss')
with open(issPath, 'w+', encoding='utf-8-sig') as f:
    f.write(getIss())

# 使用纯英文打印，彻底解决控制台 UnicodeEncodeError
print(f"Success: ISS config generated at {issPath}")