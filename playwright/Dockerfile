FROM node:20-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11vnc \
    novnc \
    websockify \
    python3 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package.json ./
RUN npm install && npx playwright install chromium --with-deps

COPY . .

EXPOSE 6080 5900

CMD ["sh", "-c", "\
Xvfb :99 -screen 0 1920x1080x24 & \
sleep 2 && \
x11vnc -display :99 -nopw -forever -shared -rfbport 5900 & \
sleep 2 && \
cd /usr/share/novnc && python3 -m http.server 6080 & \
websockify --idle-timeout=3600 9222 localhost:5900 & \
sleep 2 && \
echo 'noVNC ready at http://localhost:6080/vnc.html?host=localhost&port=9222' && \
tail -f /dev/null"]