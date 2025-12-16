# Используем официальный облегченный образ Python
FROM python:3.11-slim

# Отключает создание .pyc файлов
# В контейнере код не меняется, поэтому кэширование байт-кода только зря тратит время и место
ENV PYTHONDONTWRITEBYTECODE 1
# Отключает буферизацию стандартного вывода
# Гарантирует, что логи приложения попадут в Docker-консоль мгновенно, а не застрянут в буфере памяти
ENV PYTHONUNBUFFERED 1

# Явно указываем путь к npm для корректной работы django-tailwind
ENV NPM_BIN_PATH /usr/bin/npm

# Устанавливаем рабочую директорию
WORKDIR /app

# --- СИСТЕМНЫЕ ЗАВИСИМОСТИ ---
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    libpq-dev \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# --- ЗАВИСИМОСТИ PYTHON ---
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# --- ЗАВИСИМОСТИ NODE.JS ---
# Копируем ТОЛЬКО файлы описания зависимостей фронтенда
# Это позволяет Docker закэшировать папку node_modules
COPY tailwind_config/static_src/package.json tailwind_config/static_src/package-lock.json* /app/tailwind_config/static_src/

WORKDIR /app/tailwind_config/static_src
RUN npm install
# Даем права на исполнение бинарных файлов
RUN chmod +x node_modules/.bin/*

WORKDIR /app
# -------------------------

COPY . /app/

# --- ЗАПУСК ---
COPY entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]