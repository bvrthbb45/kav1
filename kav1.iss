[Setup]
AppName=Kav1 App
AppVersion=0.1.0
DefaultDirName={userappdata}\Kav1
PrivilegesRequired=lowest
OutputDir=setup
OutputBaseFilename=kav1_setup
Compression=lzma
SolidCompression=yes
DefaultGroupName=Kav1

[Files]
Source: "backend\dist\server\server.exe"; DestDir: "{app}\server"; Flags: ignoreversion
Source: "backend\dist\server\_internal\*"; DestDir: "{app}\server\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

Source: "frontend\dist\main\main.exe"; DestDir: "{app}\client"; Flags: ignoreversion
Source: "frontend\dist\main\_internal\*"; DestDir: "{app}\client\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Kav1 App"; Filename: "{app}\client\main.exe"
Name: "{group}\Kav1 Server"; Filename: "{app}\server\server.exe"
Name: "{userdesktop}\Kav1 App"; Filename: "{app}\client\main.exe"
Name: "{userdesktop}\Kav1 Server"; Filename: "{app}\server\server.exe"

[Code]
procedure InitializeWizard;
begin
  WizardForm.ClientHeight := WizardForm.ClientHeight + 15;
  with TLabel.Create(WizardForm) do
  begin
    Parent := WizardForm;
    Top := WizardForm.ClientHeight - 18;
    Left := 8;
    Caption := 'Built by Yon Liud - https://github.com/YonLiud';
    Font.Size := 7;
  end;
end;