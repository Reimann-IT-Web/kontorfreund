; Inno Setup: Installationsprogramm für Windows aus dist\Kontorfreund (PyInstaller).
;
;   iscc /DVersion=0.1.0 packaging\windows\kontorfreund.iss
;
; Installiert nur für den angemeldeten Benutzer, ohne Administratorrechte. Die Daten
; liegen getrennt in %LOCALAPPDATA%\Kontorfreund (siehe kontorfreund.py) und bleiben
; bei Update und Deinstallation erhalten.

#ifndef Version
  #error Version fehlt: iscc /DVersion=0.1.0 …
#endif

[Setup]
; Bleibt für alle Versionen gleich, sonst gilt ein Update als neues Programm.
AppId={{52BF44B4-6F13-4902-8F7A-13F8263453E4}
AppName=Kontorfreund
AppVersion={#Version}
AppVerName=Kontorfreund {#Version}
AppPublisher=Kontorfreund
DefaultDirName={localappdata}\Programs\Kontorfreund
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist
OutputBaseFilename=Kontorfreund-Setup-{#Version}
SetupIconFile=..\..\static\img\kontorfreund.ico
UninstallDisplayIcon={app}\Kontorfreund.exe
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
; Ein laufendes Kontorfreund vor dem Update beenden.
CloseApplications=yes

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Reste der vorigen Version entfernen, damit keine alten Module übrig bleiben.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\..\dist\Kontorfreund\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Das Fenster des Servers startet minimiert; schließen beendet Kontorfreund.
Name: "{autoprograms}\Kontorfreund"; Filename: "{app}\Kontorfreund.exe"; WorkingDir: "{app}"; Flags: runminimized
Name: "{autodesktop}\Kontorfreund"; Filename: "{app}\Kontorfreund.exe"; WorkingDir: "{app}"; Flags: runminimized; Tasks: desktopicon

[Run]
Filename: "{app}\Kontorfreund.exe"; Description: "{cm:LaunchProgram,Kontorfreund}"; Flags: nowait postinstall skipifsilent runminimized
