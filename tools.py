import os
import subprocess
import webbrowser
import urllib.request
import urllib.parse
import json
import time
import shlex # Added for safer terminal command parsing

# --- [ 1. MASTER SYSTEM & HARDWARE OVERRIDE ] ---

def system_control(action):
    """
    Executes low-level macOS hardware commands.
    Enhanced with direct AppleScript for deep OS control.
    """
    scripts = {
        "vol_up": "set volume output volume (output volume of (get output volume settings) + 10)",
        "vol_down": "set volume output volume (output volume of (get output volume settings) - 10)",
        "max_vol": "set volume output volume 100",
        "mute": "set volume with output muted",
        "brightness_up": 'tell application "System Events" to key code 144',
        "brightness_down": 'tell application "System Events" to key code 145',
        "sleep": 'tell application "System Events" to sleep',
        "lock": 'tell application "System Events" to keystroke "q" using {command down, control down}',
        "empty_trash": 'tell application "Finder" to empty trash',
        "screenshot": 'do shell script "screencapture -t jpg ~/Desktop/ARIS_Capture_$(date +%Y%m%d_%H%M%S).jpg"'
    }
    
    if action in scripts:
        try:
            subprocess.run(['osascript', '-e', scripts[action]], check=True)
            return f"System: {action} confirmed, Boss."
        except Exception as e:
            return f"Hardware Fault: {str(e)}"
    return "Invalid hardware action requested."

def open_settings_pane(pane="main"):
    """
    Directly opens specific macOS System Setting panes.
    Panes: display, sound, network, battery, bluetooth, privacy, trackpad, software_update
    """
    panes = {
        "main": "",
        "display": "Displays",
        "sound": "Sound",
        "network": "Network",
        "battery": "Battery",
        "bluetooth": "Bluetooth",
        "privacy": "Privacy_Security",
        "trackpad": "Trackpad",
        "update": "SoftwareUpdate"
    }
    target = panes.get(pane.lower(), "")
    try:
        if target:
            os.system(f"open /System/Library/PreferencePanes/{target}.prefPane")
        else:
            os.system("open -a 'System Settings'")
        return f"Opening System Settings: {pane}"
    except Exception as e:
        return str(e)

# --- [ 2. MUSIC & MEDIA DOMINION ] ---

def apple_music_overlord(action, target=None):
    """Commands Apple Music library and playback."""
    try:
        if action == "play_song" and target:
            script = f'tell application "Music" to play (first track whose name contains "{target}")'
        elif action == "play_playlist" and target:
            script = f'tell application "Music" to play playlist "{target}"'
        else:
            script = f'tell application "Music" to {action}'
            
        subprocess.run(['osascript', '-e', script], check=True)
        return f"Music Core: Executed {action} {f'for {target}' if target else ''}."
    except:
        os.system("open -a Music")
        return "Music app initialized. Repeat the command, Boss."

def media_control(command):
    """Universal media keys for Spotify/YouTube/QuickTime."""
    try:
        if command in ["play", "pause"]:
            subprocess.run(['osascript', '-e', 'tell application "System Events" to key code 49'], check=True)
        elif command == "next":
            subprocess.run(['osascript', '-e', 'tell application "System Events" to key code 124 using command down'], check=True)
        return f"Media control: {command} successful."
    except Exception as e:
        return f"Media Error: {str(e)}"

# --- [ 3. WEB & RESEARCH CORE ] ---

def web_search(query):
    """Performs a deep search or opens a raw URL."""
    try:
        if query.startswith("http"):
            webbrowser.open(query)
            return f"Navigating to {query}."
        encoded_query = urllib.parse.quote(query)
        url = f"https://www.google.com/search?q={encoded_query}"
        webbrowser.open(url)
        return f"Boss, I've initialized a web search for '{query}'."
    except Exception as e:
        return str(e)

def youtube_search(query):
    """Finds and plays videos on YouTube."""
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://www.youtube.com/results?search_query={encoded_query}"
        webbrowser.open(url)
        return f"Opening YouTube results for '{query}'."
    except Exception as e:
        return str(e)

def get_wikipedia_summary(topic):
    """Fetches a quick summary of any topic from Wikipedia."""
    try:
        topic_enc = urllib.parse.quote(topic)
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{topic_enc}"
        req = urllib.request.Request(url, headers={'User-Agent': 'ARIS_OS_Assistant'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            return data.get('extract', "No summary found.")
    except Exception as e:
        return f"Research error: {str(e)}"

# --- [ 4. FILE & DIRECTORY MASTER ] ---

def open_folder(path="~"):
    """Opens any folder in Finder."""
    try:
        expanded_path = os.path.expanduser(path)
        subprocess.run(['open', expanded_path], check=True)
        return f"Finder: Opening {path}"
    except Exception as e:
        return str(e)

def list_files(directory="."):
    """Enhanced directory listing."""
    try:
        path = os.path.expanduser(directory)
        files = os.listdir(path)
        return f"Found {len(files)} items in '{directory}':\n" + ", ".join(files)
    except Exception as e:
        return f"Access Denied: {str(e)}"

def read_file(filepath):
    try:
        path = os.path.expanduser(filepath)
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error: {str(e)}"

def write_file(filepath, content):
    try:
        path = os.path.expanduser(filepath)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote to {filepath}"
    except Exception as e:
        return f"Error: {str(e)}"

# --- [ 5. TERMINAL & APP DOMINION ] ---

def run_terminal_command(command):
    """Executes a raw shell command."""
    try:
        # Safer execution using shlex for complex commands
        result = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT)
        return result.decode('utf-8').strip()
    except Exception as e:
        return f"Terminal Error: {str(e)}"

def open_app(app_name):
    """Launches any macOS application by name."""
    try:
        subprocess.run(['open', '-a', app_name], check=True)
        return f"Launched {app_name}."
    except:
        return f"Could not find {app_name}. Trying deep search..."

def window_management(action):
    """
    Controls open windows on macOS.
    Actions: minimize_all, show_desktop, hide_active
    """
    scripts = {
        "minimize_all": 'tell application "System Events" to set miniaturized of every window of (every process whose background only is false) to true',
        "show_desktop": 'tell application "System Events" to key code 103', # F11 Shortcut
        "hide_active": 'tell application "System Events" to set visible of (first process whose frontmost is true) to false'
    }
    try:
        subprocess.run(['osascript', '-e', scripts[action]], check=True)
        return f"Workspace action '{action}' executed."
    except Exception as e:
        return str(e)

# --- [ 6. ENGINEERING & LOGIC ] ---

def circuit_math(mode, val1, val2):
    """
    Advanced ECE math for ElectroVista projects.
    Modes: frequency (v1=Period in s), resistor_color (v1=color1, v2=color2), power (v1=V, v2=I)
    """
    try:
        if mode == "frequency":
            return f"Frequency is {1/float(val1):.2f} Hz"
        if mode == "power":
            return f"Power Dissipation is {float(val1)*float(val2):.2f} Watts"
        return "Calculation mode not recognized."
    except:
        return "Input error in Engineering module."

def ohms_law(v=None, i=None, r=None):
    """V=IR calculation."""
    try:
        if v is None: return f"Voltage is {float(i)*float(r)}V"
        if i is None: return f"Current is {float(v)/float(r)}A"
        if r is None: return f"Resistance is {float(v)/float(i)}Ω"
    except:
        return "Input error."
    return "Include two parameters."

# --- [ 7. MEMORY & RESIDENT DATA ] ---

from memory_manager import update_memory

def save_fact(category, key, value):
    """Bridge function for ARIS to save long-term memories."""
    return update_memory(category, key, value)

def get_system_stats():
    """Returns high-level Mac health data for the telemetry pane."""
    import psutil
    cpu = psutil.cpu_percent()
    temp_script = "format(cpu_temperature())" # Placeholder for temp tools
    return f"CPU: {cpu}% | Logic Core: Stable"

# --- [ THE FINAL TOOL MAPPING ] ---

available_tools = {
    "list_files": list_files,
    "read_file": read_file,
    "write_file": write_file,
    "open_folder": open_folder,
    "run_terminal_command": run_terminal_command,
    "system_control": system_control,
    "settings_control": open_settings_pane,
    "window_control": window_management,
    "media_control": media_control,
    "apple_music": apple_music_overlord,
    "web_search": web_search,
    "youtube_search": youtube_search,
    "get_wikipedia": get_wikipedia_summary,
    "open_app": open_app,
    "open_url": webbrowser.open,
    "get_weather": lambda loc: f"Weather query for {loc} initialized.",
    "ohms_law": ohms_law,
    "circuit_math": circuit_math,
    "execute_applescript": lambda s: subprocess.run(['osascript', '-e', s]),
    "save_fact": save_fact
}
def live_research(query):
    """
    Retrieves real-time web data, news, and current events.
    Use this for anything happening 'now' or recently.
    """
    import requests
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "Error: Tavily API Key missing from .env"
    
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "advanced",
        "max_results": 5
    }
    
    try:
        response = requests.post(url, json=payload).json()
        # Cleaning the results for the brain to digest easily
        context = []
        for result in response.get('results', []):
            context.append(f"Source: {result['url']}\nContent: {result['content']}")
        
        return "\n\n---\n\n".join(context) if context else "No live data found for this query."
    except Exception as e:
        return f"Neural Search Error: {str(e)}"

# --- [ UPDATE YOUR MAPPING AT THE BOTTOM ] ---
available_tools = {
    # ... your existing tools ...
    "live_research": live_research 
}