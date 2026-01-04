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
appISSID = Config.appISSID

# 使用相对路径，解决 GitHub Actions 的路径匹配问题 
relBuildDir = "..\\..\\..\\build"
relLogoPath = "..\\..\\icon\\logo.ico"
relOutputDir = "..\\..\\..\\build_output"

def getIss():
    return f'''
; This file is auto-generated for GitHub Actions
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
; 打包 build 目录下的所有文件 [cite: 2]
Source: "{relBuildDir}\\*"; DestDir: "{{app}}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{{autoprograms}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"
Name: "{{autodesktop}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\{{#MyAppExeName}}"; Description: "{{cm:LaunchProgram,{{#StringChange(MyAppName, '&', '&&')}}}}"; Flags: nowait postinstall skipifsilent
'''

# 关键修复点 1：使用 utf-8-sig 编码写入，解决 InnoSetup 的中文识别问题 
issDir = os.path.dirname(__file__)
issPath = os.path.join(issDir, 'InnoSetup.iss')
with open(issPath, 'w+', encoding='utf-8-sig') as f:
    f.write(getIss())

# 关键修复点 2：将 print 语句改为英文，避免 UnicodeEncodeError 
print(f"Successfully generated ISS config: {issPath}")