; Inno Setup script: wraps dist\OfficeFlow into OfficeFlow-Setup-<version>.exe
; Build: iscc /DMyAppVersion=1.2.3 packaging\installer.iss
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
AppId={{6C2D7A43-8E1F-4B7A-9C3E-0F6A2B5D9E11}
AppName=OfficeFlow
AppVersion={#MyAppVersion}
AppPublisher=OfficeFlow
DefaultDirName={localappdata}\Programs\OfficeFlow
DefaultGroupName=OfficeFlow
DisableProgramGroupPage=yes
; Installs for the current user only: no administrator rights needed.
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=OfficeFlow-Setup-{#MyAppVersion}
SetupIconFile=officeflow.ico
UninstallDisplayIcon={app}\OfficeFlow.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\OfficeFlow\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\OfficeFlow"; Filename: "{app}\OfficeFlow.exe"
Name: "{group}\Uninstall OfficeFlow"; Filename: "{uninstallexe}"
Name: "{userdesktop}\OfficeFlow"; Filename: "{app}\OfficeFlow.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\OfficeFlow.exe"; Description: "Start OfficeFlow"; Flags: nowait postinstall skipifsilent

; Settings, history, saved workflows and plugins live in %APPDATA%\OfficeFlow and are kept on uninstall.
