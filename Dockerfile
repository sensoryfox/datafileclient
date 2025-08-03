# Dockerfile для основного сервиса (например, search-api)

# --- Этап 1: Сборщик зависимостей (Builder) ---
# Используем полную версию Python для установки зависимостей, включая те, что могут требовать компиляции
FROM python:3.11 as builder

WORKDIR /app

# Устанавливаем Poetry или просто используем pip
# Предположим, у нас есть pyproject.toml или requirements.txt
COPY pyproject.toml poetry.lock* ./
# Либо COPY requirements.txt ./

# Устанавливаем зависимости в отдельную директорию, это ускоряет пересборку
# На этом этапе будет установлена и наша библиотека data-client!
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt # или poetry install

# --- Этап 2: Финальный образ (Final) ---
# Используем легковесный образ для продакшена
FROM python:3.11-slim

WORKDIR /app

# Копируем только установленные зависимости из сборщика
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Копируем исходный код нашего FastAPI приложения
COPY ./src /app/src

# Создаем пользователя без root-прав для безопасности
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

# Команда для запуска нашего FastAPI приложения
# Обратите внимание, что хост 0.0.0.0 обязателен для доступа к контейнеру извне
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]