; Inno Setup script for Partseek — (c) Expand Technology Solutions.
; Build:  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer\Partseek.iss
; Produces: release_out\Partseek-Setup-<version>.exe
;
; The payload (release_out\Partseek.exe) is a PyArmor-obfuscated, PyInstaller
; one-file build — see installer\build_protected.py. Build the exe first.

#define MyAppName "Partseek"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Expand Technology Solutions"
#define MyAppExeName "Partseek.exe"

[Setup]
AppId={{081AE835-FD0B-4F26-8161-724E318AC7E5}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
VersionInfoCopyright=Copyright (c) 2026 {#MyAppPublisher}. All rights reserved.
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
; Install to Program Files -> needs admin. Comment the next two lines and set
; PrivilegesRequired=lowest for a per-user install that needs no admin rights.
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\release_out
OutputBaseFilename=Partseek-Setup-{#MyAppVersion}
SetupIconFile=..\partseek.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
WizardStyle=modern
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\release_out\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; DestName: "README.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
