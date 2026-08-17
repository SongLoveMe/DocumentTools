#define MyAppName "DocumentTools"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "DocumentTools"
#define MyAppExeName "DocumentTools.exe"

[Setup]
AppId={{8F7F3FD5-8C39-4D3B-9AAE-0F79E4E7C2A0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\DocumentTools
DefaultGroupName={#MyAppName}
OutputDir=..\release
OutputBaseFilename=DocumentTools-Setup-{#MyAppVersion}
ArchitecturesInstallIn64BitMode=x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\documenttools.ico

[Files]
Source: "..\dist\DocumentTools\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\vendor\libreoffice\*"; DestDir: "{app}\runtime\libreoffice"; Flags: recursesubdirs ignoreversion skipifsourcedoesntexist
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\documenttools.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\documenttools.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\documenttools.ico"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
