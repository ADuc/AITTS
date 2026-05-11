import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import asyncio
import edge_tts
import threading
import os
import re
import json
import urllib.error
import urllib.request

# ====================================
# DATA
# ====================================
all_voices = []
DEFAULT_OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_OLLAMA_MODEL = "gemma4"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_DIR = r"D:\audio\NOIDUNG"
DEFAULT_OUTPUT_FILENAME = "audio_001.mp3"
DEFAULT_VOICE = "en-US-AriaNeural"
DEFAULT_SPEED = 0
SETTINGS_FILE = os.path.join(APP_DIR, "tts_app_settings.json")
INVALID_FILENAME_CHARS = '<>:"/\\|?*'
app_settings = {}

# ====================================
# SETTINGS
# ====================================
def load_app_settings():

    if not os.path.exists(SETTINGS_FILE):
        return {}

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as settings_file:
            return json.load(settings_file)
    except (OSError, json.JSONDecodeError):
        return {}


def save_app_settings():

    settings = {
        "voice": get_selected_voice_name(),
        "speed": speed_slider.get(),
        "output_dir": output_dir_entry.get().strip() or DEFAULT_OUTPUT_DIR
    }

    os.makedirs(APP_DIR, exist_ok=True)

    with open(SETTINGS_FILE, "w", encoding="utf-8") as settings_file:
        json.dump(settings, settings_file, ensure_ascii=False, indent=2)

# ====================================
# LOAD VOICES
# ====================================
async def load_voices():

    global all_voices

    voices = await edge_tts.list_voices()

    all_voices = voices

    languages = set()
    countries = set()
    genders = set()

    for v in voices:

        locale = v["Locale"]

        parts = locale.split("-")

        if len(parts) >= 2:

            languages.add(parts[0])
            countries.add(parts[1])

        genders.add(v["Gender"])

    language_combo["values"] = ["All"] + sorted(languages)
    country_combo["values"] = ["All"] + sorted(countries)
    gender_combo["values"] = ["All"] + sorted(genders)

    language_combo.current(0)
    country_combo.current(0)
    gender_combo.current(0)

    update_voice_list()

# ====================================
# UPDATE VOICE LIST
# ====================================
def update_voice_list(event=None):

    selected_language = language_combo.get()
    selected_country = country_combo.get()
    selected_gender = gender_combo.get()
    search_text = search_entry.get().lower()

    filtered = []

    for v in all_voices:

        locale = v["Locale"]

        parts = locale.split("-")

        lang = ""
        country = ""

        if len(parts) >= 2:
            lang = parts[0]
            country = parts[1]

        if selected_language != "All":
            if lang != selected_language:
                continue

        if selected_country != "All":
            if country != selected_country:
                continue

        if selected_gender != "All":
            if v["Gender"] != selected_gender:
                continue

        voice_name = v["ShortName"]

        display_name = (
            f"{voice_name} | "
            f"{locale} | "
            f"{v['Gender']}"
        )

        if search_text:
            if search_text not in display_name.lower():
                continue

        filtered.append(display_name)

    voice_combo["values"] = filtered

    if filtered:
        voice_combo.current(0)


def get_selected_voice_name():

    selected_voice = voice_combo.get()

    if not selected_voice:
        return ""

    return selected_voice.split("|")[0].strip()


def select_voice_by_name(voice_name):

    if not voice_name:
        return

    voices = voice_combo["values"]

    for index, display_name in enumerate(voices):
        if display_name.split("|")[0].strip() == voice_name:
            voice_combo.current(index)
            return


def apply_app_settings():

    select_voice_by_name(app_settings.get("voice", DEFAULT_VOICE))

    speed = app_settings.get("speed", DEFAULT_SPEED)

    if isinstance(speed, int):
        speed_slider.set(speed)

    output_dir = app_settings.get("output_dir", DEFAULT_OUTPUT_DIR)

    if output_dir:
        output_dir_entry.delete(0, tk.END)
        output_dir_entry.insert(0, output_dir)

        next_filename = get_next_available_filename(
            output_dir,
            filename_entry.get()
        )
        filename_entry.delete(0, tk.END)
        filename_entry.insert(0, next_filename)

# ====================================
# OLLAMA TRANSLATION
# ====================================
def translate_to_english_with_ollama(text, model, api_url):

    prompt = (
        "Translate the following Vietnamese text into natural spoken English. "
        "Return only the English translation, with no notes, quotes, markdown, "
        "or explanation.\n\n"
        f"Vietnamese text:\n{text}"
    )

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2
        }
    }

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        api_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama HTTP error {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            "Cannot connect to Ollama. Make sure Ollama is running and the API URL is correct."
        ) from e

    translated_text = response_data.get("response", "").strip()

    if not translated_text:
        raise RuntimeError("Ollama returned an empty translation.")

    return translated_text

# ====================================
# OUTPUT FILE HELPERS
# ====================================
def normalize_mp3_filename(filename):

    filename = filename.strip()

    if not filename:
        filename = DEFAULT_OUTPUT_FILENAME

    filename = os.path.basename(filename)

    for char in INVALID_FILENAME_CHARS:
        filename = filename.replace(char, "_")

    name, ext = os.path.splitext(filename)

    if not name:
        name = "audio"

    if ext.lower() != ".mp3":
        ext = ".mp3"

    return f"{name}{ext}"


def increment_mp3_filename(filename):

    filename = normalize_mp3_filename(filename)
    name, ext = os.path.splitext(filename)
    match = re.search(r"(\d+)$", name)

    if match:
        number_text = match.group(1)
        next_number = int(number_text) + 1
        next_name = f"{name[:-len(number_text)]}{next_number:0{len(number_text)}d}"
    else:
        next_name = f"{name}_001"

    return f"{next_name}{ext}"



def get_next_available_filename(output_dir, filename):

    candidate = normalize_mp3_filename(filename)

    for _ in range(10000):
        output_file = os.path.join(output_dir, candidate)

        if not os.path.exists(output_file):
            return candidate

        candidate = increment_mp3_filename(candidate)

    raise RuntimeError("Cannot find an available MP3 filename.")
def get_output_file_path():

    output_dir = output_dir_entry.get().strip()

    if not output_dir:
        output_dir = DEFAULT_OUTPUT_DIR

    filename = normalize_mp3_filename(filename_entry.get())

    return os.path.join(output_dir, filename), output_dir, filename


def browse_output_dir():

    current_dir = output_dir_entry.get().strip() or DEFAULT_OUTPUT_DIR

    selected_dir = filedialog.askdirectory(initialdir=current_dir)

    if not selected_dir:
        return

    output_dir_entry.delete(0, tk.END)
    output_dir_entry.insert(0, selected_dir)

    next_filename = get_next_available_filename(selected_dir, filename_entry.get())
    filename_entry.delete(0, tk.END)
    filename_entry.insert(0, next_filename)

def format_log_line(output_filename, text):

    clean_text = " ".join(text.split())

    return f"{output_filename}\t{clean_text}\n"


def append_text_logs(output_dir, output_filename, vietnamese_text, english_text):

    vietnam_path = os.path.join(output_dir, "vietnam.txt")
    english_path = os.path.join(output_dir, "english.txt")

    with open(vietnam_path, "a", encoding="utf-8") as vietnam_file:
        vietnam_file.write(format_log_line(output_filename, vietnamese_text))

    with open(english_path, "a", encoding="utf-8") as english_file:
        english_file.write(format_log_line(output_filename, english_text))

# ====================================
# GENERATE TTS
# ====================================
async def generate_tts(text, voice, output_file, rate):

    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate
    )

    await communicate.save(output_file)

# ====================================
# RUN TTS
# ====================================
def run_tts():

    vietnamese_text = text_input.get("1.0", tk.END).strip()

    if not vietnamese_text:
        messagebox.showerror(
            "Error",
            "Please enter Vietnamese text."
        )
        return

    selected_voice = voice_combo.get()

    if not selected_voice:
        messagebox.showerror(
            "Error",
            "Please select voice."
        )
        return

    model = ollama_model_entry.get().strip()
    api_url = ollama_url_entry.get().strip()

    if not model:
        messagebox.showerror(
            "Error",
            "Please enter an Ollama model name."
        )
        return

    if not api_url:
        messagebox.showerror(
            "Error",
            "Please enter an Ollama API URL."
        )
        return

    voice = get_selected_voice_name()

    output_file, output_dir, output_filename = get_output_file_path()

    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        messagebox.showerror(
            "Error",
            f"Cannot create output folder: {e}"
        )
        return

    if os.path.exists(output_file):
        overwrite = messagebox.askyesno(
            "Overwrite MP3?",
            f"The file already exists:\n{output_file}\n\nDo you want to overwrite it?"
        )

        if not overwrite:
            return

    speed = speed_slider.get()

    rate = f"{speed:+d}%"

    set_busy(True, "Translating Vietnamese to English with Ollama...")

    async def process():

        try:

            english_text = translate_to_english_with_ollama(
                vietnamese_text,
                model,
                api_url
            )

            root.after(
                0,
                lambda: set_output_text(english_text)
            )

            root.after(
                0,
                lambda: status_label.config(text="Generating MP3 with Edge TTS...")
            )

            await generate_tts(
                english_text,
                voice,
                output_file,
                rate
            )

            append_text_logs(
                output_dir,
                output_filename,
                vietnamese_text,
                english_text
            )

            save_app_settings()

            root.after(
                0,
                lambda: status_label.config(
                    text=f"Saved: {output_file}"
                )
            )

            root.after(
                0,
                lambda: set_next_output_filename(output_filename)
            )

            root.after(
                0,
                lambda: messagebox.showinfo(
                    "Success",
                    "English MP3 generated successfully!"
                )
            )

        except Exception as e:

            root.after(
                0,
                lambda: messagebox.showerror(
                    "Error",
                    str(e)
                )
            )

            root.after(
                0,
                lambda: status_label.config(
                    text="Error"
                )
            )

        finally:
            root.after(0, lambda: set_busy(False))

    asyncio.run(process())

# ====================================
# UI HELPERS
# ====================================
def set_output_text(text):
    english_output.config(state=tk.NORMAL)
    english_output.delete("1.0", tk.END)
    english_output.insert(tk.END, text)
    english_output.config(state=tk.DISABLED)


def set_next_output_filename(current_filename):
    output_dir = output_dir_entry.get().strip() or DEFAULT_OUTPUT_DIR
    next_filename = get_next_available_filename(
        output_dir,
        increment_mp3_filename(current_filename)
    )

    filename_entry.delete(0, tk.END)
    filename_entry.insert(0, next_filename)


def set_busy(is_busy, status_text=None):
    state = tk.DISABLED if is_busy else tk.NORMAL
    generate_btn.config(state=state)

    if status_text:
        status_label.config(text=status_text)

# ====================================
# START THREAD
# ====================================
def start_thread():
    threading.Thread(target=run_tts, daemon=True).start()


def close_app():

    try:
        save_app_settings()
    except Exception:
        pass

    root.destroy()

# ====================================
# GUI
# ====================================
app_settings = load_app_settings()

root = tk.Tk()

root.title("Vietnamese to English Edge TTS")

root.protocol("WM_DELETE_WINDOW", close_app)

root.geometry("1000x850")

# ====================================
# TITLE
# ====================================
title_label = tk.Label(
    root,
    text="Vietnamese to English MP3 Generator",
    font=("Arial", 22, "bold")
)

title_label.pack(pady=10)

# ====================================
# OLLAMA FRAME
# ====================================
ollama_frame = tk.LabelFrame(root, text="Ollama")

ollama_frame.pack(padx=10, pady=5, fill=tk.X)

# MODEL
tk.Label(
    ollama_frame,
    text="Model:"
).grid(row=0, column=0, padx=5, pady=8, sticky="w")

ollama_model_entry = tk.Entry(
    ollama_frame,
    width=24
)

ollama_model_entry.insert(0, DEFAULT_OLLAMA_MODEL)

ollama_model_entry.grid(row=0, column=1, padx=5, pady=8, sticky="w")

# API URL
tk.Label(
    ollama_frame,
    text="API URL:"
).grid(row=0, column=2, padx=5, pady=8, sticky="w")

ollama_url_entry = tk.Entry(
    ollama_frame,
    width=48
)

ollama_url_entry.insert(0, DEFAULT_OLLAMA_URL)

ollama_url_entry.grid(row=0, column=3, padx=5, pady=8, sticky="we")

ollama_frame.columnconfigure(3, weight=1)

# ====================================
# FILTER FRAME
# ====================================
filter_frame = tk.Frame(root)

filter_frame.pack(pady=10)

# LANGUAGE
tk.Label(
    filter_frame,
    text="Language:"
).grid(row=0, column=0, padx=5)

language_combo = ttk.Combobox(
    filter_frame,
    width=12
)

language_combo.grid(row=0, column=1, padx=5)

language_combo.bind(
    "<<ComboboxSelected>>",
    update_voice_list
)

# COUNTRY
tk.Label(
    filter_frame,
    text="Country:"
).grid(row=0, column=2, padx=5)

country_combo = ttk.Combobox(
    filter_frame,
    width=12
)

country_combo.grid(row=0, column=3, padx=5)

country_combo.bind(
    "<<ComboboxSelected>>",
    update_voice_list
)

# GENDER
tk.Label(
    filter_frame,
    text="Gender:"
).grid(row=0, column=4, padx=5)

gender_combo = ttk.Combobox(
    filter_frame,
    width=12
)

gender_combo.grid(row=0, column=5, padx=5)

gender_combo.bind(
    "<<ComboboxSelected>>",
    update_voice_list
)

# ====================================
# SEARCH
# ====================================
search_frame = tk.Frame(root)

search_frame.pack(pady=5)

tk.Label(
    search_frame,
    text="Search Voice:"
).pack(side=tk.LEFT, padx=5)

search_entry = tk.Entry(
    search_frame,
    width=40
)

search_entry.pack(side=tk.LEFT)

search_entry.bind(
    "<KeyRelease>",
    update_voice_list
)

# ====================================
# VOICE SELECT
# ====================================
voice_frame = tk.Frame(root)

voice_frame.pack(pady=10)

tk.Label(
    voice_frame,
    text="Voice:"
).pack(side=tk.LEFT, padx=5)

voice_combo = ttk.Combobox(
    voice_frame,
    width=80
)

voice_combo.pack(side=tk.LEFT)

# ====================================
# SPEED
# ====================================
speed_frame = tk.Frame(root)

speed_frame.pack(pady=10)

tk.Label(
    speed_frame,
    text="Speed:"
).pack(side=tk.LEFT, padx=5)

speed_slider = tk.Scale(
    speed_frame,
    from_=-50,
    to=100,
    orient=tk.HORIZONTAL,
    length=300
)

speed_slider.set(DEFAULT_SPEED)

speed_slider.pack(side=tk.LEFT)

# ====================================
# OUTPUT FILE
# ====================================
output_frame = tk.LabelFrame(root, text="Output MP3")

output_frame.pack(padx=10, pady=5, fill=tk.X)

# OUTPUT DIRECTORY
tk.Label(
    output_frame,
    text="Save folder:"
).grid(row=0, column=0, padx=5, pady=8, sticky="w")

output_dir_entry = tk.Entry(
    output_frame,
    width=70
)

output_dir_entry.insert(0, DEFAULT_OUTPUT_DIR)

output_dir_entry.grid(row=0, column=1, padx=5, pady=8, sticky="we")

browse_btn = tk.Button(
    output_frame,
    text="Browse",
    command=browse_output_dir
)

browse_btn.grid(row=0, column=2, padx=5, pady=8)

# OUTPUT FILENAME
tk.Label(
    output_frame,
    text="File name:"
).grid(row=1, column=0, padx=5, pady=8, sticky="w")

filename_entry = tk.Entry(
    output_frame,
    width=40
)

filename_entry.insert(
    0,
    get_next_available_filename(DEFAULT_OUTPUT_DIR, DEFAULT_OUTPUT_FILENAME)
)

filename_entry.grid(row=1, column=1, padx=5, pady=8, sticky="w")

output_frame.columnconfigure(1, weight=1)

# ====================================
# TEXT INPUT
# ====================================
tk.Label(
    root,
    text="Vietnamese input:"
).pack(anchor="w", padx=10)

text_input = tk.Text(
    root,
    wrap=tk.WORD,
    font=("Arial", 12),
    height=8
)

text_input.pack(
    padx=10,
    pady=(3, 10),
    fill=tk.BOTH,
    expand=True
)

text_input.insert(
    tk.END,
    "Xin chào mọi người! Đây là một ứng dụng chuyển đổi văn bản tiếng Việt sang tiếng Anh và tạo file MP3 bằng Edge TTS. Hãy nhập văn bản tiếng Việt vào đây, chọn giọng nói và tốc độ, sau đó nhấn nút để tạo file MP3 tiếng Anh nhé!"
)

# ====================================
# ENGLISH OUTPUT
# ====================================
tk.Label(
    root,
    text="English output from Ollama:"
).pack(anchor="w", padx=10)

english_output = tk.Text(
    root,
    wrap=tk.WORD,
    font=("Arial", 12),
    height=6,
    state=tk.DISABLED
)

english_output.pack(
    padx=10,
    pady=(3, 10),
    fill=tk.BOTH,
    expand=True
)

# ====================================
# BUTTON
# ====================================
generate_btn = tk.Button(
    root,
    text="Generate English MP3",
    font=("Arial", 16),
    bg="#4CAF50",
    fg="white",
    padx=20,
    pady=10,
    command=start_thread
)

generate_btn.pack(pady=10)

# ====================================
# STATUS
# ====================================
status_label = tk.Label(
    root,
    text="Loading voices...",
    fg="blue",
    font=("Arial", 11)
)

status_label.pack(pady=5)

# ====================================
# LOAD VOICES
# ====================================
asyncio.run(load_voices())

apply_app_settings()

try:
    save_app_settings()
except Exception:
    pass

status_label.config(text="Ready")

# ====================================
# START GUI
# ====================================
root.mainloop()
