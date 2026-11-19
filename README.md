English Practice App for Win-x64


推荐使用 uv 管理python包及运行环境 /
在 Windows 上，使用 Winget：winget install uv /
在 macOS 上，使用 Homebrew：brew install uv /
在 Linux 上，使用官方安装脚本：curl -LsSf https://astral.sh/uv/install.sh | sh /

安装完毕后，验证是否安装成功：uv --version
使用命令查看当前可用的 Python 版本：uv python list
推荐安装特定版本（3.12）：uv python install 3.12
在当前项目目录下创建名为 .venv 的虚拟环境：uv venv
安装运行库，需要用到的是：faster-whisper edge-tts requests sounddevice soundfile pygame numpy
使用命令：uv pip install -r requirements.txt



运行界面展示：

<img width="1867" height="996" alt="UI_show" src="https://github.com/user-attachments/assets/d1211300-3c3e-4683-be62-783e4cb4101e" />
