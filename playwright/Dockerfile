FROM node:20-alpine

RUN apk update && apk add --no-cache \
    chromium \
    chromium-chromedriver \
    nss \
    freetype \
    harfbuzz \
    ca-certificates \
    ttf-freefont \
    udev \
    novnc \
    websockify \
    tigervnc \
    tigervnc-doc \
    xvfb \
    python3

ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=1
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium-browser
ENV DISPLAY=:99

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 6080 5900

CMD ["sh", "-c", "\
Xvfb :99 -geometry 1920x1080 -depth 24 &>/dev/null; \
vncconfig -display :99 &>/dev/null; \
chromium --headless --no-sandbox --disable-gpu --remote-debugging-port=9222 &>/dev/null & \
sleep 2 && \
cd /usr/share/novnc && python3 -m http.server 6080 &>/dev/null & \
websockify --idle-timeout=3600 5900 localhost:5999 &>/dev/null & \
sleep 2 && \
echo 'noVNC ready at http://localhost:6080/vnc.html?host=localhost&port=5900' && \
tail -f /dev/null"]