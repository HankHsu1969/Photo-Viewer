# Removes everything register_open_with.ps1 added (current user only).
$ErrorActionPreference = 'SilentlyContinue'
$progId = 'PhotoViewer.Image'
$exts = @('.jpg', '.jpeg', '.jpe', '.jfif', '.png', '.bmp', '.gif', '.webp', '.tif', '.tiff', '.ico', '.tga')
$C = 'HKCU:\Software\Classes'

Remove-Item -LiteralPath "$C\$progId" -Recurse -Force
Remove-Item -LiteralPath "$C\Applications\PhotoViewer.exe" -Recurse -Force
foreach ($e in $exts) {
    Remove-ItemProperty -LiteralPath "$C\$e\OpenWithProgids" -Name $progId -Force
}
Remove-Item -LiteralPath 'HKCU:\Software\PhotoViewer\Capabilities' -Recurse -Force
$root = Get-Item -LiteralPath 'HKCU:\Software\PhotoViewer'
if ($root -and $root.SubKeyCount -eq 0 -and $root.ValueCount -eq 0) { Remove-Item -LiteralPath 'HKCU:\Software\PhotoViewer' -Force }
Remove-ItemProperty -LiteralPath 'HKCU:\Software\RegisteredApplications' -Name 'PhotoViewer' -Force
Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath('Programs')) 'Photo Viewer 看圖.lnk') -Force

Add-Type -Namespace PV -Name Shell -MemberDefinition '[DllImport("shell32.dll")] public static extern void SHChangeNotify(int e, uint f, System.IntPtr a, System.IntPtr b);'
[PV.Shell]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
Write-Host '已移除 Photo Viewer 的開啟方式註冊與開始功能表捷徑。'
