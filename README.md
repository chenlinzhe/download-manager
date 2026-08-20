# 下载包管家（桌面 AI 版）

本机下载包扫描与整理工具。当前版本：**智能搜索版 v10**（桌面端入口 `desktop.py`，界面 `index.html`）。

应用使用 pywebview（Windows WebView2）显示桌面窗口，直接调用本机 Python，不启动 HTTP 服务、不占用网络端口。

## 运行方式

### 方式一：直接运行源码（开发/自用）

```bash
# 1. 安装依赖（仅需 pywebview）
pip install -r requirements.txt

# 2. 运行桌面版
python desktop.py
```

或双击 `启动下载包管家桌面版.bat`。

### 方式二：打包成 EXE（桌面端 APP，推荐给用户）

```bash
# 一键打包（自动安装依赖并执行 PyInstaller）
powershell -ExecutionPolicy Bypass -File build.ps1
```

产物在 `dist/下载包管家智能搜索版-v10.exe`，绿色免安装，可直接发给用户双击运行；也可以发布到 GitHub Releases 供下载。

### 方式三：Electron 打包（备用桌面方案）

本仓库同时保留了 Electron 桌面壳（`desktop-main.cjs` / `preload.cjs`）：

```bash
npm install
npm run dist   # 生成 portable 版 EXE（electron-builder）
```

## 功能

- 扫描固定盘根目录下名称包含“down”或“下载”的目录，把其中每个一级项目视为一个下载包。
- 根据时间、大小、重下难度、授权情况及可疑破解/注册机文件给出整理建议。
- 支持多选转移、移入 Windows 回收站，以及持久化的“保留（手工）”标记；手工标记不会被重新扫描覆盖。
- 可在“软件设置”中配置或更换 DeepSeek API Key、接口地址及模型。界面只显示密钥尾号，不回显完整密钥。
- 选中下载包后可点击“AI 搜索说明”，查询它是什么、当前价值、重下和授权情况。
- AI 说明按包的名称、大小和修改时间持久缓存。开启自动搜索后，“重新扫描”只查询新增且尚无说明的包，不会反复查询已有结果；发生内容变化的包会作为新版本处理。

## 本地数据

打包后的桌面程序将配置和持久数据保存在 %LOCALAPPDATA%\DownloadPackageManager。

其中包括 settings.json、ai_descriptions.json、inventory.json 和 user_labels.json。请妥善保护包含 API Key 的 settings.json。

> 本仓库仅含干净源码：`settings.json`（含 API Key）已被 `.gitignore` 排除，构建产物 `build*/dist*/node_modules` 不提交；旧浏览器/服务端入口（`server.py`）仍保留用于兼容，但桌面版入口为 `desktop.py`。