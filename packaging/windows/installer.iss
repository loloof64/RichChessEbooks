; Inno Setup script for the .exe installer. Built by the release workflow:
;   iscc /DAppVersion=0.1.0 /DSourceDir=<bundle> /DOutputDir=<dist> installer.iss

#define AppName "Rich Chess Ebooks"
#define AppExe "rich_chess_ebooks.exe"

[Setup]
AppId={{79488A32-83CE-430B-A263-83A322591B46}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=loloof64
AppPublisherURL=https://github.com/loloof64/RichChessEbooks
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
; Lets the user install for themselves only, without administrator rights.
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=RichChessEbooks-{#AppVersion}-windows-x64-setup
SetupIconFile=..\..\windows\runner\resources\app_icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
