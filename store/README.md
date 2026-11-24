# 上架 Microsoft Store：步驟說明

這個資料夾放著上架需要的商品資訊、螢幕擷取畫面和商店圖片。
只有帳號本人能做的步驟標示為「**你**」，其他步驟可以交給 Claude 處理。

| 項目 | 檔案 |
|---|---|
| 商品資訊（中文 / 英文） | `listing.zh-TW.md`、`listing.en-US.md` |
| 螢幕擷取畫面（1920 × 1080，5 張） | `screenshots/` |
| 商店圖片：1:1 方塊圖、2:3 海報圖 | `boxart-1x1-2160.png`、`poster-2x3-1440x2160.png` |
| 隱私權政策 | repo 根目錄的 `PRIVACY.md` |
| MSIX 套件設定 | `packaging/msix/`、`packaging/build_msix.py` |

## 1. 註冊開發者帳號（你）

1. 到 <https://storedeveloper.microsoft.com> 用你的 Microsoft 帳號註冊「個人」開發者帳號（免費）。
2. 依畫面完成身分驗證（證件與自拍）。

## 2. 保留名稱 Kirapix（你）

1. Partner Center >「應用程式和遊戲」>「新增產品」>「MSIX 或 PWA 應用程式」。
2. 輸入 **Kirapix** 保留名稱。如果已被使用，需要換一個名稱。
3. 進入這個產品 >「產品管理」>「產品身分識別」，複製下面三個值：
   - `Package/Identity/Name`
   - `Package/Identity/Publisher`（`CN=` 開頭）
   - `Package/Properties/PublisherDisplayName`

把這三個值交給 Claude，或照 `packaging/msix/identity.json` 的格式填進 `packaging/msix/identity.local.json`（這個檔不會傳上 GitHub，因為發行者名稱是你的本名）。

## 3. 產生上架用的 MSIX 套件

```powershell
build.bat
```

```powershell
python packaging\build_msix.py
```

會產生 `dist\msix\Kirapix-<版本>.msix`。需要微軟的 Windows SDK 打包工具（放在 `tools\winsdk`）；還沒填身分識別時，產生的是只能測試的 `-TEST.msix`。

## 4. 定價：免費

- 「定價和可用性」> 基本價格選 **免費**。免費 App 不需要在 Partner Center 填收款帳戶或稅務資料。
- 市場：所有市場；可見度：公開。

## 5. 屬性、年齡分級

- 類別：**相片與視訊**
- 隱私權原則網址：`https://github.com/HankHsu1969/Photo-Viewer/blob/main/PRIVACY.md`
- 支援網址：`https://github.com/HankHsu1969/Photo-Viewer/issues`
- 系統需求：Windows 10 版本 1809 以上、64 位元
- 年齡分級問卷：本程式沒有使用者互動、分享、位置、網路或購買功能，照實回答即可（通常為 3+）。

## 6. 上傳套件與商品資訊

1. 「套件」：上傳 `Kirapix-<版本>.msix`。
2. 「Store 商品資訊」：分別貼上 `listing.zh-TW.md` 與 `listing.en-US.md` 的內容，上傳 `screenshots/` 的 5 張圖與兩張商店圖片。
3. 「提交選項」> 受限功能 **runFullTrust** 的說明可以填：
   > Kirapix is a desktop (Win32) photo viewer and editor packaged as MSIX. Full trust is required to open, edit and save the user's image files anywhere on disk and to launch its companion fast viewer (Kirapix Quick) for double-clicked images.

## 7. 送審（你）

按「提交至 Store」。審核通常在幾個工作天內完成，結果會寄到你的信箱。

## 之後更新版本

調高 `pv/__init__.py` 的版本號，重新執行第 3 步，在 Partner Center 建立新的提交並上傳新的 `.msix`。

## Store 版與安裝檔版的差異

- Store 版由微軟簽章與自動更新，雙擊圖片的關聯由套件宣告，不需要額外設定。
- Store 版的修圖原檔備份放在「圖片\Kirapix 原檔備份」，解除安裝時不會被刪除。
- Store 版和 GitHub 上的安裝檔版各自保存設定與評等，互不影響。
