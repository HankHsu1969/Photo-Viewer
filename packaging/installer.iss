; Photo Viewer installer (Inno Setup 6). Build with build.bat, or:
;   ISCC packaging\installer.iss
; Per-user install (no admin): %LOCALAPPDATA%\Programs\PhotoViewer

#define AppName "Photo Viewer"
#define AppVersion "1.3.0"
#define AppExe "PhotoViewer.exe"
#define QuickExe "QuickViewer.exe"
#define QuickName "Quick Viewer"
#define Root ".."

[Setup]
AppId={{71A24371-3A86-4A2E-8C09-48DB9B1E8911}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Photo Viewer
AppComments=相片管理與影像編輯；雙擊圖片以 Quick Viewer 快速看圖
PrivilegesRequired=lowest
DefaultDirName={autopf}\PhotoViewer
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
OutputDir={#Root}\dist\installer
OutputBaseFilename=PhotoViewer-Setup-{#AppVersion}
SetupIconFile={#Root}\assets\app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
ChangesAssociations=yes
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} 安裝程式
VersionInfoProductName={#AppName}

[Tasks]
Name: "fileassoc"; Description: "雙擊圖片用 Quick Viewer 開啟：加入「開啟檔案」清單（JPG、PNG、GIF、WEBP、TIFF…）"; GroupDescription: "整合："
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#Root}\dist\PhotoViewer\*"; DestDir: "{app}"; Excludes: "Register-OpenWith.bat,Unregister-OpenWith.bat,register_open_with.ps1,unregister_open_with.ps1"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; renamed in 1.1.1: old Quick Viewer exe and the old "Photo Viewer 看圖" shortcuts
Type: files; Name: "{app}\QuickView.exe"
Type: files; Name: "{autoprograms}\Photo Viewer 看圖.lnk"
Type: files; Name: "{autodesktop}\Photo Viewer 看圖.lnk"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "相片管理與影像編輯"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Double-clicked images open in the lightweight Quick Viewer (QuickViewer.exe)
; ProgID
Root: HKA; Subkey: "Software\Classes\PhotoViewer.Image"; ValueType: string; ValueName: ""; ValueData: "Quick Viewer 影像"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\PhotoViewer.Image"; ValueType: string; ValueName: "FriendlyTypeName"; ValueData: "Quick Viewer 影像"; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\PhotoViewer.Image\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\{#QuickExe}"",0"; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\PhotoViewer.Image\shell"; ValueType: string; ValueName: ""; ValueData: "open"; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\PhotoViewer.Image\shell\open"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#QuickName}"; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\PhotoViewer.Image\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#QuickExe}"" ""%1"""; Tasks: fileassoc
; Application entry shown in the Open with list. 1.0 registered PhotoViewer.exe for images: replace that
; with NoOpenWith so Windows never offers (or falls back to) the full program for opening files.
Root: HKA; Subkey: "Software\Classes\Applications\PhotoViewer.exe"; ValueType: string; ValueName: "NoOpenWith"; ValueData: ""; Flags: deletekey uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\QuickView.exe"; Flags: deletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#QuickExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#QuickName}"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Applications\{#QuickExe}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\{#QuickExe}"",0"; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Applications\{#QuickExe}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#QuickExe}"" ""%1"""; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Applications\{#QuickExe}\SupportedTypes"; ValueType: string; ValueName: ".jpg"; ValueData: ""; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Applications\{#QuickExe}\SupportedTypes"; ValueType: string; ValueName: ".jpeg"; ValueData: ""; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Applications\{#QuickExe}\SupportedTypes"; ValueType: string; ValueName: ".jpe"; ValueData: ""; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Applications\{#QuickExe}\SupportedTypes"; ValueType: string; ValueName: ".jfif"; ValueData: ""; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Applications\{#QuickExe}\SupportedTypes"; ValueType: string; ValueName: ".png"; ValueData: ""; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Applications\{#QuickExe}\SupportedTypes"; ValueType: string; ValueName: ".bmp"; ValueData: ""; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Applications\{#QuickExe}\SupportedTypes"; ValueType: string; ValueName: ".gif"; ValueData: ""; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Applications\{#QuickExe}\SupportedTypes"; ValueType: string; ValueName: ".webp"; ValueData: ""; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Applications\{#QuickExe}\SupportedTypes"; ValueType: string; ValueName: ".tif"; ValueData: ""; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Applications\{#QuickExe}\SupportedTypes"; ValueType: string; ValueName: ".tiff"; ValueData: ""; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Applications\{#QuickExe}\SupportedTypes"; ValueType: string; ValueName: ".ico"; ValueData: ""; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Applications\{#QuickExe}\SupportedTypes"; ValueType: string; ValueName: ".tga"; ValueData: ""; Tasks: fileassoc
; Add to each extension's "Open with" list (other apps' entries are left alone)
Root: HKA; Subkey: "Software\Classes\.jpg\OpenWithProgids"; ValueType: string; ValueName: "PhotoViewer.Image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\.jpeg\OpenWithProgids"; ValueType: string; ValueName: "PhotoViewer.Image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\.jpe\OpenWithProgids"; ValueType: string; ValueName: "PhotoViewer.Image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\.jfif\OpenWithProgids"; ValueType: string; ValueName: "PhotoViewer.Image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\.png\OpenWithProgids"; ValueType: string; ValueName: "PhotoViewer.Image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\.bmp\OpenWithProgids"; ValueType: string; ValueName: "PhotoViewer.Image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\.gif\OpenWithProgids"; ValueType: string; ValueName: "PhotoViewer.Image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\.webp\OpenWithProgids"; ValueType: string; ValueName: "PhotoViewer.Image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\.tif\OpenWithProgids"; ValueType: string; ValueName: "PhotoViewer.Image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\.tiff\OpenWithProgids"; ValueType: string; ValueName: "PhotoViewer.Image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\.ico\OpenWithProgids"; ValueType: string; ValueName: "PhotoViewer.Image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\.tga\OpenWithProgids"; ValueType: string; ValueName: "PhotoViewer.Image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
; Capabilities: list under Settings > Apps > Default apps
Root: HKA; Subkey: "Software\PhotoViewer"; Flags: uninsdeletekeyifempty; Tasks: fileassoc
Root: HKA; Subkey: "Software\PhotoViewer\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#QuickName}"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKA; Subkey: "Software\PhotoViewer\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "快速看圖；雙擊開啟 Photo Viewer 管理與修圖"; Tasks: fileassoc
Root: HKA; Subkey: "Software\PhotoViewer\Capabilities"; ValueType: string; ValueName: "ApplicationIcon"; ValueData: """{app}\{#QuickExe}"",0"; Tasks: fileassoc
Root: HKA; Subkey: "Software\PhotoViewer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".jpg"; ValueData: "PhotoViewer.Image"; Tasks: fileassoc
Root: HKA; Subkey: "Software\PhotoViewer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".jpeg"; ValueData: "PhotoViewer.Image"; Tasks: fileassoc
Root: HKA; Subkey: "Software\PhotoViewer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".jpe"; ValueData: "PhotoViewer.Image"; Tasks: fileassoc
Root: HKA; Subkey: "Software\PhotoViewer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".jfif"; ValueData: "PhotoViewer.Image"; Tasks: fileassoc
Root: HKA; Subkey: "Software\PhotoViewer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".png"; ValueData: "PhotoViewer.Image"; Tasks: fileassoc
Root: HKA; Subkey: "Software\PhotoViewer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".bmp"; ValueData: "PhotoViewer.Image"; Tasks: fileassoc
Root: HKA; Subkey: "Software\PhotoViewer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".gif"; ValueData: "PhotoViewer.Image"; Tasks: fileassoc
Root: HKA; Subkey: "Software\PhotoViewer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".webp"; ValueData: "PhotoViewer.Image"; Tasks: fileassoc
Root: HKA; Subkey: "Software\PhotoViewer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".tif"; ValueData: "PhotoViewer.Image"; Tasks: fileassoc
Root: HKA; Subkey: "Software\PhotoViewer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".tiff"; ValueData: "PhotoViewer.Image"; Tasks: fileassoc
Root: HKA; Subkey: "Software\PhotoViewer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".ico"; ValueData: "PhotoViewer.Image"; Tasks: fileassoc
Root: HKA; Subkey: "Software\PhotoViewer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".tga"; ValueData: "PhotoViewer.Image"; Tasks: fileassoc
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "PhotoViewer"; ValueData: "Software\PhotoViewer\Capabilities"; Flags: uninsdeletevalue; Tasks: fileassoc

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Messages]
SetupAppTitle=安裝程式
SetupWindowTitle=安裝程式 - %1
UninstallAppTitle=解除安裝
UninstallAppFullTitle=解除安裝 %1
AboutSetupMenuItem=關於安裝程式(&A)...
ConfirmTitle=確認
InformationTitle=資訊
ErrorTitle=錯誤
SetupAlreadyRunning=安裝程式已在執行中。
ButtonBack=< 上一步(&B)
ButtonNext=下一步(&N) >
ButtonInstall=安裝(&I)
ButtonOK=確定
ButtonCancel=取消
ButtonYes=是(&Y)
ButtonYesToAll=全部皆是(&A)
ButtonNo=否(&N)
ButtonNoToAll=全部皆否(&O)
ButtonFinish=完成(&F)
ButtonBrowse=瀏覽(&B)...
ButtonWizardBrowse=瀏覽(&R)...
ButtonNewFolder=新增資料夾(&M)
ExitSetupTitle=結束安裝
ExitSetupMessage=安裝尚未完成。如果現在結束，程式將不會被安裝。%n%n您可以稍後再執行安裝程式完成安裝。%n%n確定要結束安裝嗎？
BrowseDialogTitle=瀏覽資料夾
BrowseDialogLabel=請在下方清單中選擇資料夾，然後按「確定」。
NewFolderName=新資料夾
WelcomeLabel1=歡迎使用 [name] 安裝精靈
WelcomeLabel2=這個程式會在您的電腦上安裝 [name/ver]。%n%n建議您先關閉其他應用程式再繼續。
WizardSelectDir=選擇安裝位置
SelectDirDesc=要將 [name] 安裝在哪裡？
SelectDirLabel3=安裝程式會將 [name] 安裝到下列資料夾。
SelectDirBrowseLabel=按「下一步」繼續。如果要選擇其他資料夾，請按「瀏覽」。
DiskSpaceGBLabel=至少需要 [gb] GB 的可用磁碟空間。
DiskSpaceMBLabel=至少需要 [mb] MB 的可用磁碟空間。
DirExistsTitle=資料夾已存在
DirExists=資料夾：%n%n%1%n%n已經存在。仍要安裝到這個資料夾嗎？
WizardSelectTasks=選擇附加工作
SelectTasksDesc=要執行哪些附加工作？
SelectTasksLabel2=請選擇安裝 [name] 時要執行的附加工作，然後按「下一步」。
WizardReady=準備安裝
ReadyLabel1=安裝程式已準備好在您的電腦上安裝 [name]。
ReadyLabel2a=按「安裝」開始安裝；如要檢視或修改設定，請按「上一步」。
ReadyLabel2b=按「安裝」開始安裝。
ReadyMemoDir=安裝位置：
ReadyMemoTasks=附加工作：
WizardPreparing=準備安裝
PreparingDesc=安裝程式正在準備將 [name] 安裝到您的電腦。
ApplicationsFound=下列應用程式正在使用需要更新的檔案。建議讓安裝程式自動關閉這些應用程式。
ApplicationsFound2=下列應用程式正在使用需要更新的檔案。建議讓安裝程式自動關閉這些應用程式；安裝完成後會嘗試重新啟動它們。
CloseApplications=自動關閉應用程式(&A)
DontCloseApplications=不要關閉應用程式(&D)
WizardInstalling=安裝中
InstallingLabel=正在安裝 [name]，請稍候。
FinishedHeadingLabel=[name] 安裝完成
FinishedLabelNoIcons=[name] 已安裝到您的電腦。
FinishedLabel=[name] 已安裝到您的電腦，可從開始功能表的捷徑啟動。
ClickFinish=按「完成」結束安裝程式。
StatusClosingApplications=正在關閉應用程式...
StatusCreateDirs=正在建立資料夾...
StatusExtractFiles=正在解壓縮檔案...
StatusCreateIcons=正在建立捷徑...
StatusCreateRegistryEntries=正在寫入登錄資訊...
StatusSavingUninstall=正在儲存解除安裝資訊...
StatusRunProgram=正在完成安裝...
StatusRollback=正在復原變更...
ConfirmUninstall=確定要完全移除 %1 及其所有元件嗎？
WizardUninstalling=解除安裝狀態
UninstallStatusLabel=正在從您的電腦移除 %1，請稍候。
StatusUninstalling=正在解除安裝 %1...
UninstalledAll=%1 已從您的電腦移除。

[CustomMessages]
AdditionalIcons=其他捷徑：
CreateDesktopIcon=建立桌面捷徑(&D)
LaunchProgram=立即啟動 %1
UninstallProgram=解除安裝 %1
