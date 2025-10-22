Детальный план разработки дополнительных тестов для новой LLM-функциональности сформирован. План покрывает юнит- и интеграционные сценарии, фиксирует стратегии мокирования, проверку логирования и крайние случаи. Ниже приведены конкретные шаги и ожидаемые файлы тестов.

Цели покрытия:
- Подтвердить корректность клиента LLM [python.class LLMClient](llm/llm_client.py:12) и обработки ответов [python.def generate_response()](llm/llm_client.py:51).
- Устойчивость парсинга в [python.def calculate_skill_match()](llm/vacancy_filter.py:17), включая fallback.
- Корректную бизнес-логику [python.def is_vacancy_suitable()](llm/vacancy_filter.py:76) для всех жизненных статусов.
- Надежность работы с файлами резюме [python.def read_resume_text()](llm/resume_utils.py:7).
- Генерацию и сохранение сопроводительных писем [python.def generate_cover_letter()](llm/cover_letter_generator.py:14), [python.def save_cover_letter()](llm/cover_letter_generator.py:94).
- Интеграцию с фазой обработки и fallback механизмы (см. [python.def run_processing_phase()](phases/processing.py:107)).

Структура и предполагаемые файлы тестов:
- tests/unit/llm/test_llm_client.py — юнит-тесты клиента LLM.
- tests/unit/llm/test_vacancy_filter_calculate_skill_match.py — юнит-тесты парсинга и логирования.
- tests/unit/llm/test_vacancy_filter_is_vacancy_suitable.py — юнит-тесты бизнес-логики фильтрации вакансий.
- tests/unit/llm/test_resume_utils.py — юнит-тесты чтения резюме.
- tests/unit/llm/test_cover_letter_generator.py — юнит-тесты генерации писем и обработки исключений.
- tests/integration/test_llm_filter_fallback.py — интеграция LLM-фильтра с fallback-логикой из phases.processing.
- tests/integration/test_cover_letter_end_to_end.py — сквозной сценарий генерации и сохранения письма с заглушкой LLM.

Фикстуры и вспомогательные стратегии:
- Мок LLM-клиента: патч [python.def get_llm_client()](llm/client_factory.py:6) для возврата объекта с методом generate_response, управляемого тестом.
- Переопределение конфигурации: monkeypatch для env-переменных или прямой патч [python.class LLMSettings](llm/config.py:6) полей (LLM_PROVIDER, LLM_THRESHOLD_PERCENTAGE, LLM_TEMPERATURE).
- Мок БД: патч core.database.get_vacancy_by_id для возврата контролируемых словарей.
- Временные файлы резюме: tmp_path/monkeypatch для сценариев существующего/пустого/отсутствующего файла.
- Проверка логов: caplog с валидацией статусов result_status и ключевых полей extra.

Unit-тесты: детальные кейсы
1) llm_client.py
- Провайдеры: при разных settings.LLM_PROVIDER = "openai"/"ollama"/"anthropic" корректно инициализируется соответствующий клиент.
- generate_response:
  - Возврат объекта с атрибутом content — возвращается .content.
  - Возврат строки — преобразуется через str(response).
  - Исключение из client.invoke — логируется ошибка и пробрасывается LLMGenerationError.

2) vacancy_filter.calculate_skill_match()
- Валидный JSON: '{"match_percentage": 85, "analysis": "..."}' → (85, "...", result_status="success"); проверка 0≤match≤100.
- Невалидный JSON с числом: "85% overall" → (85, "85% overall", result_status="fallback_parse_success").
- Невалидный JSON без числа: "no clear match" → (0, "no clear match", result_status="fallback_parse_failed").
- Выход за границы: '{"match_percentage": 120, "analysis":"x"}' → ValueError (проверка устойчивости валидации).

3) vacancy_filter.is_vacancy_suitable()
- VacancyNotFound: core.database.get_vacancy_by_id → None → VacancyNotFoundError, лог result_status="vacancy_not_found".
- Пустое описание: description="" → False, лог result_status="no_description".
- Ошибка чтения резюме: [python.def read_resume_text()](llm/resume_utils.py:7) бросает ResumeReadError → пробрасывание, лог result_status="resume_read_error".
- Порог сравнения: патч settings.LLM_THRESHOLD_PERCENTAGE и мок calculate_skill_match:
  - match=69, threshold=70 → False.
  - match=70, threshold=70 → True.
  - match=0, threshold=0 → True.
  - match=100, threshold=100 → True.
- Логирование финальных полей: match_percentage, analysis, is_suitable, threshold, result_status="completed".

4) resume_utils.read_resume_text()
- Существующий файл: возвращает текст.
- Отсутствующий: FileNotFoundError → ResumeReadError; лог ошибки.
- Пустой файл: возвращает пустую строку без исключений.

5) cover_letter_generator.generate_cover_letter()
- Успех: патч core.database.get_vacancy_by_id на словарь с ключами; [python.def read_resume_text()](llm/resume_utils.py:7) → текст; мок [python.def get_llm_client()](llm/client_factory.py:6).generate_response → "LETTER". Проверить, что в переданном промпте присутствуют job_title, company_name, resume_text.
- Исключения:
  - VacancyNotFoundError: отсутствие вакансии → проброс.
  - ResumeReadError: ошибка чтения резюме → проброс.
  - Общая ошибка из generate_response → CoverLetterGenerationError с логированием.

6) cover_letter_generator.save_cover_letter()
- Успех: запись в tmpdir/generated_letters/cover_letter_{vacancy_id}.docx, проверка содержимого и логов.
- Ошибка: мок open() или os.makedirs для генерации исключения → CoverLetterSaveError.

Интеграционные тесты:
1) Fallback при ошибке LLM в обработке:
- Имитация ошибки в [python.def is_vacancy_suitable()](llm/vacancy_filter.py:76) (raise Exception) внутри логики обработки (см. [python.def run_processing_phase()](phases/processing.py:107) и [python.def _is_job_suitable()](phases/processing.py:21) из архитектуры).
- Проверить, что вызывается резервная word-based фильтрация и решается судьба вакансии корректно (в статусах и выборе apply/skip), а лог содержит отметку fallback.

2) Сквозной сценарий генерации письма:
- Использовать заглушку LLM (патч [python.def get_llm_client()](llm/client_factory.py:6) → FakeClient.generate_response возвращает детерминированный текст).
- Вызвать [python.def generate_cover_letter()](llm/cover_letter_generator.py:14) и затем [python.def save_cover_letter()](llm/cover_letter_generator.py:94).
- Проверить созданный файл, содержимое письма, логи.

Покрытие логирования и метрик:
- В [python.def calculate_skill_match()](llm/vacancy_filter.py:17) проверять provider, model, latency_ms, retries_count, result_status через caplog и extra.
- В [python.def is_vacancy_suitable()](llm/vacancy_filter.py:76) проверять match_percentage, analysis, threshold, is_suitable, итоговый result_status.
- Для ошибок — подтверждать коды статусов ("vacancy_not_found", "resume_read_error", "error").

Матрица конфигураций:
- Провайдеры: "openai", "ollama", "anthropic" — проверка корректной инициализации клиента.
- Пороговые значения: 0, 70 (дефолт), 100 — проверки границ.
- Ретраи/таймауты: убедиться, что значения читаются и участвуют в логировании (не эмулировать реальный retry, но проверять max_retries и timeout в полях клиента).
- Температура: устанавливать 0.0 в тестах для детерминизма, когда это влияет.

Риски и минимизация недетерминизма:
- Не вызывать реальных API LLM; все ответы детерминированы через моки.
- Для интеграции с Ollama использовать заглушку вместо реального рантайма.

Запуск тестов:
- Юнит: pytest tests/unit -q
– Интеграция: pytest tests/integration -q
- Маркеры: при необходимости ввести @pytest.mark.llm для группировки новых тестов.

Критерии готовности:
- Покрытие > 90% для директории llm/.
- Пройденные интеграционные сценарии с подтвержденным fallback-потоком.
- Проверена корректность логирования и статусов обработки во всех ключевых ветвлениях.

Все ссылки на элементы реализации:
- [python.class LLMClient](llm/llm_client.py:12), [python.def generate_response()](llm/llm_client.py:51)
- [python.def calculate_skill_match()](llm/vacancy_filter.py:17), [python.def is_vacancy_suitable()](llm/vacancy_filter.py:76)
- [python.def read_resume_text()](llm/resume_utils.py:7)
- [python.def generate_cover_letter()](llm/cover_letter_generator.py:14), [python.def save_cover_letter()](llm/cover_letter_generator.py:94)
- [python.def get_llm_client()](llm/client_factory.py:6)
- [python.class LLMSettings](llm/config.py:6)
- [python.def run_processing_phase()](phases/processing.py:107)

Этот план завершен и готов для имплементации тестов в согласованной структуре.

# Todo List
**Настройка тестового окружения**
Создать фикстуры `pytest` для мокирования `LLMClient`.
Создать фикстуры для тестовых данных (вакансии, резюме).
**Unit-тесты для `llm/`**
`llm_client.py`: Проверить корректность инициализации клиента (`ChatOpenAI`, `Ollama`, `ChatAnthropic`) в зависимости от `LLM_PROVIDER`.
`llm_client.py`: Проверить, что `generate_response` корректно обрабатывает ответы (`AIMessage`, `str`) и пробрасывает `LLMGenerationError` при ошибке.
`resume_utils.py`: Проверить `read_resume_text` на чтение существующего файла, пустого файла и обработку `FileNotFoundError` (через `ResumeReadError`).
`vacancy_filter.py`: `calculate_skill_match` - мокировать `LLMClient` и проверить:
- Успешный парсинг валидного JSON ответа.
- Устойчивый fallback-парсинг при невалидном JSON (извлечение числа).
- Обработку ответа без чисел (возврат 0).
- Проверку граничных значений `match_percentage` (0, 100).
`vacancy_filter.py`: `is_vacancy_suitable` - проверить:
- Вызов `VacancyNotFoundError` при отсутствии вакансии.
- Возврат `False` для вакансий без описания.
- Проброс `ResumeReadError` при ошибке чтения резюме.
- Корректное сравнение `match_percentage` с пороговым значением.
`cover_letter_generator.py`: `generate_cover_letter` - проверить:
- Успешную генерацию письма (проверка формирования промпта).
- Обработку исключений (`VacancyNotFoundError`, `ResumeReadError`).
`cover_letter_generator.py`: `save_cover_letter` - проверить создание директории и файла.
**Integration-тесты**
Создать тест, проверяющий полный цикл: `is_vacancy_suitable` вызывает `calculate_skill_match`, который использует мок `LLMClient`.
Создать тест для `phases/processing.py`: убедиться, что при возникновении исключения в `is_vacancy_suitable` происходит fallback на word-based фильтрацию.
Настроить интеграционный тест с использованием локального mock-сервера для Ollama, который проверяет сквозной сценарий генерации и сохранения сопроводительного письма.

Диаграмма:
graph TD
    subgraph "Unit-тесты"
        A[llm_client.py] --> B(Тест выбора провайдера)
        A --> C(Тест обработки ошибок)
        
        D[vacancy_filter.py] --> E(calculate_skill_match)
        E --> E1(Успешный парсинг JSON)
        E --> E2(Fallback-парсинг при невалидном JSON)
        E --> E3(Граничные значения match_percentage)
        
        D --> F(is_vacancy_suitable)
        F --> F1(Вакансия не найдена)
        F --> F2(Пустое описание вакансии)
        F --> F3(Ошибка чтения резюме)
        F --> F4(Проверка порогового значения)
        
        G[resume_utils.py] --> H(read_resume_text)
        H --> H1(Существующий файл)
        H --> H2(Отсутствующий файл)
        H --> H3(Пустой файл)
        
        I[cover_letter_generator.py] --> J(generate_cover_letter)
        J --> J1(Успешная генерация)
        J --> J2(Обработка исключений)
    end

    subgraph "Integration-тесты"
        K(Сквозной сценарий) --> L{Локальный LLM}
        L --> M(Мок-сервер Ollama)
        L --> N(Сохранение письма)
        
        O(Интеграция с `processing.py`) --> P(Fallback-логика)
        P --> P1(LLM возвращает ошибку)
        P --> P2(Переключение на word-based фильтр)
    end

    subgraph "Настройка и фикстуры"
        Q(Фикстуры pytest) --> R(Мок LLMClient)
        Q --> S(Тестовые данные вакансий)
        Q --> T(Временные файлы резюме)
    end

    A --> D
    D --> G
    G --> I
    K --> O
