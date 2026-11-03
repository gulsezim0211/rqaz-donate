#define MyAppName "RQAZ-DONATE"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "RONIN & QSEZIIM"
#define MyAppExeName "RQAZ-DONATE.exe"

[Setup]
AppId={{C722610E-7C24-4C65-A392-0F3B54B5A5DB}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\RQAZ-DONATE
DefaultGroupName=RQAZ-DONATE
DisableProgramGroupPage=yes
OutputDir=installer-output
OutputBaseFilename=RQAZ-DONATE-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\RQAZ-DONATE"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\RQAZ-DONATE"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить RQAZ-DONATE"; Flags: nowait postinstall skipifsilent
