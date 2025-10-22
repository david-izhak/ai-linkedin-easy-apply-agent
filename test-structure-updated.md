# Структура тестовой системы проекта LinkedIn Easy Apply Bot

## 1. Введение

Тестовая система проекта LinkedIn Easy Apply Bot состоит из unit-тестов и интеграционных тестов, которые проверяют логику приложения, взаимодействие с базой данных и функциональность веб-скрэпинга. Система использует pytest в качестве основного фреймворка с плагинами для асинхронных тестов и интеграции с Playwright.

## 2. Общая структура тестовой директории

```
tests/
├── __init__.py
├── conftest.py
├── fixtures/
├── integration/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_database_flow.py
│   ├── test_phases_flow.py
│   ├── test_scraping_logic.py
│   └── test_workflow_integration.py
└── unit/
    ├── __init__.py
    ├── actions/
    │   ├── __init__.py
    │   ├── test_apply.py
    │   ├── test_login.py
    │   └── test_fetch_jobs.py
    ├── apply_form/
    │   ├── __init__.py
    │   ├── test_change_text_input.py
    │   ├── test_click_next_button.py
    │   ├── test_fill_boolean.py
    │   ├── test_fill_fields.py
    │   ├── test_fill_multiple_choice_fields.py
    │   ├── test_fill_text_fields.py
    │   ├── test_insert_home_city.py
    │   ├── test_insert_phone.py
    │   ├── test_uncheck_follow_company.py
    │   ├── test_upload_docs.py
    │   └── test_wait_for_no_error.py
    ├── core/
    │   ├── __init__.py
    │   └── test_database_unit.py
    │   └── test_utils.py
    └── phases/
        ├── __init__.py
        └── test_discovery.py
        └── test_enrichment.py
        └── test_processing_logic.py
```

### 2.1. Основные файлы и модули

- **`conftest.py`** (корень): Содержит общие фикстуры для тестов, включая фикстуру для тестовой базы данных и настройки event loop для избежания конфликтов между pytest-asyncio и pytest-playwright.
- **`fixtures/`**: Директория с HTML-файлами, используемыми в интеграционных тестах для симуляции страниц LinkedIn.
- **`integration/`**: Интеграционные тесты, проверяющие взаимодействие между компонентами.
- **`unit/`**: Unit-тесты, проверяющие изолированную логику отдельных модулей.

## 3. Архитектура тестов и зависимости

### 3.1. Unit-тесты

- **`tests/unit/actions/test_apply.py`**: Тестирует логику подачи заявки.
- **`tests/unit/actions/test_login.py`**: Тестирует логику входа в LinkedIn.
- **`tests/unit/actions/test_fetch_jobs.py`**: Тестирует логику получения информации о вакансиях.
- **`tests/unit/apply_form/test_fill_fields.py`**: Тестирует логику заполнения полей формы.
- **`tests/unit/apply_form/test_*`**: Тестирует отдельные модули заполнения формы (boolean, text, multiple choice, etc.).
- **`tests/unit/core/test_database_unit.py`**: Тестирует функции работы с базой данных.
- **`tests/unit/core/test_utils.py`**: Тестирует вспомогательные функции.
- **`tests/unit/phases/test_discovery.py`**: Тестирует фазу поиска вакансий.
- **`tests/unit/phases/test_enrichment.py`**: Тестирует фазу обогащения вакансий.
- **`tests/unit/phases/test_processing_logic.py`**: Тестирует логику обработки фаз приложения.

### 3.2. Интеграционные тесты

- **`tests/integration/test_database_flow.py`**: Тестирует потоки работы с базой данных.
- **`tests/integration/test_phases_flow.py`**: Тестирует потоки выполнения фаз приложения.
- **`tests/integration/test_scraping_logic.py`**: Тестирует логику скрэпинга данных с LinkedIn (после решения конфликта плагинов использует синхронный API Playwright).
- **`tests/integration/test_workflow_integration.py`**: Тестирует полный рабочий процесс от поиска до подачи заявки.

### 3.3. Зависимости между тестами

- Все тесты используют фикстуры из `tests/conftest.py` для настройки тестовой базы данных.
- Интеграционные тесты используют HTML-файлы из `tests/fixtures/` для симуляции страниц LinkedIn.
- Модуль `actions/fetch_jobs_sync.py` был создан специально для тестирования функций скрэпинга в синхронном режиме.

## 4. Схема и работа тестовой базы данных

### 4.1. Фикстура тестовой базы данных

В `tests/conftest.py` определена фикстура `db_connection`, которая:

- Создает ин-память SQLite базу данных для каждого теста
- Использует `MockConnectionWrapper` для предотвращения преждевременного закрытия соединения
- Применяет патч к `sqlite3.connect` для перенаправления всех подключений к тестовой базе
- Вызывает `database.setup_database()` для инициализации схемы

```python
class MockConnectionWrapper:
    """A wrapper around a real sqlite3 connection that intercepts the close() call."""
    def __init__(self, real_conn):
        self._real_conn = real_conn

    def close(self):
        # This is the magic: we do nothing when close() is called by the application code.
        pass

    def __getattr__(self, name):
        # Delegate all other attribute access (e.g., .cursor(), .commit())
        # to the real connection object.
        return getattr(self._real_conn, name)

@pytest.fixture
def db_connection():
    """
    Pytest fixture that patches `sqlite3.connect` to use a single, shared
    in-memory database for the duration of a test. This prevents functions from
    closing the connection prematurely.
    """
    real_conn = sqlite3.connect(":memory:")
    mock_conn_wrapper = MockConnectionWrapper(real_conn)

    with patch('core.database.sqlite3.connect', return_value=mock_conn_wrapper):
        database.setup_database()
        yield mock_conn_wrapper # Yield the wrapped connection

    real_conn.close()
```

### 4.2. Модель базы данных

Тесты работают с базой данных, определенной в `core/database.py`. В тестах используется in-memory версия для изоляции.

## 5. Типы тестов их логика

### 5.1. Unit-тесты

**Уровень:** Изолированные проверки отдельных функций или классов

**Инструменты:** pytest, unittest.mock

**Примеры:**
- `tests/unit/apply_form/test_fill_fields.py`: Проверяет логику заполнения полей формы
- `tests/unit/core/test_database_unit.py`: Проверяет функции работы с базой данных
- `tests/unit/phases/test_processing_logic.py`: Проверяет логику обработки фаз
- `tests/unit/actions/test_apply.py`: Проверяет логику подачи заявки
- `tests/unit/actions/test_login.py`: Проверяет логику входа в LinkedIn

### 5.2. Integration-тесты

**Уровень:** Взаимодействие компонентов, API, базы данных

**Инструменты:** pytest, playwright.sync_api (после решения конфликта), фикстуры из conftest.py

**Примеры:**
- `tests/integration/test_scraping_logic.py`: Проверяет логику скрэпинга данных с LinkedIn
- `tests/integration/test_database_flow.py`: Проверяет потоки работы с базой данных
- `tests/integration/test_phases_flow.py`: Проверяет потоки выполнения фаз приложения
- `tests/integration/test_workflow_integration.py`: Проверяет полный рабочий процесс

## 6. Изоляция и подготовка данных

### 6.1. Механизмы изоляции

- **Mock-объекты:** Используются в `tests/conftest.py` для изоляции базы данных
- **Patch:** Используется для перенаправления вызовов `sqlite3.connect` к тестовой базе
- **In-memory база данных:** Обеспечивает изоляцию между тестами

### 6.2. Подготовка тестовых данных

- **HTML-файлы:** Используются в интеграционных тестах для симуляции страниц LinkedIn
- **Фикстуры:** Определяют начальное состояние тестов
- **Функция `load_fixture()`**: Вспомогательная функция для загрузки HTML-файлов в тестах

## 7. Интеграции и внешние зависимости

### 7.1. Внешние сервисы

- **LinkedIn API (через веб-скрэпинг):** Имитируется с помощью HTML-файлов в интеграционных тестах
- **Playwright:** Используется для автоматизации браузера (в синхронном режиме в интеграционных тестах после решения конфликта)

### 7.2. Подмены сервисов

- **База данных:** Заменяется in-memory SQLite для изоляции тестов
- **Сетевые вызовы:** Имитируются с помощью HTML-файлов в интеграционных тестах

## 8. Конфигурация и окружение

### 8.1. Файлы конфигурации

- **`pyproject.toml`**: Содержит настройки pytest, зависимости и параметры asyncio
- **`pytest_integration.ini`**: Специальная конфигурация для запуска интеграционных тестов
- **`tests/conftest.py`**: Содержит общие фикстуры для всех тестов
- **`tests/integration/conftest.py`**: Содержит фикстуры для интеграционных тестов

### 8.2. Параметры pytest

```toml
[tool.pytest.ini_options]
# Убираем asyncio_mode для предотвращения конфликта между pytest-asyncio и pytest-playwright
asyncio_mode = "auto"
addopts = "-v --disable-warnings"
python_files = "test_*.py"
python_classes = "Test*"
python_functions = "test_*"
testpaths = ["tests/unit"]
markers = [
    "unit: marks tests as unit tests",
    "integration: marks tests as integration tests"
]
```

### 8.3. Используемые плагины

- **pytest-asyncio**: Для асинхронных тестов (в unit-тестах)
- **pytest-playwright**: Для тестов с браузерной автоматизацией (в интеграционных тестах в синхронном режиме)
- **pytest-mock**: Для создания mock-объектов

## 9. Качество тестов и рекомендации

### 9.1. Покрытие кода

- **Unit-тесты:** Проверяют основные функции и классы изолированно
- **Integration-тесты:** Проверяют взаимодействие между компонентами
- **Проблема с конфликтом плагинов:** Была решена путем создания синхронной версии функций скрэпинга

### 9.2. Рекомендации по улучшению

1. **Добавить E2E тесты:** Для проверки полного пользовательского сценария
2. **Расширить unit-тесты:** Покрыть больше граничных случаев и исключений
3. **Добавить параметризованные тесты:** Для проверки различных сценариев
4. **Улучшить фикстуры:** Для более удобного управления тестовыми данными

### 9.3. Особенности после решения конфликта плагинов

После решения конфликта между pytest-asyncio и pytest-playwright:

- Интеграционные тесты используют синхронный API Playwright
- Создана отдельная синхронная версия функций скрэпинга в `actions/fetch_jobs_sync.py`
- Используется специальная фикстура в `tests/integration/conftest.py` для управления браузером
- Все интеграционные тесты теперь проходят успешно без ошибок конфликта плагинов

## 10. Диаграмма зависимостей тестов

```mermaid
graph TD
    A[Main Test Entry] --> B[conftest.py]
    B --> C[db_connection fixture]
    B --> D[event_loop fixture]
    A --> E[Unit Tests]
    A --> F[Integration Tests]
    E --> G[test_fill_fields.py]
    E --> H[test_database_unit.py]
    E --> I[test_processing_logic.py]
    E --> J[test_apply.py]
    E --> K[test_login.py]
    E --> L[test_fetch_jobs.py]
    F --> M[test_scraping_logic.py]
    F --> N[test_database_flow.py]
    F --> O[test_phases_flow.py]
    F --> P[test_workflow_integration.py]
    M --> Q[fetch_jobs_sync.py]
    G --> R[apply_form module]
    H --> S[core/database.py]
    I --> T[phases module]
    J --> U[actions/apply.py]
    K --> V[actions/login.py]
    L --> W[actions/fetch_jobs.py]
    Q --> X[Playwright sync API]
    M --> Y[HTML fixtures]
    Y --> Z[sample_search_page.html]
    Y --> AA[sample_job_page.html]
    Y --> AB[sample_company_page.html]