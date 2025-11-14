# Механизм обнаружения кнопки Easy Apply

## Обзор

Программа обнаруживает кнопку Easy Apply на странице вакансии LinkedIn используя систему resilient selectors с повторными попытками и circuit breaker.

## Компоненты

### 1. Селектор кнопки

**Файл:** `core/selectors.py`

**Селектор:**
```python
"easy_apply_button": "div.jobs-apply-button--top-card button"
```

**Альтернативные варианты (закомментированы):**
- `"button.jobs-apply-button:enabled"` - устаревший
- `'button:has-text("Easy Apply"):not([aria-label*="{:companyName}"])'` - более специфичный

### 2. Код обнаружения

**Файл:** `actions/apply.py`

```python
async def click_easy_apply_button(page: Page) -> None:
    """Clicks the easy apply button using a resilient selector."""
    logger.info("Clicking easy apply button...")
    executor = resilience.get_selector_executor(page)
    await executor.click(selectors.get("easy_apply_button", "div.jobs-apply-button--top-card button"))
    logger.debug("Easy apply button is clicked")
```

### 3. Механизм resilient execution

**Файл:** `core/resilience.py`

**Класс:** `SelectorExecutor`

**Метод:** `click(selector_name, css_selector=None, context=None, timeout=None)`

#### Как работает:

1. **Получение CSS селектора:**
   - Если `css_selector` не передан, берется из словаря `selectors` по ключу `selector_name`
   - Если не найден, используется сам `selector_name` как CSS селектор

2. **Таймаут:**
   - По умолчанию: `config.performance.selector_timeout` (5000ms = 5 секунд)
   - Можно переопределить через параметр `timeout`

3. **Операция:**
   ```python
   async def operation():
       await self.page.wait_for_selector(css_selector, timeout=timeout)
       await self.page.click(css_selector)
   ```

4. **Повторные попытки:**
   - Количество попыток: `config.resilience.max_attempts` (по умолчанию: 3)
   - Задержка: экспоненциальная с базой 2
   - Начальная задержка: `config.resilience.initial_wait` (по умолчанию: 1.0 секунда)
   - Максимальная задержка: `config.resilience.max_wait` (по умолчанию: 10.0 секунд)
   - Jitter: включен по умолчанию

5. **Circuit Breaker:**
   - Порог срабатывания: `config.circuit_breaker.failure_threshold` (по умолчанию: 5)
   - Время восстановления: `config.circuit_breaker.recovery_timeout` (по умолчанию: 60 секунд)

## Проблема в текущей реализации

### Текущий код (неправильный):

```python
await executor.click(selectors.get("easy_apply_button", "div.jobs-apply-button--top-card button"))
```

**Проблема:** Передается CSS селектор напрямую как позиционный аргумент, что интерпретируется как `selector_name`, а не как `css_selector`.

### Правильный вызов:

```python
await executor.click(selector_name="easy_apply_button")
```

Или, если нужно явно указать CSS селектор:

```python
await executor.click(
    selector_name="easy_apply_button",
    css_selector="div.jobs-apply-button--top-card button"
)
```

## Конфигурация

### Таймауты и повторы

**Файл:** `config.py`

```python
class PerformanceConfig(BaseSettings):
    selector_timeout: int = 5000  # ms

class ResilienceConfig(BaseSettings):
    max_attempts: int = 3
    initial_wait: float = 1.0  # seconds
    max_wait: float = 10.0  # seconds
    exponential_base: int = 2
    jitter: bool = True
```

### Переопределения для конкретных селекторов

**Файл:** `config.py`

```python
class SelectorRetryOverrideConfig(BaseSettings):
    overrides: Dict[str, Dict[str, Any]] = {
        "easy_apply_button_enabled": {"max_attempts": 5, "initial_wait": 2.0},
        "submit": {"max_attempts": 1, "initial_wait": 0},
    }
```

**Примечание:** Для `easy_apply_button` переопределений нет, используются значения по умолчанию.

## Возможные причины, почему кнопка не находится

1. **Неверный селектор:**
   - LinkedIn мог изменить структуру HTML
   - Классы или структура DOM могли измениться

2. **Таймаут слишком короткий:**
   - Страница загружается медленно
   - Кнопка появляется асинхронно после загрузки страницы
   - Текущий таймаут: 5 секунд на каждую попытку

3. **Кнопка в iframe:**
   - Если кнопка находится в iframe, селектор не сработает на основной странице
   - Нужно переключиться на iframe перед поиском

4. **Кнопка не видима:**
   - Кнопка может быть скрыта CSS (display: none, visibility: hidden)
   - Кнопка может быть за пределами видимой области (требуется прокрутка)

5. **Условия отображения:**
   - Кнопка может не отображаться для некоторых вакансий
   - Может требоваться авторизация
   - Могут быть ограничения на основе профиля пользователя

6. **Проблема с вызовом метода:**
   - Текущий вызов `executor.click()` может работать некорректно из-за неправильной передачи параметров

## Рекомендации по исправлению

1. **Исправить вызов метода:**
   ```python
   await executor.click(selector_name="easy_apply_button")
   ```

2. **Увеличить таймаут для easy_apply_button:**
   ```python
   class SelectorRetryOverrideConfig(BaseSettings):
       overrides: Dict[str, Dict[str, Any]] = {
           "easy_apply_button": {"max_attempts": 5, "initial_wait": 2.0},
           "easy_apply_button_enabled": {"max_attempts": 5, "initial_wait": 2.0},
       }
   ```

3. **Добавить альтернативные селекторы:**
   - Попробовать несколько вариантов селекторов
   - Использовать более гибкие селекторы (например, по тексту)

4. **Добавить ожидание загрузки страницы:**
   - Убедиться, что страница полностью загружена перед поиском кнопки
   - Использовать `page.wait_for_load_state("networkidle")`

5. **Добавить логирование:**
   - Логировать, какие селекторы пробуются
   - Логировать скриншоты при неудаче
   - Логировать HTML структуру вокруг ожидаемого места кнопки

6. **Проверить видимость:**
   - Использовать `wait_for_selector` с параметром `state="visible"`
   - Проверить, не скрыта ли кнопка CSS

## Пример правильной реализации

```python
async def click_easy_apply_button(page: Page) -> None:
    """Clicks the easy apply button using a resilient selector."""
    logger.info("Clicking easy apply button...")
    
    # Убедиться, что страница загружена
    await page.wait_for_load_state("networkidle", timeout=10000)
    
    executor = resilience.get_selector_executor(page)
    
    # Попробовать основной селектор
    try:
        await executor.click(
            selector_name="easy_apply_button",
            timeout=10000  # Увеличенный таймаут
        )
        logger.debug("Easy apply button is clicked")
        return
    except Exception as e:
        logger.warning(f"Primary selector failed: {e}")
    
    # Попробовать альтернативные селекторы
    alternative_selectors = [
        'button:has-text("Easy Apply")',
        'button[aria-label*="Easy Apply"]',
        '.jobs-apply-button button',
        'button.jobs-apply-button:enabled'
    ]
    
    for alt_selector in alternative_selectors:
        try:
            logger.info(f"Trying alternative selector: {alt_selector}")
            await executor.click(
                selector_name="easy_apply_button_alt",
                css_selector=alt_selector,
                timeout=5000
            )
            logger.debug("Easy apply button is clicked with alternative selector")
            return
        except Exception as e:
            logger.warning(f"Alternative selector {alt_selector} failed: {e}")
            continue
    
    # Если все селекторы не сработали, выбросить исключение
    raise Exception("Easy Apply button not found with any selector")
```

## Логирование

Текущее логирование показывает:
- Попытки поиска селектора
- Таймауты
- Ошибки

Но не показывает:
- Какие селекторы пробуются
- Структуру DOM вокруг ожидаемого места
- Скриншоты при неудаче

Рекомендуется добавить более детальное логирование для диагностики.






