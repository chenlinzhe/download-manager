const {contextBridge, ipcRenderer} = require('electron');
contextBridge.exposeInMainWorld('desktop', {
  scan: force => ipcRenderer.invoke('scan', !!force),
  keep: paths => ipcRenderer.invoke('keep', paths),
  move: (paths, destination) => ipcRenderer.invoke('move', {paths, destination}),
  recycle: paths => ipcRenderer.invoke('recycle', paths)
});
