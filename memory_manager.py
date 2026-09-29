import json
import os

MEMORY_FILE = "aris_memory.json"

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        default_memory = {
            "boss_profile": {
                "name": "Priyangshu",
                "role": "Lead of ElectroVista",
                "university": "MIT Bengaluru",
                "interests": ["F1", "Drones", "ECE", "Assassin's Creed"]
            },
            "recent_tasks": [],
            "learned_facts": {}
        }
        with open(MEMORY_FILE, 'w') as f:
            json.dump(default_memory, f, indent=4)
        return default_memory
    
    try:
        with open(MEMORY_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"boss_profile": {"name": "Priyangshu", "role": "User", "university": "N/A"}, "learned_facts": {}}

def update_memory(category, key, value):
    memory = load_memory()
    if category not in memory: memory[category] = {}
    memory[category][key] = value
    with open(MEMORY_FILE, 'w') as f:
        json.dump(memory, f, indent=4)
    return f"Memory Bank updated: {key} saved."