# Оптимизация производительности

**Статус:** ✅ Реализовано и протестировано

## Обзор

LinkedIn Easy Apply Bot был оптимизирован для значительно более быстрой работы благодаря следующим улучшениям:

### Основные оптимизации

1. **Параллельное ожидание селекторов** - Вместо последовательной проверки множества селекторов используется параллельная проверка через `wait_for_any_selector()`

2. **Event-driven подход** - Замена активного polling на event-driven ожидание элементов страницы

3. **Оптимизированные таймауты** - Сокращение избыточных таймаутов без потери надёжности

## Новые утилиты

### `core/utils.py`

#### `wait_for_selector_parallel()`
Параллельное ожидание появления любого из списка селекторов:

```python
from core.utils import wait_for_selector_parallel

result = await wait_for_selector_parallel(
    page,
    ["div.job-list", "ul.jobs", "div.no-results"],
    timeout=5000
)

if result:
    selector, element = result
    print(f"Found element: {selector}")
```

**Преимущества:**
- В 2-5 раз быстрее чем `wait_for_load_state("networkidle")`
- Проверяет все селекторы параллельно
- Возвращается сразу при первом совпадении

#### `wait_for_selector_with_event()`
Event-driven ожидание селектора для оптимизации производительности:

```python
from core.utils import wait_for_selector_with_event

element = await wait_for_selector_with_event(
    page,
    "div.content",
    timeout=5000
)
```

## Настройки производительности

### `config.py`

```python
# Оптимизированные таймауты для баланса между скоростью и надёжностью
SELECTOR_WAIT_TIMEOUT = 5000  # 5 секунд для ожидания элементов
PAGE_LOAD_TIMEOUT = 10000     # 10 секунд для загрузки страниц
```

## Best Practices

### ✅ Используйте:

1. **`wait_for_selector_parallel()` вместо `wait_for_load_state()`**
   ```python
   # Плохо
   await page.wait_for_load_state("networkidle")
   
   # Хорошо
   await wait_for_selector_parallel(page, ["div.content", "div.error"])
   ```

2. **Параллельные проверки для альтернативных структур DOM**
   ```python
   result = await wait_for_selector_parallel(
       page,
       ["div.modern-layout", "div.legacy-layout", "div.mobile-layout"]
   )
   ```

3. **Короткие таймауты для быстрых операций**
   ```python
   result = await wait_for_selector_parallel(page, selectors, timeout=3000)
   ```

### ❌ Избегайте:

1. **`wait_for_load_state("networkidle")` - очень медленно**
2. **Последовательной проверки множества селекторов**
3. **Активного ожидания с `wait_for_timeout()`**

## Resilience и Retry-логика

### `core/resilience.py`

Модуль обеспечивает устойчивость операций:

- **Retry-логика** (`tenacity`): Автоматические повторные попытки при временных ошибках
- **Circuit Breakers** (`pybreaker`): Предотвращение каскадных сбоев
- **Graceful degradation**: Переход на резервные механизмы при сбоях

## Мониторинг

### `core/metrics.py`

Модуль для сбора метрик производительности:

- Сбор метрик времени выполнения операций
- Подсчёт событий и ошибок
- Агрегация статистики по операциям

## Тестирование

Все оптимизации покрыты unit-тестами:

```bash
# Тестировать утилиты производительности
uv run pytest tests/unit/core/test_utils.py -v

# Тестировать resilience
uv run pytest tests/unit/core/test_resilience.py -v

# Тестировать metrics
uv run pytest tests/unit/core/test_metrics.py -v
```

---

## Дополнительная информация

- [Архитектура проекта](architecture.md)
- [Описание компонентов](components.md) - Детальное описание `core/utils.py`, `core/resilience.py`, `core/metrics.py`
- [Руководство по началу работы](getting-started.md)
- [Workflow и поток данных](workflow.md)
- [Тестирование](testing.md)
