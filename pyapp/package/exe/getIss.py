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
# 核心修复：确保 GUID 内部不包含大括号
appISSID = Config.appISSID.strip('{}') 

# 使用相对路径，解决 GitHub Actions 环境下的盘符不一致问题
relBuildDir = "..\\..\\..\\build"
relLogoPath = "..\\..\\icon\\logo.ico"
relOutputDir = "..\\..\\..\\build_output"

def getIss():
    # 注意：在 Python f-string 中，{{ 渲染为 {， }} 渲染为 }
    # 而 Inno Setup 需要两个 {{ 来表示一个纯文本的 {
    # 因此这里使用了复杂的嵌套转义
    return f'''
[Setup]
; 核心修复：GUID 必须使用双左大括号转义以供 Inno Setup 识别
AppId={{{{{{{appISSID}}}
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
; 核心修复：指向相对路径并包含所有子文件
Source: "{relBuildDir}\\*"; DestDir: "{{{{app}}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{{{{autoprograms}}\\{appName}"; Filename: "{{{{app}}\\{appName}.exe"
Name: "{{{{autodesktop}}\\{appName}"; Filename: "{{{{app}}\\{appName}.exe"; Tasks: desktopicon

[Run]
Filename: "{{{{app}}\\{appName}.exe"; Description: "{{{{cm:LaunchProgram,{appName}}}"; Flags: nowait postinstall skipifsilent
'''

# 核心修复：使用 utf-8-sig 编码写入文件，确保 Inno Setup 能正确显示中文
issDir = os.path.dirname(__file__)
issPath = os.path.join(issDir, 'InnoSetup.iss')
with open(issPath, 'w+', encoding='utf-8-sig') as f:
    f.write(getIss())

# 核心修复：控制台仅打印英文，防止 GitHub Actions 环境下的编码报错
print(f"Success: Inno Setup config generated at {issPath}")