FROM nginx:1.25-alpine

# Удаляем дефолтный конфиг Nginx и подставляем свой
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d