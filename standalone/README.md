# Mon3tr 独立 Windows 桌宠

这是不依赖 Codex 的便携版，适用于 Windows 10/11 x64。程序是原生 Win32 可执行文件，不需要 Python 或 .NET 运行时。

## 运行

下载仓库中的 [`downloads/Mon3tr-standalone-win-x64.zip`](../downloads/Mon3tr-standalone-win-x64.zip)，解压后双击 `Mon3tr.exe`。请把 `assets` 文件夹与 EXE 放在同一目录。也可在完整仓库中直接运行本目录的 `Mon3tr.exe`。

- 左键按住角色拖动。拖动距离决定步伐，水平移动方向决定朝向，停下便切回待机。
- 右键角色，选择“退出 Mon3tr”。
- 透明区域允许鼠标穿过，窗口始终显示在普通桌面窗口之上。

![16 个连续姿势预览](walk-contact-sheet.png)

## 流畅度设计

行走循环由 8 个双脚承重关键姿势插值得到 64 个不同画面。窗口按所在显示器的刷新率更新，最高目标为 240 Hz；实际显示帧率取决于显示器和系统负载。桌宠静止时，相同画面不会重复提交给桌面合成器。

## 从源码构建

素材生成需要 Python、Pillow 和 NumPy。先在仓库根目录运行：

```powershell
python -m pip install -r requirements.txt
python standalone/tools/generate_assets.py
python standalone/tools/check_assets.py
```

程序构建需要 Visual Studio 2022 的 C++ 桌面开发组件。在仓库根目录运行：

```powershell
./standalone/build.ps1
./standalone/Mon3tr.exe --self-test
```

`standalone/src/Mon3tr.cpp` 实现原生透明窗口、按距离推进的行走动画、跟随显示器刷新率的渲染循环和退出菜单。`standalone/assets` 包含构建与运行所需的 PNG 动画图集。

本项目为非官方同人桌宠，与《明日方舟》官方无关。许可及第三方角色权利说明见仓库根目录的 [LICENSE](../LICENSE) 和 [README](../README.md)。
