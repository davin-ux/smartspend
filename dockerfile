FROM python:3.10-slim

# Install system dependencies for GUI environments and browser streaming
RUN apt-get update && apt-get install -y \
    xvfb x11vnc python3-tk novnc websockify \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt

# Explicitly assign the DISPLAY variable globally
ENV DISPLAY=:99

# The command runs the virtual window buffer first, configures VNC, 
# then boots your python app, giving each stage time to breathe.
CMD Xvfb :99 -screen 0 1024x768x16 & \
    sleep 3 && \
    x11vnc -display :99 -nopw -forever -shared -bg & \
    sleep 3 && \
    websockify --web=/usr/share/novnc $PORT localhost:5900 --web-base=/vnc.html & \
    sleep 2 && \
    python app.py
