FROM python:3.10-slim

# Install system dependencies for GUI environments and browser streaming
RUN apt-get update && apt-get install -y \
    xvfb x11vnc python3-tk novnc websockify \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt

# THE FIX: Create a shortcut copy of vnc.html named index.html so the server loads it automatically
RUN cp /usr/share/novnc/vnc.html /usr/share/novnc/index.html

# Render assigns a random port dynamically via the $PORT variable
CMD Xvfb :99 -screen 0 1024x768x16 & \
    sleep 2 && \
    x11vnc -display :99 -nopw -forever -shared & \
    websockify --web=/usr/share/novnc $PORT localhost:5900 & \
    export DISPLAY=:99 && \
    python app.py
