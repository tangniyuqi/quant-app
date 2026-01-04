; 已经针对 GitHub Actions 路径和编码问题进行了优化
#define MyAppName "Sophon"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Tang Ming"
#define MyAppURL "https://go.boooya.com"
; 关键点：确保这里的名字和你在 build 流程（如 npm run build）中生成的 exe 文件名完全一致
#define MyAppExeName "Sophon.exe" 
#define MyAppAssocName MyAppName + " File"
#define MyAppAssocExt ".myp"
#define MyAppAssocKey StringChange(MyAppAssocName, " ", "") + MyAppAssocExt

[Setup]
AppId={{AC18B034-AC83-EA47-AC87-3D3FC82BA9A1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
ChangesAssociations=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest

; 路径修复：使用相对路径指向根目录下的输出位置
OutputDir=..\..\..\build_output
OutputBaseFilename=Sophon-V1.0.0_Windows
SetupIconFile=..\..\icon\logo.ico

Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; 核心修复：指向 GitHub 工作流生成的 build 目录 
; 建议加上 ignoreversion 避免版本冲突 
Source: "..\..\..\build\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; 如果 build 目录下还有其他依赖文件夹，建议取消下行注释以包含所有文件
; Source: "..\..\..\build\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent