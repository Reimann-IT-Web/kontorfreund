; Inno Setup: Installationsprogramm für Windows aus dist\Kontorfreund (PyInstaller).
;
;   iscc /DVersion=0.1.0 packaging\windows\kontorfreund.iss
;
; Installiert für alle Benutzer nach C:\Program Files und braucht dafür
; Administratorrechte; Kontorfreund selbst läuft ohne sie. Die Daten liegen je Benutzer
; getrennt in %LOCALAPPDATA%\Kontorfreund (siehe kontorfreund.py) und bleiben bei
; Update und Deinstallation erhalten.

#ifndef Version
  #error Version fehlt: iscc /DVersion=0.1.0 …
#endif

[Setup]
; Bleibt für alle Versionen gleich, sonst gilt ein Update als neues Programm.
AppId={{52BF44B4-6F13-4902-8F7A-13F8263453E4}
AppName=Kontorfreund
AppVersion={#Version}
AppVerName=Kontorfreund {#Version}
AppPublisher=Reimann IT & Web
AppPublisherURL=https://github.com/Reimann-IT-Web/kontorfreund
; Ohne BOM liest Inno Setup das Skript nicht sicher als UTF-8, daher nur ASCII.
AppCopyright=Copyright (C) 2026 Reimann IT & Web, freie Software unter der AGPL-3.0
DefaultDirName={autopf}\Kontorfreund
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist
OutputBaseFilename=Kontorfreund-Setup-{#Version}
SetupIconFile=..\..\static\img\kontorfreund.ico
UninstallDisplayIcon={app}\Kontorfreund.exe
; Aussehen wie das Programm, hell oder dunkel je nach Windows-Einstellung. Quelle der Bilder: bilder\hintergrund.html
WizardStyle=modern dynamic windows11 hidebevels
WizardResizable=no
WizardBackColor=#f7f6f3
WizardBackColorDynamicDark=#15181a
WizardBackImageFile=bilder\hintergrund-hell-*.png
WizardBackImageFileDynamicDark=bilder\hintergrund-dunkel-*.png
Compression=lzma2
SolidCompression=yes
; Ein laufendes Kontorfreund vor dem Update beenden.
CloseApplications=yes

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl,texte.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"

[InstallDelete]
; Reste der vorigen Version entfernen, damit keine alten Module übrig bleiben.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
; Die Schrift des Programms, nur für die Fenster des Installers; steht vorn, weil sie schon beim Start gebraucht wird.
Source: "schrift\*.ttf"; Flags: dontcopy
Source: "..\..\dist\Kontorfreund\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Das Fenster des Servers startet minimiert; schließen beendet Kontorfreund.
Name: "{autoprograms}\Kontorfreund"; Filename: "{app}\Kontorfreund.exe"; WorkingDir: "{app}"; Flags: runminimized
Name: "{autodesktop}\Kontorfreund"; Filename: "{app}\Kontorfreund.exe"; WorkingDir: "{app}"; Flags: runminimized; Tasks: desktopicon

[Registry]
; Den Start beim Anmelden (Einstellungen > Benachrichtigungen) beim Deinstallieren entfernen.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "Kontorfreund"; ValueType: none; Flags: uninsdeletevalue dontcreatekey

[Run]
Filename: "{app}\Kontorfreund.exe"; Description: "{cm:LaunchProgram,Kontorfreund}"; Flags: nowait postinstall skipifsilent runminimized

[Code]
// Der Assistent ist aufgebaut wie das Programm: links die Seitenleiste, rechts der Inhalt.
// Logo und Leiste kommen aus dem Hintergrundbild, die Schritte sind echter Text.

const
  NUR_DIESES_PROGRAMM = $10;
  SCHRIFT = 'Atkinson Hyperlegible Next';
  LINKS = 230;

var
  Schritte: array[0..2] of TNewStaticText;
  Breite: Integer;

function AddFontResourceEx(Datei: String; Art: DWORD; Rest: Cardinal): Integer;
  external 'AddFontResourceExW@gdi32.dll stdcall';
function RemoveFontResourceEx(Datei: String; Art: DWORD; Rest: Cardinal): Boolean;
  external 'RemoveFontResourceExW@gdi32.dll stdcall';

procedure SchriftLaden(Datei: String);
begin
  ExtractTemporaryFile(Datei);
  AddFontResourceEx(ExpandConstant('{tmp}\' + Datei), NUR_DIESES_PROGRAMM, 0);
end;

// Der geladene Schrift-Ordner ließe sich sonst am Ende nicht aufräumen.
procedure DeinitializeSetup;
begin
  RemoveFontResourceEx(ExpandConstant('{tmp}\atkinson-regular.ttf'), NUR_DIESES_PROGRAMM, 0);
  RemoveFontResourceEx(ExpandConstant('{tmp}\atkinson-bold.ttf'), NUR_DIESES_PROGRAMM, 0);
end;

// Das Hintergrundbild ist bei 100 % 596 breit; hieraus folgen alle Maße, damit sie bei jeder Skalierung passen.
function Stelle(Wert: Integer): Integer;
begin
  Result := MulDiv(WizardForm.ClientWidth, Wert, 596);
end;

procedure Ueberschrift(Text: TNewStaticText);
begin
  Text.Font.Name := SCHRIFT;
  Text.Font.Size := 17;
  Text.Font.Style := [fsBold];
end;

procedure Fliesstext(Text: TNewStaticText);
begin
  Text.Font.Name := SCHRIFT;
  Text.Font.Size := 10;
end;

procedure Liste(Text: TNewCheckListBox);
begin
  Text.Font.Name := SCHRIFT;
  Text.Font.Size := 10;
end;

procedure LinkOeffnen(Sender: TObject);
var
  Fehler: Integer;
begin
  ShellExecAsOriginalUser('open', TNewStaticText(Sender).Caption, '', '', SW_SHOWNORMAL, ewNoWait, Fehler);
end;

procedure SchritteAnlegen;
var
  I: Integer;
begin
  for I := 0 to 2 do begin
    Schritte[I] := TNewStaticText.Create(WizardForm);
    Schritte[I].Parent := WizardForm;
    Schritte[I].Caption := CustomMessage('Schritt' + IntToStr(I));
    Schritte[I].StyleElements := Schritte[I].StyleElements - [seFont];
    Schritte[I].Font.Name := SCHRIFT;
    Schritte[I].Font.Size := 11;
    Schritte[I].Left := Stelle(34);
    Schritte[I].Top := Stelle(101 + I * 24);
    Schritte[I].BringToFront;
  end;
end;

procedure SchrittZeigen(Nummer: Integer);
var
  I: Integer;
begin
  for I := 0 to 2 do begin
    if I = Nummer then
      Schritte[I].Font.Style := [fsBold]
    else
      Schritte[I].Font.Style := [];
    // Bei hohem Kontrast zeichnet Windows selbst, die Leiste fehlt dann.
    if not HighContrastActive then
      if I = Nummer then
        Schritte[I].Font.Color := clWhite
      else
        Schritte[I].Font.Color := StrToColor('#b9d3d8');
  end;
end;

function Zeile(Text: String; Von, Oben: Integer): TNewStaticText;
begin
  Result := TNewStaticText.Create(WizardForm);
  Result.Parent := WizardForm.SelectTasksPage;
  Result.ShowAccelChar := False;
  Result.Caption := Text;
  Fliesstext(Result);
  Result.Left := Von;
  Result.Top := Oben;
end;

// Links als eigener Text: die Windows-Linkfarbe ist im Dunkelmodus zu dunkel.
function LinkZeile(Name, Adresse: String; Oben: Integer): Integer;
var
  Vorn, Link: TNewStaticText;
begin
  Vorn := Zeile(CustomMessage(Name), 0, Oben);
  Link := Zeile(CustomMessage(Adresse), Vorn.Width + ScaleX(4), Oben);
  Link.Font.Style := [fsUnderline];
  Link.Cursor := crHand;
  Link.OnClick := @LinkOeffnen;
  if not HighContrastActive then begin
    Link.StyleElements := Link.StyleElements - [seFont];
    if IsDarkInstallMode then
      Link.Font.Color := StrToColor('#8cc4d0')
    else
      Link.Font.Color := StrToColor('#17535f');
  end;
  Result := Oben + Vorn.Height;
end;

procedure HinweisAnlegen;
var
  Hinweis: TNewStaticText;
  Oben: Integer;
begin
  Hinweis := Zeile(CustomMessage('Hinweis'), 0, 0);
  Hinweis.AutoSize := False;
  Hinweis.WordWrap := True;
  Hinweis.Width := Breite;
  Hinweis.AdjustHeight;
  Oben := LinkZeile('QuellcodeName', 'QuellcodeAdresse', Hinweis.Height + Stelle(10));
  LinkZeile('InternetName', 'InternetAdresse', Oben);
end;

procedure SeitenAnordnen;
var
  Rechts, Hoehe: Integer;
begin
  Rechts := WizardForm.CancelButton.Left + WizardForm.CancelButton.Width;
  Breite := Rechts - Stelle(LINKS);

  WizardForm.MainPanel.Height := Stelle(84);
  WizardForm.WizardSmallBitmapImage.Visible := False;
  WizardForm.PageNameLabel.SetBounds(Stelle(LINKS), Stelle(22), Breite, Stelle(32));
  Ueberschrift(WizardForm.PageNameLabel);
  WizardForm.PageDescriptionLabel.SetBounds(Stelle(LINKS), Stelle(54), Breite, Stelle(22));
  Fliesstext(WizardForm.PageDescriptionLabel);

  WizardForm.InnerNotebook.SetBounds(Stelle(LINKS), Stelle(84), Breite, WizardForm.CancelButton.Top - Stelle(84 + 12));
  Hoehe := WizardForm.InnerNotebook.Height;

  // Erste Seite: Hinweise und die eine Frage auf einen Blick statt auf zwei Seiten.
  WizardForm.SelectTasksLabel.Visible := False;
  WizardForm.TasksList.SetBounds(0, Hoehe - Stelle(26), Breite, Stelle(26));
  Liste(WizardForm.TasksList);
  HinweisAnlegen;

  // Die Dateinamen flackern beim Entpacken nur vorbei, der Balken rückt an ihre Stelle.
  WizardForm.FilenameLabel.Visible := False;
  Fliesstext(WizardForm.StatusLabel);
  WizardForm.ProgressGauge.Top := WizardForm.StatusLabel.Top + WizardForm.StatusLabel.Height + Stelle(6);
  WizardForm.ProgressGauge.Height := Stelle(10);

  WizardForm.WizardBitmapImage2.Visible := False;
  WizardForm.FinishedHeadingLabel.SetBounds(Stelle(LINKS), Stelle(22), Breite, Stelle(36));
  Ueberschrift(WizardForm.FinishedHeadingLabel);
  Fliesstext(WizardForm.FinishedLabel);
  Liste(WizardForm.RunList);
end;

// Text und Liste dieser Seite setzt Inno Setup erst beim Öffnen, deshalb erst jetzt.
procedure FertigAnordnen;
begin
  WizardForm.FinishedLabel.SetBounds(Stelle(LINKS), Stelle(62), Breite, Stelle(44));
  WizardForm.FinishedLabel.Caption := Trim(WizardForm.FinishedLabel.Caption);
  WizardForm.FinishedLabel.AdjustHeight;
  WizardForm.RunList.SetBounds(Stelle(LINKS), WizardForm.FinishedLabel.Top + WizardForm.FinishedLabel.Height + Stelle(14), Breite, Stelle(28));
  WizardForm.NextButton.Left := WizardForm.CancelButton.Left;
end;

procedure InitializeWizard;
begin
  SchriftLaden('atkinson-regular.ttf');
  SchriftLaden('atkinson-bold.ttf');
  SeitenAnordnen;
  SchritteAnlegen;
end;

procedure CurPageChanged(Seite: Integer);
begin
  case Seite of
    wpSelectTasks: begin
      SchrittZeigen(0);
      WizardForm.NextButton.Caption := SetupMessage(msgButtonInstall);
    end;
    wpPreparing, wpInstalling: SchrittZeigen(1);
    wpFinished: begin
      SchrittZeigen(2);
      FertigAnordnen;
    end;
  end;
end;
