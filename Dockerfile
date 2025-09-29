# Используем официальный образ Python с Debian Bookworm
FROM python:3.11-slim-bookworm

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Устанавливаем системные зависимости, такие как tzdata для настройки часового пояса
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем часовой пояс, как указано в settings.py
ENV TZ="Europe/Kiev"
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Копируем файл requirements.txt и устанавливаем Python-зависимости.
# Это позволяет Docker кэшировать этот слой, если требования не меняются.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь остальной код приложения в рабочую директорию контейнера.
COPY . .

# Определяем команду, которая будет выполнена при запуске контейнера.
# Исправленный путь к initialize.py: scripts/setup_sheets.py
CMD ["sh", "-c", "python scripts/setup_sheets.py && python main.py"]