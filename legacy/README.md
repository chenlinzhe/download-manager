# legacy：早期 Electron 实现（已废弃）

`desktop-main.cjs`、`preload.cjs`、`package.json`、`package-lock.json` 是更早的 Electron 版本遗留文件。
它的扫描、整理与 AI 分析逻辑早已和 `server.py` 漂移，看起来和现在发布的行为不一致，因此只作为历史参考
保存在这里，**不参与构建与发布**。

当前桌面版入口是 `desktop.py`（pywebview），打包脚本是 `build.ps1` +
`下载包管家智能搜索版-v11.spec`。若确实要复活 Electron 版本，把这四个文件移回仓库根目录并
`npm install` 即可。
