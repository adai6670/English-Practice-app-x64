**English Practice App for win/ubuntu-x64**
  
**这是一款基于AI语音人机对话的，用于英语口语练习的程序。**  
  
*推荐使用 uv 管理python包及运行环境，在shell中操作。*  
在 Windows 上，使用 Winget：winget install uv  
在 macOS 上，使用 Homebrew：brew install uv  
在 Linux 上，使用官方安装脚本：curl -LsSf https://astral.sh/uv/install.sh | sh  
安装完毕后，验证是否安装成功：uv --version  
使用命令查看当前可用的 Python 版本：uv python list  
推荐的 python 版本（3.12）：uv python install 3.12  
shell进入项目目录，创建名为 .venv 的虚拟环境：uv venv  
  
*激活虚拟环境*  
macOS / Linux：source .venv/bin/activate  
Windows（PowerShell）：.venv\Scripts\activate  
*退出虚拟环境*  
deactivate  
*日常开发中可以使用 uv run 直接运行脚本，无需手动激活虚拟环境*  
  
**python程序需要用到的运行库有：faster-whisper edge-tts requests sounddevice soundfile pygame**  
  
**Win环境下**  
  
使用命令安装运行库：uv pip install -r requirements.txt  
确认已安装的包：uv pip list  
启动项目：uv run english_talking_win.py  

**Ubuntu环境下（本人运行在26.04.1 LTS）**  
   
##如果运行报错：OSError: PortAudio library not found  
*原始系统缺少 PortAudio 底层库‌，sounddevice 是 Python 封装，它依赖系统级的 PortAudio 动态库才能工作，光 pip install sounddevice 包是不够的，需安装：sudo apt install portaudio19-dev*  
##如果 pip 安装不上 pygame  
*需要补齐：sudo apt install python3-dev libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev libfreetype6-dev libportmidi-dev libjpeg-dev libpng-dev build-essential*  
##文件夹 fonts 及 simhei.ttf 字体，主要用于在ubuntu下，程序界面中文字体出现 口口 问题，程序内通过调用实现显示，亦可切换为微软雅黑字体  
  
使用命令安装运行库：uv pip install av faster-whisper edge-tts requests sounddevice soundfile pygame  
或者使用命令：uv pip install -r requirements.txt  
确认已安装的包：uv pip list  
启动项目：uv run english_talking_ubuntu.py
  
  
**运行界面展示：**  
<img width="600" height="400" alt="屏幕截图 2026-11-19 103733" src="https://github.com/user-attachments/assets/da72c5df-4c5c-4ca5-9755-10b42efe6d30" />


