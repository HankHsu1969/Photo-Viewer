# Registers PhotoViewer.exe (in this folder) as an "Open with" app for images, for the current user only.
# Undo with unregister_open_with.ps1. Windows does not let programs set themselves as the default app;
# pick it once via right-click > Open with > Choose another app > Kirapix Quick > Always.
$ErrorActionPreference = 'Stop'
# Images open in Kirapix Quick (QuickViewer.exe); double-click there opens Kirapix (PhotoViewer.exe).
$full = Join-Path $PSScriptRoot 'PhotoViewer.exe'
$exe = Join-Path $PSScriptRoot 'QuickViewer.exe'
foreach ($f in @($full, $exe)) { if (-not (Test-Path $f)) { throw "找不到 $f" } }

$progId = 'PhotoViewer.Image'
$appName = 'Kirapix Quick'
$exts = @('.jpg', '.jpeg', '.jpe', '.jfif', '.png', '.bmp', '.gif', '.webp', '.tif', '.tiff', '.ico', '.tga')
$cmd = "`"$exe`" `"%1`""
$icon = "`"$exe`",0"
$C = 'HKCU:\Software\Classes'

function Ensure-Key([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) { New-Item -Path $path -Force | Out-Null }
}
function Set-Default([string]$path, [string]$value) {
    Ensure-Key $path
    Set-Item -LiteralPath $path -Value $value
}
function Set-Str([string]$path, [string]$name, [string]$value) {
    Ensure-Key $path
    New-ItemProperty -LiteralPath $path -Name $name -Value $value -PropertyType String -Force | Out-Null
}

# ProgID used by every image extension
Set-Default "$C\$progId" 'Kirapix Quick 影像'
Set-Str "$C\$progId" 'FriendlyTypeName' 'Kirapix Quick 影像'
Set-Default "$C\$progId\DefaultIcon" $icon
Set-Default "$C\$progId\shell" 'open'
Set-Str "$C\$progId\shell\open" 'FriendlyAppName' $appName
Set-Default "$C\$progId\shell\open\command" $cmd

# Application entry (name/icon shown in the Open with list); drop the 1.0 entry that pointed at PhotoViewer.exe
foreach ($old in "$C\Applications\PhotoViewer.exe", "$C\Applications\QuickView.exe") { if (Test-Path -LiteralPath $old) { Remove-Item -LiteralPath $old -Recurse -Force } }
# keep the full program out of "Open with" for files: images belong to Kirapix Quick
Set-Str "$C\Applications\PhotoViewer.exe" 'NoOpenWith' ''
$app = "$C\Applications\QuickViewer.exe"
Set-Str $app 'FriendlyAppName' $appName
Set-Default "$app\DefaultIcon" $icon
Set-Default "$app\shell\open\command" $cmd
foreach ($e in $exts) {
    Set-Str "$app\SupportedTypes" $e ''
    Set-Str "$C\$e\OpenWithProgids" $progId ''
}

# Capabilities so it also appears in Settings > Apps > Default apps
$cap = 'HKCU:\Software\PhotoViewer\Capabilities'
Set-Str $cap 'ApplicationName' $appName
Set-Str $cap 'ApplicationDescription' '快速看圖；雙擊開啟 Kirapix 管理與修圖'
Set-Str $cap 'ApplicationIcon' $icon
foreach ($e in $exts) { Set-Str "$cap\FileAssociations" $e $progId }
Set-Str 'HKCU:\Software\RegisteredApplications' 'PhotoViewer' 'Software\PhotoViewer\Capabilities'

# Start menu shortcut
$progs = [Environment]::GetFolderPath('Programs')
foreach ($old in 'Photo Viewer 看圖.lnk', 'Photo Viewer.lnk') { Remove-Item -LiteralPath (Join-Path $progs $old) -Force -ErrorAction SilentlyContinue }
$lnk = Join-Path $progs 'Kirapix.lnk'
$sh = New-Object -ComObject WScript.Shell
$s = $sh.CreateShortcut($lnk)
$s.TargetPath = $full
$s.WorkingDirectory = $PSScriptRoot
$s.IconLocation = "$full,0"
$s.Description = '相片管理與影像編輯'
$s.Save()

# Tell Explorer that associations changed
Add-Type -Namespace PV -Name Shell -MemberDefinition '[DllImport("shell32.dll")] public static extern void SHChangeNotify(int e, uint f, System.IntPtr a, System.IntPtr b);'
[PV.Shell]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)

Write-Host "已註冊：$exe"
Write-Host "已加入開始功能表捷徑：$lnk"
Write-Host '設為預設：對任一張圖片按右鍵 > 開啟檔案 > 選擇其他應用程式 > Kirapix Quick > 一律使用'
