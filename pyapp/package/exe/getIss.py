#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Author: Tang Ming
Date: 2025-12-12 17:42:32
LastEditTime: 2026-01-04 15:00:00
Description: 生成 .iss 配置文件，使用相对路径适配 GitHub Actions
'''

import sys
import os

# 保持原有配置获取逻辑
pyappDir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(pyappDir)
from config.config import Config

appName = Config.appName
appVersion = Config.appVersion[1:] if Config.appVersion.startswith('V') else Config.appVersion
appDeveloper = Config.appDeveloper
appBlogs = Config.appBlogs
appISSID = Config.appISSID

# --- 关键修改：使用相对于 .iss 文件的相对路径 ---
# 假设 .iss 文件生成在 pyapp/package/exe/ 目录下
# build 目录通常在项目根目录，即 ../../../build
relBuildDir = "..\\..\\..\\build"
relLogoPath = "..\\..\\icon\\logo.ico"
relOutputDir = "..\\..\\..\\build_output"

def getIss():
    return f'''
; 脚本由 Python 动态生成，适配 GitHub Actions
#define MyAppName "{appName}"
#define MyAppVersion "{appVersion}"
#define MyAppPublisher "{appDeveloper}"
#define MyAppURL "{appBlogs}"
#define MyAppExeName "{appName}.exe"

[Setup]
AppId={{{appISSID}}}
AppName={{#MyAppName}}
AppVersion={{#MyAppVersion}}
AppPublisher={{#MyAppPublisher}}
AppPublisherURL={{#MyAppURL}}
DefaultDirName={{autopf}}\\{{#MyAppName}}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
; 修改输出目录为相对路径
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
; 核心修复：指向构建出的 exe 或文件夹
; 如果是打包整个目录：
Source: "{relBuildDir}\\*"; DestDir: "{{app}}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{{autoprograms}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"
Name: "{{autodesktop}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\{{#MyAppExeName}}"; Description: "{{cm:LaunchProgram,{{#StringChange(MyAppName, '&', '&&')}}}}"; Flags: nowait postinstall skipifsilent
'''

# 生成配置文件，使用 utf-8-sig 以兼容 Inno Setup 中文
issDir = os.path.dirname(__file__)
issPath = os.path.join(issDir, 'InnoSetup.iss')
with open(issPath, 'w+', encoding='utf-8-sig') as f:
    f.write(getIss())

print(f"成功生成 ISS 配置文件: {issPath}")