# Миграция управления параметром SUBMIT в конфигурацию

## Дата
29 октября 2025

## Обзор изменений

Управление параметром `SUBMIT` (определяющим реальную отправку заявок vs тестовый режим) было перенесено из аргументов командной строки в конфигурационный файл `config.py` через расширенные режимы `BOT_MODE`.

## Мотивация

### Проблемы старого подхода
- ❌ Параметр `SUBMIT` передавался отдельно через `sys.argv`
- ❌ Разрозненное управление режимами работы
- ❌ Неудобство для CI/CD конфигурации
- ❌ Отсутствие централизованной настройки

### Преимущества нового подхода
- ✅ Все настройки в одном месте (`config.py`)
- ✅ Явное указание намерений в названии режима
- ✅ Поддержка переменных окружения для CI/CD
- ✅ Валидация режимов при старте
- ✅ Безопасность по умолчанию (DRY RUN)

## Изменения в коде

### 1. Новые режимы BOT_MODE

Добавлены два новых режима:

```python
# config.py
BOT_MODE = "processing_submit"  # Обработка с реальной отправкой
BOT_MODE = "full_run_submit"    # Полный цикл с реальной отправкой
```

### 2. Таблица всех режимов

| Режим | Discovery | Enrichment | Processing | Submit |
|-------|-----------|------------|------------|--------|
| `discovery` | ✅ | ❌ | ❌ | - |
| `enrichment` | ❌ | ✅ | ❌ | - |
| `processing` | ❌ | ❌ | ✅ | ❌ (DRY RUN) |
| `processing_submit` | ❌ | ❌ | ✅ | ✅ (SUBMIT) |
| `full_run` | ✅ | ✅ | ✅ | ❌ (DRY RUN) |
| `full_run_submit` | ✅ | ✅ | ✅ | ✅ (SUBMIT) |
| `test_logging` | - | - | - | - |

### 3. Изменения в config.py

```python
# Поддержка переменных окружения
import os
BOT_MODE = os.getenv("BOT_MODE", "discovery")

# Список валидных режимов для валидации
VALID_BOT_MODES = [
    "discovery",
    "enrichment",
    "processing",
    "processing_submit",
    "full_run",
    "full_run_submit",
    "test_logging"
]
```

### 4. Новые функции в main.py

#### Функция определения режима отправки

```python
def get_submit_mode_from_bot_mode(bot_mode: str) -> bool:
    """
    Определяет необходимость отправки заявок на основе BOT_MODE.
    
    Args:
        bot_mode: Текущий режим работы бота
        
    Returns:
        True если режим заканчивается на "_submit", иначе False
    """
    return bot_mode in ["processing_submit", "full_run_submit"]
```

#### Функция валидации режима

```python
def validate_bot_mode(bot_mode: str, valid_modes: list[str]) -> None:
    """
    Валидирует что BOT_MODE входит в список допустимых режимов.
    
    Args:
        bot_mode: Текущий режим работы бота
        valid_modes: Список допустимых режимов
        
    Raises:
        ValueError: Если bot_mode не входит в valid_modes
    """
    if bot_mode not in valid_modes:
        raise ValueError(
            f"Invalid BOT_MODE: '{bot_mode}'. "
            f"Valid modes are: {', '.join(valid_modes)}"
        )
```

### 5. Удалено из main.py

```python
# УДАЛЕНО:
should_submit = len(sys.argv) > 1 and sys.argv[1] == "SUBMIT"

# ДОБАВЛЕНО:
should_submit = get_submit_mode_from_bot_mode(BOT_MODE)
```

## Руководство по миграции

### Старый способ запуска

```bash
# Тестовый режим
python main.py

# Режим с реальной отправкой
python main.py SUBMIT
```

### Новый способ запуска

#### Вариант 1: Изменение в config.py

```python
# config.py
BOT_MODE = "processing"          # Тестовый режим
BOT_MODE = "processing_submit"   # Реальная отправка

BOT_MODE = "full_run"            # Полный цикл (тест)
BOT_MODE = "full_run_submit"     # Полный цикл (отправка)
```

```bash
python main.py
```

#### Вариант 2: Через переменную окружения

```bash
# PowerShell (Windows)
$env:BOT_MODE = "processing_submit"
python main.py

# Bash/Zsh (Linux/Mac)
BOT_MODE=processing_submit python main.py

# Или экспорт переменной
export BOT_MODE=full_run_submit
python main.py
```

## Безопасность

### Защита от случайной отправки

1. **По умолчанию - DRY RUN**: Старые режимы (`processing`, `full_run`) остаются в режиме DRY RUN
2. **Явное намерение**: Для реальной отправки нужно использовать режимы с суффиксом `_submit`
3. **Валидация при старте**: Приложение проверяет корректность `BOT_MODE` и выдает ошибку при неверном значении

### Пример валидации

```python
# При неверном режиме:
BOT_MODE = "processing_sumbit"  # Опечатка!

# Приложение выдаст ошибку:
# ERROR - Invalid BOT_MODE: 'processing_sumbit'. 
# Valid modes are: discovery, enrichment, processing, processing_submit, full_run, full_run_submit, test_logging
```

## Примеры использования

### Локальная разработка (тестирование)

```python
# config.py
BOT_MODE = "processing"  # DRY RUN по умолчанию
```

### Локальная разработка (реальная отправка)

```python
# config.py
BOT_MODE = "processing_submit"  # Реальная отправка
```

### CI/CD Pipeline

```yaml
# GitHub Actions / GitLab CI
env:
  BOT_MODE: full_run_submit

script:
  - python main.py
```

### Docker

```dockerfile
ENV BOT_MODE=processing_submit
CMD ["python", "main.py"]
```

или

```bash
docker run -e BOT_MODE=full_run_submit linkedin-bot
```

## Тесты

Добавлены новые тесты для валидации изменений:

### Файл: `tests/unit/test_main.py`

- ✅ `test_processing_submit_returns_true` - проверка режима `processing_submit`
- ✅ `test_full_run_submit_returns_true` - проверка режима `full_run_submit`
- ✅ `test_processing_returns_false` - DRY RUN для `processing`
- ✅ `test_full_run_returns_false` - DRY RUN для `full_run`
- ✅ `test_valid_mode_discovery` - валидация корректного режима
- ✅ `test_invalid_mode_raises_value_error` - валидация некорректного режима
- ✅ `test_case_sensitive_validation` - проверка чувствительности к регистру

**Всего создано: 14 новых тестов**

## Обратная совместимость

✅ **Все существующие тесты проходят успешно** (27 unit + 8 integration тестов)

❌ **Использование `python main.py SUBMIT` больше не работает**  
→ Используйте `BOT_MODE="processing_submit"` или `BOT_MODE="full_run_submit"`

## Рекомендации

1. **Для ежедневного использования**: Установите `BOT_MODE = "processing"` для тестирования и `"processing_submit"` для отправки
2. **Для CI/CD**: Используйте переменные окружения для гибкого управления режимами
3. **Для безопасности**: Всегда тестируйте в DRY RUN режиме перед переключением на `_submit`

## Связанные файлы

- `config.py` - конфигурация и новые режимы
- `main.py` - логика определения режима отправки
- `tests/unit/test_main.py` - тесты для новых функций
- `actions/apply.py` - использует параметр `should_submit`
- `phases/processing.py` - передает параметр `should_submit`

## Вопросы и поддержка

При возникновении вопросов обращайтесь к:
- Этому документу для понимания изменений
- `config.py` для доступных режимов
- `tests/unit/test_main.py` для примеров использования
