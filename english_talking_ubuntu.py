import asyncio
import os
import queue
import shlex
import shutil
import subprocess
import tempfile
import threading
import time

# ===== 在导入 tkinter 之前注入本地 fonts/ 目录到 Fontconfig =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(BASE_DIR, "fonts")


def setup_local_fonts_for_tk(fonts_dir: str):
    """为当前进程创建临时 Fontconfig 配置，使 Tk 能够扫描项目本地 fonts/ 下的字体文件。"""
    if not os.path.isdir(fonts_dir):
        return None
    has_font = any(
        name.lower().endswith((".ttf", ".otf", ".ttc"))
        for name in os.listdir(fonts_dir)
    )
    if not has_font:
        return None

    tmp_dir = tempfile.mkdtemp(prefix="tk_fonts_")
    conf_path = os.path.join(tmp_dir, "fonts.conf")
    cache_dir = os.path.join(tmp_dir, "cache")
    os.makedirs(cache_dir, exist_ok=True)

    # 继承系统默认规则并追加本地 fonts 目录，同时把缓存写到临时目录避免污染系统缓存
    conf_xml = f"""<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>
  <dir>{os.path.abspath(fonts_dir)}</dir>
  <cachedir>{os.path.abspath(cache_dir)}</cachedir>
</fontconfig>
"""
    with open(conf_path, "w", encoding="utf-8") as f:
        f.write(conf_xml)

    os.environ["FONTCONFIG_FILE"] = conf_path
    return tmp_dir


_TK_FONT_TMP_DIR = setup_local_fonts_for_tk(FONTS_DIR)

import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, scrolledtext, filedialog, simpledialog

# ===== PyAV 19.0.2 兼容性修复 =====
import av

_original_av_open = av.open


def av_open_compat(*args, **kwargs):
    # PyAV 19 不再支持 metadata_errors 参数
    kwargs.pop("metadata_errors", None)
    return _original_av_open(*args, **kwargs)


av.open = av_open_compat
# ===== 兼容性修复结束 =====

import edge_tts
import requests
import sounddevice as sd
import soundfile as sf
from faster_whisper import WhisperModel


# ---------------- 配置 ----------------
# 请确认 models/ 下的 Whisper 模型目录名称；如名称不同，请修改此行。
STT_MODEL_SIZE = r"models/faster-whisper-base"
# 注意：这里填入你在 llama-server 中加载的模型名称（或者简单的 "gemma"）
LLM_MODEL = "gemma-4"
# 修改为你的 llama-server 地址（默认通常是 8080 端口）
LLAMA_SERVER_URL = "http://127.0.0.1:8080/v1/chat/completions"
# 也可以换成 "en-US-GuyNeural" (男声)
TTS_VOICE = "en-US-JennyNeural"

INPUT_AUDIO = "test_audio.wav"
# MP3 文件固定保存在 Python 程序所在目录
OUTPUT_AUDIO = os.path.join(BASE_DIR, "output_response.mp3")

SAMPLE_RATE = 16000
CHANNELS = 1
# 录音设备默认使用系统默认麦克风
AUDIO_DTYPE = "int16"

# 可选：将你自己的 llama-server 启动命令写入这里。
# 留空时，点击“启动 llama-server”会弹出输入框，你可以临时填写完整命令。
LLAMA_SERVER_COMMAND = r"""
echo "程序自动运行 1-llama_ubuntu.sh，请保持终端窗口运行直至程序运行结束"
pwd
sh ./1-llama_ubuntu.sh
""".strip()


stt_model = None


def get_tk_font_family(root, preferred_names=("Microsoft Yahei UI",)):
    """获取 Tk 实际可用的字体族名称，优先匹配本地/系统中的目标字体。"""
    available = list(tkfont.families(root))
    available_lower = {name.lower(): name for name in available}

    for target in preferred_names:
        if target in available:
            return target
        if target.lower() in available_lower:
            return available_lower[target.lower()]

    for name in available:
        if any(k in name.lower() for k in ("simhei", "cjk", "wqy", "noto", "hei", "song")):
            return name

    return "TkDefaultFont"


def speech_to_text(audio_path):
    segments, _ = stt_model.transcribe(audio_path, beam_size=5)
    return "".join(segment.text for segment in segments).strip()


def ask_gemma(user_text, history):
    """将完整对话历史发送给 llama-server，保留多轮上下文。"""
    system_prompt = (
        "You are a patient professional English conversation teacher. "
        "Help the student practice English. Keep the answer concise and suitable for speaking. "
        "For every student message, respond in this exact structure:\n"
        "1) Natural English: give a natural corrected version of the student's sentence. "
        "If the sentence is already correct, say it is natural and do not overcorrect.\n"
        "2) 中文解释: briefly explain the key grammar or wording corrections in Chinese. "
        "If no correction is needed, say so in Chinese.\n"
        "3) English reply: continue the conversation naturally in English and ask at most one follow-up question.\n"
        "Use clear labels. Do not reveal internal reasoning."
    )
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1024,
    }
    response = requests.post(
        LLAMA_SERVER_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=(10, 180),
    )
    response.raise_for_status()
    data = response.json()
    message = data["choices"][0]["message"]
    return (message.get("content") or "").strip()


async def text_to_speech(text, output_file=OUTPUT_AUDIO):
    if not text or not text.strip():
        raise ValueError("模型回复为空，无法生成语音。")
    # TTS 念英文部分，不朗读中文纠错说明和标签。
    english_text = extract_english_for_tts(text)
    if not english_text.strip():
        english_text = text
    communicate = edge_tts.Communicate(english_text, TTS_VOICE)
    await communicate.save(output_file)


def extract_english_for_tts(text):
    """从格式化回复中提取适合朗读的英文，避免 TTS 朗读中文说明。"""
    lines = text.splitlines()
    english_sections = []
    current = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if line.startswith(("1)", "1.", "Natural English:", "自然英文：", "自然英文:")):
            current = "correction"
            # 同行标签后的内容
            for sep in (":", "："):
                if sep in line:
                    value = line.split(sep, 1)[1].strip()
                    if value:
                        english_sections.append(value)
                    break
            continue
        if line.startswith(("2)", "2.", "中文解释：", "中文解释:")):
            current = "chinese"
            continue
        if line.startswith(("3)", "3.", "English reply:", "英文回复：", "英文回复:")):
            current = "reply"
            for sep in (":", "："):
                if sep in line:
                    value = line.split(sep, 1)[1].strip()
                    if value:
                        english_sections.append(value)
                    break
            continue
        if current in ("correction", "reply"):
            # 不让含中文的解释进入语音
            if not any('\u4e00' <= c <= '\u9fff' for c in line):
                english_sections.append(line)
    return " ".join(english_sections).strip()


class EnglishTalkingApp:
    def __init__(self, root, font_family="SimHei"):
        self.root = root
        self.ui_font = font_family
        self.root.title("English Talking - 英语口语练习")
        self.root.geometry("900x720")
        self.root.minsize(680, 520)

        self.events = queue.Queue()
        self.busy = False
        self.recording = False
        self.replaying = False
        self.audio_stream = None
        self.audio_chunks = []
        self.audio_lock = threading.Lock()
        self.turn_history = []
        self.llama_process = None
        self.record_button_state = "idle"

        top = tk.Frame(root, padx=12, pady=10)
        top.pack(fill="x")
        tk.Label(top, text="英语口语练习", font=(self.ui_font, 16)).pack(side="left")
        self.start_server_button = tk.Button(
            top, text="开启 llama-server 服务", font=(self.ui_font, 10), command=self.start_llama_server
        )
        self.start_server_button.pack(side="left", padx=(20, 6))
        self.server_status_var = tk.StringVar(value="服务器：未由本界面启动")
        tk.Label(top, textvariable=self.server_status_var, font=(self.ui_font, 10), anchor="w").pack(side="left", padx=6)

        self.status_var = tk.StringVar(value="正在初始化界面...")
        tk.Label(root, textvariable=self.status_var, font=(self.ui_font, 10), anchor="w", padx=12).pack(fill="x")

        self.chat = scrolledtext.ScrolledText(
            root, wrap="word", font=(self.ui_font, 11), state="disabled"
        )
        self.chat.pack(fill="both", expand=True, padx=12, pady=8)
        self.chat.tag_config("user_label", foreground="#1769aa", font=(self.ui_font, 10))
        self.chat.tag_config("assistant_label", foreground="#16803c", font=(self.ui_font, 10))
        self.chat.tag_config("error", foreground="#c62828", font=(self.ui_font, 10))
        self.chat.tag_config("translation", foreground="#777777", font=(self.ui_font, 10))

        controls = tk.Frame(root, padx=12, pady=8)
        controls.pack(fill="x")
        # 开始录音 按钮
        self.record_button = tk.Button(
            controls, text="🎙 开始录音", font=(self.ui_font, 12),
            height=2, width=18, command=self.toggle_recording, state="disabled"
        )
        self.record_button.pack(side="left")
        # 重播纠错 按钮
        self.replay_button = tk.Button(
            controls,
            text="🔊 重播纠错",
            command=self.replay_response,
            font=(self.ui_font, 10)
        )
        self.replay_button.pack(side="left", padx=8)
        # 清空对话 按钮
        tk.Button(
            controls,
            text="清空对话",
            command=self.clear_chat,
            font=(self.ui_font, 10)
        ).pack(side="left", padx=8)
        # 重置对话上下文 按钮
        tk.Button(
            controls,
            text="重置对话上下文",
            command=self.reset_history,
            font=(self.ui_font, 10)
        ).pack(side="left")
        tk.Label(
            controls,
            text="点击开始录音，再次点击结束；处理完成并播放后可继续下一轮。",
            font=(self.ui_font, 10),
            anchor="w", justify="left", wraplength=390,
        ).pack(side="left", padx=12)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self.poll_events)
        self.root.after(200, self.initialize_model)

    def append_chat(self, label, text, tag):
        self.chat.configure(state="normal")
        self.chat.insert("end", f"{label}\n", tag)
        self.chat.insert("end", f"{text}\n\n")
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def replay_response(self):
        """重播上一次 AI 英语纠错语音"""
        if self.busy or self.recording or self.replaying:
            return
        if not os.path.isfile(OUTPUT_AUDIO):
            messagebox.showinfo(
                "无法重播",
                "尚未生成语音文件 output_response.mp3！"
            )
            return
        self.replaying = True
        self.replay_button.configure(state="disabled")
        self.set_status("正在重播上一次 AI 英语回复...")
        threading.Thread(
            target=self._replay_worker,
            daemon=True
        ).start()

    def _replay_worker(self):
        """后台播放，避免界面卡顿"""
        try:
            self.play_audio_blocking(OUTPUT_AUDIO)
        except Exception as exc:
            self.events.put((
                "error",
                f"重播失败：{type(exc).__name__}: {exc}"
            ))
        finally:
            self.events.put(("replay_done", None))

    def clear_chat(self):
        if self.busy or self.recording:
            messagebox.showinfo("请稍候", "录音或处理期间不能清空对话。")
            return
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")

    def reset_history(self):
        if self.busy or self.recording:
            messagebox.showinfo("请稍候", "录音或处理期间不能重置上下文。")
            return
        self.turn_history.clear()
        self.set_status("已重置模型对话上下文；屏幕上的历史文字仍保留。")

    def set_status(self, text):
        self.status_var.set(text)

    def initialize_model(self):
        self.record_button.configure(state="disabled")
        self.set_status("正在加载 Whisper 模型，请稍候...")
        threading.Thread(target=self._load_model_worker, daemon=True).start()

    def _load_model_worker(self):
        try:
            global stt_model
            stt_model = WhisperModel(STT_MODEL_SIZE, device="cpu", compute_type="int8")
            self.events.put(("ready", "Whisper 模型已加载，可以开始录音。"))
        except Exception as exc:
            self.events.put(("error", f"Whisper 模型加载失败：{exc}"))

    def toggle_recording(self):
        if self.busy or self.replaying:
            return
        if not self.recording:
            self.begin_recording()
        else:
            self.end_recording()

    def begin_recording(self):
        try:
            self.audio_chunks = []
            self.audio_stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=AUDIO_DTYPE,
                callback=self.audio_callback,
            )
            self.audio_stream.start()
            self.recording = True
            self.record_button.configure(text="■ 结束录音")
            self.set_status("正在录音……再次点击按钮结束录音。")
        except Exception as exc:
            self.audio_stream = None
            self.recording = False
            messagebox.showerror("录音启动失败", str(exc))

    def audio_callback(self, indata, frames, time_info, status):
        if status:
            self.events.put(("status", f"录音设备提示：{status}"))
        with self.audio_lock:
            self.audio_chunks.append(indata.copy())

    def end_recording(self):
        if not self.recording:
            return
        self.recording = False
        self.record_button.configure(text="正在处理...", state="disabled")
        try:
            self.audio_stream.stop()
            self.audio_stream.close()
            self.audio_stream = None
            with self.audio_lock:
                chunks = list(self.audio_chunks)
                self.audio_chunks = []
            if not chunks:
                raise RuntimeError("没有录到音频，请检查麦克风。")
            import numpy as np
            audio = np.concatenate(chunks, axis=0)
            sf.write(INPUT_AUDIO, audio, SAMPLE_RATE, subtype="PCM_16")
            self.busy = True
            self.set_status("录音已保存，正在识别语音...")
            threading.Thread(target=self._turn_worker, daemon=True).start()
        except Exception as exc:
            self.busy = False
            self.record_button.configure(text="🎙 开始录音", state="normal")
            messagebox.showerror("录音结束失败", str(exc))

    def _turn_worker(self):
        try:
            user_text = speech_to_text(INPUT_AUDIO)
            if not user_text:
                self.events.put(("error", "没有识别到语音，请重新录音。"))
                return
            self.events.put(("user", user_text))
            self.events.put(("status", "正在等待 Gemma 回复..."))
            reply = ask_gemma(user_text, self.turn_history)
            if not reply:
                raise RuntimeError("模型返回空回复，请检查 llama-server。")
            self.turn_history.extend([
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": reply},
            ])
            self.events.put(("assistant", reply))
            self.events.put(("status", "正在生成语音..."))
            asyncio.run(text_to_speech(reply, OUTPUT_AUDIO))
            self.events.put(("status", "正在播放 AI 英文回复..."))
            self.play_audio_blocking(OUTPUT_AUDIO)
            self.events.put(("status", "本轮完成，可以继续点击“开始录音”。"))
        except Exception as exc:
            self.events.put(("error", f"{type(exc).__name__}: {exc}"))
        finally:
            self.events.put(("turn_done", None))

    @staticmethod
    def play_audio_blocking(path):
        import pygame
        pygame.mixer.init()
        try:
            pygame.mixer.music.load(os.path.abspath(path))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
        finally:
            pygame.mixer.music.stop()
            pygame.mixer.quit()

    def start_llama_server(self):
        if self.llama_process and self.llama_process.poll() is None:
            messagebox.showinfo("llama-server", "本程序启动的 llama-server 仍在运行。")
            return
        command = LLAMA_SERVER_COMMAND
        if not command or all(
            line.strip().startswith("#") or not line.strip()
            for line in command.splitlines()
        ):
            command = simpledialog.askstring(
                "启动 llama-server",
                "请输入完整启动命令（例如 ./llama-server --model xxx.gguf）：",
                parent=self.root,
            )
        if not command or not command.strip():
            return

        wrapped_cmd = f"{command}\necho '--- 命令已结束，按回车关闭窗口 ---'\nread -r _"
        child_env = os.environ.copy()
        child_env.pop("FONTCONFIG_FILE", None)

        terminal_builders = [
            ("ptyxis", lambda c: ["ptyxis", "--", "bash", "-c", c]),
            ("gnome-terminal", lambda c: ["gnome-terminal", "--", "bash", "-c", c]),
            ("kgx", lambda c: ["kgx", "--", "bash", "-c", c]),
            ("xfce4-terminal", lambda c: ["xfce4-terminal", "-e", f"bash -c {shlex.quote(c)}"]),
            ("tilix", lambda c: ["tilix", "-e", f"bash -c {shlex.quote(c)}"]),
            ("konsole", lambda c: ["konsole", "-e", "bash", "-c", c]),
            ("xterm", lambda c: ["xterm", "-e", "bash", "-c", c]),
        ]

        try:
            launched = False
            for term_name, builder in terminal_builders:
                if shutil.which(term_name) is None:
                    continue
                self.llama_process = subprocess.Popen(
                    builder(wrapped_cmd),
                    cwd=BASE_DIR,
                    env=child_env,
                )
                launched = True
                break

            if not launched:
                log_path = os.path.join(BASE_DIR, "llama_server.log")
                log_file = open(log_path, "a", encoding="utf-8")
                self.llama_process = subprocess.Popen(
                    ["bash", "-c", command],
                    cwd=BASE_DIR,
                    env=child_env,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                )
                self.server_status_var.set("服务器：已后台启动（无图形终端）")
                self.set_status(f"未检测到图形终端，已后台启动，日志见 {log_path}")
                return

            self.server_status_var.set("服务器：已请求启动（请查看新开的终端窗口）")
            self.set_status("已打开 llama-server 终端窗口；请确认模型加载完成后再开始对话。")
        except Exception as exc:
            messagebox.showerror("启动失败", f"{type(exc).__name__}: {exc}")

    def poll_events(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "ready":
                    self.set_status(payload)
                    self.record_button.configure(state="normal")
                elif kind == "status":
                    self.set_status(payload)
                elif kind == "user":
                    self.append_chat("你（语音识别）", payload, "user_label")
                elif kind == "assistant":
                    self.append_chat("AI 老师（英文纠错 + 中文解释）", payload, "assistant_label")
                elif kind == "error":
                    self.set_status(payload)
                    self.append_chat("错误", payload, "error")
                    messagebox.showerror("程序运行错误", payload)
                elif kind == "turn_done":
                    self.busy = False
                    self.record_button.configure(text="🎙 开始录音", state="normal")
                elif kind == "replay_done":
                    self.replaying = False
                    self.replay_button.configure(state="normal")
                    self.set_status("重播完成，可以继续练习。")
        except queue.Empty:
            pass
        self.root.after(100, self.poll_events)

    def on_close(self):
        if self.recording and self.audio_stream:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception:
                pass
        self.root.destroy()


def main():
    root = tk.Tk()
    ui_font = get_tk_font_family(root, preferred_names=("SimHei",))
    app = EnglishTalkingApp(root, font_family=ui_font)
    try:
        root.mainloop()
    finally:
        if _TK_FONT_TMP_DIR and os.path.isdir(_TK_FONT_TMP_DIR):
            shutil.rmtree(_TK_FONT_TMP_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()
