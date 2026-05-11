; =====================================================
; 授業ファイル振り分けツール - Inno Setup スクリプト
; 使い方:
;   1. このファイルを dist\FileSorter.exe と同じフォルダに置く
;   2. Inno Setup Compiler でこのファイルを開いてビルド
; =====================================================

[Setup]
; アプリ情報
AppName=授業ファイル振り分けツール
AppVersion=1.0.0
AppPublisher=あなたの名前
AppPublisherURL=https://example.com

; インストール先（Program Filesの中にフォルダを作る）
DefaultDirName={autopf}\FileSorter
DefaultGroupName=授業ファイル振り分けツール

; インストーラーの出力設定
OutputDir=installer_output
OutputBaseFilename=FileSorter_Setup_v1.0.0

; インストーラーのアイコン（あれば）
; SetupIconFile=icon.ico

; 圧縮設定（高圧縮）
Compression=lzma2/ultra64
SolidCompression=yes

; 管理者権限不要（ユーザーフォルダにインストール）
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; ウィザードのスタイル
WizardStyle=modern

; 最低限必要なWindowsバージョン（Windows 10以上）
MinVersion=10.0

; アンインストーラーを作成する
Uninstallable=yes
UninstallDisplayName=授業ファイル振り分けツール
CreateUninstallRegKey=yes

; ライセンスファイル（あれば）
; LicenseFile=LICENSE.txt

; インストール前に表示する情報ファイル（あれば）
; InfoBeforeFile=README.txt

[Languages]
; 日本語表示
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
; デスクトップにショートカットを作るか選べるようにする
Name: "desktopicon"; Description: "デスクトップにショートカットを作成する"; GroupDescription: "追加タスク:"

[Files]
; メインのexeファイル（このスクリプトと同じフォルダのdist\FileSorter.exeを参照）
Source: "dist\FileSorter.exe"; DestDir: "{app}"; Flags: ignoreversion

; 取り扱い説明書PDFがあれば同梱する（なければこの行をコメントアウト）
; Source: "取り扱い説明書.pdf"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; スタートメニューにショートカット
Name: "{group}\授業ファイル振り分けツール"; Filename: "{app}\FileSorter.exe"
Name: "{group}\アンインストール"; Filename: "{uninstallexe}"

; デスクトップショートカット（タスクで選択した場合のみ）
Name: "{autodesktop}\授業ファイル振り分けツール"; Filename: "{app}\FileSorter.exe"; Tasks: desktopicon

[Run]
; インストール完了後にアプリを起動するか聞く
Filename: "{app}\FileSorter.exe"; Description: "インストール完了後にアプリを起動する"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; アンインストール時にスタートアップ登録を解除する
Filename: "reg"; Parameters: "delete ""HKCU\Software\Microsoft\Windows\CurrentVersion\Run"" /v FileSorterTray /f"; Flags: runhidden; StatusMsg: "スタートアップ登録を解除しています..."

[UninstallDelete]
; アンインストール時に設定ファイルも削除する（任意）
; Type: files; Name: "{userdocs}\.file_sorter_config.json"
