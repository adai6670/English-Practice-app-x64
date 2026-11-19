English Practice App for Win-x64


推荐使用 uv 管理python包及运行环境，在shell中操作。  
在 Windows 上，使用 Winget：winget install uv  
在 macOS 上，使用 Homebrew：brew install uv  
在 Linux 上，使用官方安装脚本：curl -LsSf https://astral.sh/uv/install.sh | sh  
安装完毕后，验证是否安装成功：uv --version  
使用命令查看当前可用的 Python 版本：uv python list  
推荐安装特定版本（3.12）：uv python install 3.12  
在shell中进入项目目录，创建名为 .venv 的虚拟环境：uv venv  

##激活虚拟环境  
macOS / Linux：source .venv/bin/activate  
Windows（PowerShell）：.venv\Scripts\activate  
##退出虚拟环境  
deactivate  
##日常开发中可以使用 uv run 直接运行脚本，无需手动激活虚拟环境。  
  
安装运行库，需要用到的是：faster-whisper edge-tts requests sounddevice soundfile pygame numpy。  
使用命令：uv pip install -r requirements.txt  
确认已安装的包：uv pip list  
启动项目：uv run english_talking_gui_win.py  

运行界面展示：
<img width="1506" height="1007" alt="屏幕截图 2026-11-19 103733" src="https://github.com/user-attachments/assets/da72c5df-4c5c-4ca5-9755-10b42efe6d30" />


