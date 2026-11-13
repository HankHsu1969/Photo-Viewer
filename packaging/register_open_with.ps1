# Registers PhotoViewer.exe (in this folder) as an "Open with" app for images, for the current user only.
# Undo with unregister_open_with.ps1. Windows does not let programs set themselves as the default app;
# pick it once via right-click > Open with > Choose another app > Photo Viewer > Always.
$ErrorActionPreference = 'Stop'
$exe = Join-Path $PSScriptRoot 'PhotoViewer.exe'
if (-not (Test-Path $exe)) { throw "找不到 $exe" }

$progId = 'PhotoViewer.Image'
$appName = 'Photo Viewer 看圖'
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
Set-Default "$C\$progId" 'Photo Viewer 影像'
Set-Str "$C\$progId" 'FriendlyTypeName' 'Photo Viewer 影像'
Set-Default "$C\$progId\DefaultIcon" $icon
Set-Default "$C\$progId\shell" 'open'
Set-Str "$C\$progId\shell\open" 'FriendlyAppName' $appName
Set-Default "$C\$progId\shell\open\command" $cmd

# Application entry (name/icon shown in the Open with list)
$app = "$C\Applications\PhotoViewer.exe"
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
Set-Str $cap 'ApplicationDescription' '快速看圖、相片管理與影像編輯'
Set-Str $cap 'ApplicationIcon' $icon
foreach ($e in $exts) { Set-Str "$cap\FileAssociations" $e $progId }
Set-Str 'HKCU:\Software\RegisteredApplications' 'PhotoViewer' 'Software\PhotoViewer\Capabilities'

# Start menu shortcut
$lnk = Join-Path ([Environment]::GetFolderPath('Programs')) 'Photo Viewer 看圖.lnk'
$sh = New-Object -ComObject WScript.Shell
$s = $sh.CreateShortcut($lnk)
$s.TargetPath = $exe
$s.WorkingDirectory = $PSScriptRoot
$s.IconLocation = "$exe,0"
$s.Description = '快速看圖、相片管理與影像編輯'
$s.Save()

# Tell Explorer that associations changed
Add-Type -Namespace PV -Name Shell -MemberDefinition '[DllImport("shell32.dll")] public static extern void SHChangeNotify(int e, uint f, System.IntPtr a, System.IntPtr b);'
[PV.Shell]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)

Write-Host "已註冊：$exe"
Write-Host "已加入開始功能表捷徑：$lnk"
Write-Host '設為預設：對任一張圖片按右鍵 > 開啟檔案 > 選擇其他應用程式 > Photo Viewer 看圖 > 一律使用'
