#!/bin/bash
set -e

echo "📦 Собираем статику..."
python manage.py collectstatic --noinput

echo "🔄 Применяем миграции..."
python manage.py migrate --noinput

echo "🔍 Проверяем Redis..."
python manage.py shell -c "from django.core.cache import cache; cache.set('check', 1); print('✅ Redis OK')" || echo "⚠️ Redis недоступен"

echo "✅ Инициализация завершена. Запускаем приложение..."

# Передаём управление команде из docker-compose
exec "$@"