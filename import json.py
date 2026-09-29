import json
import os

MEMORY_FILE = "aris_memory.json"

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        # Initializing with your profile context
        default_memory = {
            "boss_profile": {
                "name": "Priyangshu",
                "role": "Lead of ElectroVista, Lead of Office of Alumni Relations, F1 Enthusiast",
                "university": "MIT Bengaluru",
                "interests": ["F1", "Drones", "ECE", "Assassin's Creed"]
            },
            "recent_tasks": [],
            "learned_facts": {}
        }
        with open(MEMORY_FILE, 'w') as f:
            json.dump(default_memory, f, indent=4)
        return default_memory
    
    with open(MEMORY_FILE, 'r') as f:
        return json.load(f)

def update_memory(category, key, value):
    memory = load_memory()
    if category not in memory:
        memory[category] = {}
    memory[category][key] = value
    with open(MEMORY_FILE, 'w') as f:
        json.dump(memory, f, indent=4)
    return f"Memory Updated: {key} saved to {category}."