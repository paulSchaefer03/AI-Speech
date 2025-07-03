# run.py
import subprocess
import uvicorn
import threading
import time
import os

def run_frontend():
    frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
    subprocess.Popen(["npm", "run", "dev"], cwd=frontend_dir)

def run_backend():
    uvicorn.run("backend.main:app", host="0.0.0.0", port=7860, reload=True)

if __name__ == "__main__":
    t = threading.Thread(target=run_frontend)
    t.start()

    # Optional: Warten, damit der Frontend-Server zuerst startet
    time.sleep(2)
    subprocess.Popen(["caddy", "run"])
    run_backend()
