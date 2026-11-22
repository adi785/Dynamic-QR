import os

# Render dynamic port binding
port = os.environ.get("PORT", "5000")
bind = f"0.0.0.0:{port}"

# Free tier concurrency (single worker with lightweight threads)
# Keeps RAM usage < 150MB, preventing OOM SIGKILL on Render 512MB limits
workers = 1
threads = 4
timeout = 120
preload_app = False
