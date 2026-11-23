; Inno Setup script for an offline Windows installer of the PyInstaller bundle.
; Compile on Windows:  iscc /DBundleDir=C:\kwb_build\dist\KikuchiWorkbench packaging\kikuchiworkbench.iss
#ifndef BundleDir
  #define BundleDir "..\\dist\\KikuchiWorkbench"
#endif
#define AppVersion "0.1.0.dev0"

[Setup]
AppId={{6C1E9F2B-6B7A-4E5B-9C2D-KIKUCHIWB01}
AppName=KikuchiWorkbench
AppVersion={#AppVersion}
DefaultDirName={autopf}\KikuchiWorkbench
DefaultGroupName=KikuchiWorkbench
OutputBaseFilename=KikuchiWorkbench-{#AppVersion}-setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequiredOverridesAllowed=dialog
; Licence: the application licence is still an open decision (docs/THIRD_PARTY.md); add LicenseFile= once chosen.

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\KikuchiWorkbench"; Filename: "{app}\KikuchiWorkbench.exe"
Name: "{group}\KikuchiWorkbench command prompt"; Filename: "{cmd}"; Parameters: "/K cd /d ""{app}"" && kwb --help"

[Run]
Filename: "{app}\kwb.exe"; Parameters: "demo --jobs ""{localappdata}\KikuchiWorkbench\demo_jobs"" --rows 3 --cols 3 --resolution 6 --quiet"; Description: "Run the offline self-check demo"; Flags: postinstall skipifsilent runhidden
