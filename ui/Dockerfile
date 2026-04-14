FROM nginx:alpine

COPY . /usr/share/nginx/html

RUN cat > /etc/nginx/conf.d/default.conf << 'EOF'
resolver 127.0.0.11 valid=10s ipv6=off;

upstream ocr_api {
    server tms-ocr-api:9000;
}

upstream tms_api {
    server tms-api:9001;
}

server {
    listen 80;
    server_name localhost;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/v1/ {
        client_max_body_size 100M;
        proxy_pass http://ocr_api/api/v1/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_buffering off;
        proxy_cache off;
    }

    location /api/ {
        proxy_pass http://tms_api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_buffering off;
        proxy_cache off;
    }
}
EOF

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
