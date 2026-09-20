#define AppName "OCR PDF Layer Tool"
#ifndef AppVersion
  #define AppVersion "1.1.6"
#endif
#define AppPublisher "OCRTool"
#define AppExeName "OCRTool.exe"

[Setup]
AppId={{A9F99F2D-3D88-4E2A-A4D9-90D9BD31C11C}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\OCRTool
DefaultGroupName={#AppName}
DisableProgramGroupPage=no
OutputDir=output
OutputBaseFilename=OCRTool-Setup-{#AppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\icon.ico
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#AppExeName},0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked
Name: "contextmenu"; Description: "Add right-click menu: OCR this PDF"; GroupDescription: "Explorer integration:"; Flags: checkedonce
Name: "associatepdf"; Description: "Associate .pdf files with OCR PDF Layer Tool"; GroupDescription: "Explorer integration:"; Flags: unchecked

[Files]
Source: "..\dist\OCRTool\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; AppUserModelID: "0verWatchO5.OCRTool.PDFLayer"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon; AppUserModelID: "0verWatchO5.OCRTool.PDFLayer"

[Registry]
Root: HKCR; Subkey: "SystemFileAssociations\.pdf\shell\OCRWithOCRTool"; ValueType: string; ValueName: ""; ValueData: "OCR this PDF"; Tasks: contextmenu; Flags: uninsdeletekey
Root: HKCR; Subkey: "SystemFileAssociations\.pdf\shell\OCRWithOCRTool"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#AppExeName},0"; Tasks: contextmenu
Root: HKCR; Subkey: "SystemFileAssociations\.pdf\shell\OCRWithOCRTool\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; Tasks: contextmenu; Flags: uninsdeletekey

Root: HKCR; Subkey: ".pdf"; ValueType: string; ValueName: ""; ValueData: "OCRTool.PDF"; Tasks: associatepdf
Root: HKCR; Subkey: "OCRTool.PDF"; ValueType: string; ValueName: ""; ValueData: "PDF File (OCR PDF Layer Tool)"; Tasks: associatepdf; Flags: uninsdeletekey
Root: HKCR; Subkey: "OCRTool.PDF\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExeName},0"; Tasks: associatepdf; Flags: uninsdeletekey
Root: HKCR; Subkey: "OCRTool.PDF\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; Tasks: associatepdf; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
