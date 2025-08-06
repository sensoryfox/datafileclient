# upload.py
import os
import subprocess
import sys
from pathlib import Path

# --- КОНФИГУРАЦИЯ ---
# Вставьте сюда ваши данные.
# ВНИМАНИЕ: Это небезопасно, если вы используете Git.
PROXY_URL = "http://azyQZx:VTDf5S@170.244.95.14:9310"
PYPI_TOKEN = os.environ['PYPI_API_TOKEN'] 
DIST_DIR = "dist"
# --- КОНЕЦ КОНФИГУРАЦИИ ---


def main():
    """
    Скрипт для сборки и загрузки дистрибутива на PyPI через прокси.
    """
    project_root = Path(__file__).parent
    dist_path = project_root / DIST_DIR

    # 1. Проверка, что дистрибутивы существуют
    if not dist_path.exists() or not any(dist_path.iterdir()):
        print(f"❌ Папка '{DIST_DIR}' не найдена или пуста.")
        print("💡 Сначала соберите пакет командой: python -m build")
        sys.exit(1)

    print("📦 Найдены дистрибутивы для загрузки.")

    # 2. Настройка окружения с прокси
    # Создаем копию текущих переменных окружения и добавляем наши прокси
    proxy_env = os.environ.copy()
    proxy_env["HTTP_PROXY"] = PROXY_URL
    proxy_env["HTTPS_PROXY"] = PROXY_URL
    print(f"🔧 Настроен прокси: {PROXY_URL}")

    # 3. Формирование и выполнение команды twine
    # Используем sys.executable для вызова pip из того же окружения
    # Передаем токен через аргумент -p, чтобы он не отображался в логах процессов
    command = [
        sys.executable,
        "-m",
        "twine",
        "upload",
        "--username",
        "__token__",  # Имя пользователя для токена PyPI
        "--password",
        PYPI_TOKEN,
        str(dist_path / "*"),  # Путь к файлам для загрузки
    ]

    print("\n🚀 Запускаю загрузку на PyPI...")
    try:
        # Запускаем twine как дочерний процесс с настроенным окружением
        result = subprocess.run(
            command,
            env=proxy_env,
            check=True,  # Вызовет исключение, если twine завершится с ошибкой
            capture_output=True,  # Перехватываем вывод
            text=True,  # Декодируем вывод в текст
        )
        print("✅ Успешно загружено!")
        print("\n--- Вывод Twine ---")
        print(result.stdout)
        print("--------------------")

    except subprocess.CalledProcessError as e:
        print("\n❌ ОШИБКА: Загрузка не удалась.")
        print(f"Код возврата: {e.returncode}")
        print("\n--- STDOUT ---")
        print(e.stdout)
        print("\n--- STDERR ---")
        print(e.stderr)
        print("--------------")
        sys.exit(1)
    except FileNotFoundError:
        print("❌ ОШИБКА: Команда 'twine' не найдена.")
        print("💡 Убедитесь, что twine установлен: pip install twine")
        sys.exit(1)


if __name__ == "__main__":
    main()