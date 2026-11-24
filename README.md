# Kirapix

Windows 上的快速看圖、相片管理與影像編輯工具，操作方式與常見的專業看圖軟體相近（Python + PySide6 + NumPy + Pillow）。

由兩個程式組成，共用同一個程式資料夾：

| 程式 | 用途 | 啟動時間 |
|---|---|---|
| **Kirapix Quick**（`QuickViewer.exe`） | 快速看圖：在檔案總管雙擊圖片時開啟。只載入最精簡的 Qt 繪圖模組，←/→ 立即換圖 | 約 0.5 秒 |
| **Kirapix**（`PhotoViewer.exe`） | 管理與修圖：一個視窗、三種模式，右上角切換：**管理 / 檢視 / 編輯** | 約 1 秒 |

在 Kirapix Quick 中**雙擊影像或按 Enter** → 開啟 Kirapix 的管理模式並選取這張；**按 E** → 直接進入編輯。

## Kirapix Quick（快速看圖）

- **← / →**、滾輪、空白鍵、PgUp/PgDn、Home/End：上一張 / 下一張（前後幾張已預先載入）
- **雙擊 / Enter**：開啟 Kirapix 管理；**E**：開啟 Kirapix 編輯
- Ctrl+滾輪、+ / -：縮放（放大超過螢幕大小時才載入原始解析度）；`0` 符合視窗、`1` 實際大小；拖曳平移
- F / F11 全螢幕、I 顯示資訊、`[` / `]` 旋轉（JPEG 無損）、Delete 移到資源回收筒、Ctrl+C 複製、Ctrl+0~5 評等、Esc 關閉

## 安裝與啟動（原始碼）

```bash
python -m pip install -r requirements.txt
```

```bash
python main.py
```

```bash
python quickviewer.py "C:\path\to\photo.jpg"
```

- `main.py` 另接受 `--manage <圖片>`（開管理並選取）與 `--edit <圖片>`（直接編輯），Kirapix Quick 就是用這兩個參數交接給 Kirapix。
- 直接雙擊 `PhotoViewer.bat` 也可以啟動（不會出現命令列視窗）。
- 把**圖片**拖到 `PhotoViewer.bat` 上 → 直接進入檢視模式，←/→ 瀏覽同資料夾。
- 把**資料夾**拖到 `PhotoViewer.bat` 上 → 在管理模式開啟該資料夾。
- 不帶參數 → 開啟上次瀏覽的資料夾（第一次為「圖片」資料夾）。

## 安裝檔（建議）

`dist\installer\Kirapix-Setup-1.4.0.exe`（約 28 MB）—— 繁體中文安裝精靈，不需要系統管理員權限：

- 安裝到 `%LOCALAPPDATA%\Programs\PhotoViewer`（即 `C:\Users\<你的帳號>\AppData\Local\Programs\PhotoViewer`），可在精靈中更改
- 建立開始功能表捷徑；可選建立桌面捷徑
- 可選「加入圖片的開啟檔案清單」（預設勾選）—— 雙擊圖片會用 Kirapix Quick 開啟，開始功能表的「Kirapix」捷徑則開啟管理與修圖程式
- 出現在「設定 > 應用程式」中，可從那裡解除安裝；解除安裝會移除程式、捷徑與登錄項目，但保留你的設定、評等與縮圖快取（`%APPDATA%\PhotoViewer`、`%LOCALAPPDATA%\PhotoViewer`）
- 安裝新版本時直接執行新的安裝檔即可（會自動關閉執行中的 Kirapix）

## 免安裝版與手動設定「開啟方式」

免安裝版在 `dist\PhotoViewer\`（整個資料夾一起用，約 96 MB）：

- `QuickViewer.exe` —— Kirapix Quick 快速看圖，把圖片拖上去即可
- `PhotoViewer.exe` —— Kirapix 管理與修圖
- `Register-OpenWith.bat` —— 把 Kirapix Quick 加入圖片的「開啟檔案」清單、開始功能表捷徑，並列入「設定 > 應用程式 > 預設應用程式」（只寫入目前使用者的設定）
- `Unregister-OpenWith.bat` —— 完整移除上述註冊

Windows 不允許程式自行設為預設，第一次請手動指定：對任一張圖片按右鍵 →「開啟檔案」→「選擇其他應用程式」→ **Kirapix Quick** → 「一律使用」。之後在檔案總管雙擊圖片就會直接用它開啟。

若搬移 `dist\PhotoViewer` 資料夾，請在新位置重新執行 `Register-OpenWith.bat`。

重新打包（修改程式後）—— 需要 PyInstaller；若已安裝 Inno Setup，會一併產生安裝檔：

```bash
python -m pip install pyinstaller
```

```bash
winget install JRSoftware.InnoSetup
```

```bash
build.bat
```

## Kirapix：檢視模式

- **← / →** 上一張 / 下一張（也可用滑鼠滾輪、空白鍵、PgUp/PgDn、Home/End）
- **雙擊影像**（或 Enter / Esc）→ 開啟管理介面，並自動選取目前這張
- 背景預先解碼前後幾張，連續翻頁幾乎零等待
- Ctrl+滾輪、+/- 縮放（以游標為中心），拖曳平移；`0` 符合視窗、`1` 實際大小
- F / F11 全螢幕、S 投影片播放、I 顯示 EXIF 資訊、T 顯示/隱藏縮圖列
- `[` / `]` 向左/右旋轉 —— JPEG 為**無損旋轉**（只改 EXIF 方向，不重新壓縮）
- Delete 移到資源回收筒、Ctrl+C 複製影像、Ctrl+0~5 評等
- 支援 EXIF 自動轉正、GIF 動畫、JPG/PNG/WEBP/TIFF/BMP/GIF/ICO/TGA

## 設定（字體大小）

在 Kirapix 按右上角的**齒輪**，或選單「**設定 > 顯示與字體大小…**」（Ctrl+,）：

- 用滑桿（8～18 pt）或「小／標準／大／特大」按鈕調整整個軟體的字體大小，畫面立即預覽
- 按「確定」儲存（下次開啟沿用），「取消」恢復原本大小，「還原預設」回到 9.5 pt
- Kirapix Quick 的資訊文字也會套用（下次開啟時）

## Kirapix：管理模式

- 左：快速存取（桌面/圖片/下載/文件，Ctrl+D 加入我的最愛）＋資料夾樹
- 中：縮圖瀏覽（背景多執行緒產生、磁碟快取、Ctrl+滾輪調整大小、可拖曳檔案到其他程式）
- 右：預覽＋屬性（檔案資訊、尺寸、評等、相機 EXIF：快門、光圈、ISO、焦距、GPS…）
- 排序（名稱/日期/大小/類型、遞增遞減）、評等篩選、檔名搜尋
- 右鍵選單：檢視、**編輯**、**拼接圖片**、旋轉、評等、複製到/移動到、重新命名、刪除、
  批次重新命名、批次調整大小／轉檔、複製路徑、在檔案總管中顯示
- **拖曳移動／複製**：把縮圖拖到左側資料夾樹、快速存取或縮圖格中的資料夾即可移動；跨磁碟預設為複製，按住 Ctrl 複製、Shift 移動；從檔案總管拖進來的檔案會複製到目前資料夾
- 資料夾內容變動時自動重新整理

### 拼接圖片

在管理畫面按住 Ctrl 或 Shift 選取要拼接的圖片 → 按工具列的「**拼接**」或右鍵「**拼接圖片…**」（選單「工具 > 拼接圖片」也有）。在編輯畫面按工具列的「**拼接**」則以目前這張為第一張。

- **往下接**（第一張在最上面）、**往右接**（第一張在最左邊）、**往左接**（第一張在最右邊）
- 按「**加入圖片…**」可從任何資料夾再加入圖片；在左側清單拖曳調整順序，或用上移／下移／反轉／移除
- 尺寸：縮放成相同寬度（往下）或相同高度（往左、往右），以最小或最大的為準；或保持原尺寸置中對齊
- 可設定間距、四周留邊與底色；即時預覽並顯示輸出尺寸
- 輸出 JPEG 或 PNG，存到目前資料夾（可更改）；可勾選「完成後開啟編輯」，再裁切、調整尺寸或加上文字

## Kirapix：編輯模式（修圖）

在縮圖上按右鍵 →「編輯」（或 Ctrl+E）。所有調整皆為**非破壞性**，即時預覽，儲存時才以完整解析度套用。

| 區塊 | 功能 |
|---|---|
| 曝光／光線 | 曝光 (EV)、亮度、對比、亮部、陰影（依局部明暗自動調整）、白色、黑色、清晰度、去霧、一鍵自動調整光線 |
| 色階 | RGB／紅／綠／藍通道，拖曳黑點／中間調／白點與輸出範圍，自動色階、自動對比 |
| 色調曲線 | RGB 與各通道曲線，點擊新增控制點、右鍵刪除 |
| 白平衡與飽和度 | 色溫、色調、**滴管點選中性灰自動校正**、鮮豔度、飽和度 |
| 色彩 EQ（HSL） | 紅/橙/黃/綠/青/藍/紫/洋紅 八個色域的色相、飽和度、亮度 |
| 色彩平衡 | 陰影／中間調／亮部分別調整青紅、洋紅綠、黃藍，可保持明度 |
| 分離色調 | 亮部與陰影各自上色，可調平衡 |
| 黑白 | 轉黑白並依六個色域調整明暗 |
| 細節 | 銳利化（數量、半徑）、雜訊消除 |
| 幾何 | 90° 旋轉、水平/垂直翻轉、拉直（自動裁去黑邊）、裁切、調整尺寸 |
| 特效 | 暈影（數量、中點、羽化）、底片顆粒 |

工具列上的三個工具：

- **裁切**（C）：拖曳框線或四個角調整範圍、在框外拖曳重新框選；比例可選自由、原始、1:1、4:3、3:2、16:9…（含直式），即時顯示裁切後的像素尺寸；Enter 套用、Esc 取消
- **尺寸**（Ctrl+R）：輸入寬度或高度、百分比，或選常用長邊（3840、1920、1080…）；可保持長寬比或自訂（會拉伸）。保持長寬比時記住的是長邊，之後再裁切或旋轉也會維持
- **文字**（T）：在影像上點一下即可新增文字並直接輸入（可多行）。拖曳移動、拖曳右下角方塊縮放、方向鍵微調、Delete 刪除；可設定字型、粗體／斜體、對齊、大小、顏色、不透明度、旋轉角度、外框、陰影與底色方塊。可加入多段文字，新增的文字沿用上一段的樣式

- 預設集：鮮豔、柔和、高對比、暖/冷色調、電影感、復古懷舊、褪色底片、黑白經典…，也可儲存/載入自訂預設集（套用預設集不會改動裁切、尺寸與文字）
- 按住「比較原圖」或 `\` 鍵檢視原圖；Ctrl+Z / Ctrl+Y 復原 / 取消復原；雙擊任何滑桿重設該項
- 儲存（Ctrl+S）會先把原檔備份到 `%LOCALAPPDATA%\PhotoViewer\originals`；另存新檔（Ctrl+Shift+S）可選 JPEG/PNG/WEBP/TIFF/BMP、品質與輸出尺寸；保留 EXIF 與 ICC 色彩描述檔

## 第三方元件授權

本程式使用下列開放原始碼元件，各依其授權條款散布。完整條文在 [`licenses/`](licenses/)（安裝後位於程式資料夾的 `licenses`），程式內可從「說明 > 開放原始碼授權…」查看。

| 元件 | 授權 |
|---|---|
| Qt 6 / PySide6、Shiboken6 | GNU LGPL v3（[原始碼](https://download.qt.io/official_releases/qt/)、[PySide6 原始碼](https://code.qt.io/cgit/pyside/pyside-setup.git/)） |
| Python | Python Software Foundation License |
| NumPy | BSD 3-Clause（含隨附元件的授權） |
| Pillow | MIT-CMU（HPND，含隨附影像函式庫的授權） |
| PyInstaller 啟動程式 | GPL 2.0+，附 bootloader 例外條款 |

Qt 與 PySide6 未經修改，以動態連結方式使用：Qt 函式庫是程式資料夾內獨立的 DLL 檔案（`_internal\PySide6`），可以自行替換成相容版本。`build.bat` 打包時會執行 `packaging\collect_licenses.py`，從目前的 Python 環境更新授權檔案與版本號，並把 `licenses` 複製到程式資料夾。

## 商標聲明

文中提到的產品名稱與商標（例如 Windows）屬於其各自的擁有者。本專案為個人獨立開發，未經任何商業看圖或修圖軟體廠商授權、贊助或認可，也與它們沒有任何關係。

## 資料存放位置

- 設定、評等：`%APPDATA%\PhotoViewer\`
- 縮圖快取、原檔備份、預設集：`%LOCALAPPDATA%\PhotoViewer\`
- Microsoft Store 版的原檔備份：`圖片\Kirapix 原檔備份`（Store App 解除安裝時會清除自己的 AppData，原檔備份放在這裡才不會被刪掉）

（1.4.0 起程式改名為 Kirapix；為了讓舊版順利升級、保留你的設定與預設看圖程式，exe 檔名與設定資料夾名稱維持不變。）

## Microsoft Store

上架用的商品資訊、螢幕擷取畫面、商店圖片與步驟說明在 [`store/`](store/)；隱私權政策在 [`PRIVACY.md`](PRIVACY.md)。MSIX 套件由 `packaging\build_msix.py` 產生。

## 程式結構

```
main.py            進入點
quickviewer.py     Kirapix Quick 進入點（QuickViewer.exe）
pv/quick.py        Kirapix Quick 視窗（只用 QtCore/QtGui，背景預先載入）
pv/startup.py      兩個程式共用的啟動工具（錯誤記錄、中文按鈕、互相啟動）
pv/mainwindow.py   主視窗與 管理/檢視/編輯 模式切換（編輯器延遲載入）
pv/viewer.py       檢視模式（預先載入、縮圖列、全螢幕、投影片）
pv/manager.py      管理模式（資料夾樹、縮圖、預覽、屬性、檔案操作）
pv/editor.py       編輯模式（調整面板、裁切／文字工具、背景算圖、復原、儲存）
pv/imageops.py     影像處理管線（曝光、色階、曲線、HSL、色彩平衡…、尺寸）
pv/textlayer.py    文字圖層的排版與繪製（預覽與存檔共用）
pv/stitch.py       拼接圖片（往下／往右／往左）
pv/canvas.py       可縮放平移的影像畫布、裁切框、文字圖層互動
pv/thumbs.py       縮圖快取與縮圖模型
pv/editwidgets.py  滑桿、色階分佈圖、色階與曲線元件
pv/dialogs.py      重新命名、批次處理、調整尺寸、儲存選項、說明
pv/common.py       共用工具（EXIF、無損旋轉、評等、圖示…）
licenses/          第三方元件授權條文與 THIRD-PARTY-NOTICES.txt
packaging/         PyInstaller 規格、安裝檔腳本、圖示與授權檔案產生器
```
