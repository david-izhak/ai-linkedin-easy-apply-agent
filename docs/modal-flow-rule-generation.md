# Автоматическая генерация правил для Modal Flow

## Обзор

Система автоматической генерации правил позволяет боту автоматически создавать правила для заполнения полей форм на основе решений, принятых LLM. Это обеспечивает непрерывное обучение системы и уменьшает количество обращений к LLM для повторяющихся вопросов.

## Архитектура

### Разделение запросов

Система использует два отдельных запроса к LLM:

1. **Запрос на принятие решения** - LLM решает, как заполнить поле формы
2. **Запрос на генерацию правила** - LLM генерирует правило для автоматического заполнения подобных полей в будущем

Это разделение обеспечивает:
- Более надежную генерацию правил (специализированный промпт)
- Упрощение промпта для принятия решений
- Лучшее качество генерируемых правил

### Компоненты

#### 1. RuleSuggestion Model

Модель данных для представления сгенерированного правила:

```python
class RuleSuggestion(BaseModel):
    q_pattern: str  # Regex паттерн для матчинга вопроса
    strategy: Dict[str, Any]  # Определение стратегии (kind, params)
    confidence: float  # Уверенность в правиле (0.0-1.0)
```

#### 2. BaseLLMDelegate

Абстрактный базовый класс с методом `generate_rule()`:

```python
async def generate_rule(
    self,
    field_info: Dict[str, Any],
    selected_value: Any,
    profile: CandidateProfile,
    job_context: Optional[Dict[str, Any]] = None
) -> Optional[RuleSuggestion]
```

#### 3. OpenAILLMDelegate

Реализация генерации правил для OpenAI:

- Использует `RULE_GENERATION_PROMPT` как system prompt
- Вызывает `llm_client.generate_structured_response()` с схемой `RuleSuggestion`
- Обрабатывает ошибки и возвращает `None` при неудаче

#### 4. RulesEngine

Интеграция генерации правил в процесс принятия решений:

1. После получения решения от LLM
2. Если `learning_config.enabled` и `learning_config.auto_learn` включены
3. Если `learning_config.use_separate_rule_generation` включен:
   - Вызывается `llm_delegate.generate_rule()`
   - Если генерация успешна, правило обрабатывается
4. Если генерация не удалась и `learning_config.rule_generation_fallback` включен:
   - Используется `suggest_rule` из решения LLM (fallback)
5. Правило валидируется и сохраняется в `RuleStore`

## Процесс генерации правил

### 1. Принятие решения

Когда поле не найдено в правилах и эвристиках, система обращается к LLM:

```python
llm_decision = await llm_delegate.decide(field_info, profile)
```

LLM возвращает решение без `suggest_rule` (поле оставлено как `null`).

### 2. Генерация правила

После успешного принятия решения система генерирует правило:

```python
rule_suggestion = await llm_delegate.generate_rule(
    field_info=field_info,
    selected_value=llm_decision.value,
    profile=profile,
    job_context=job_context
)
```

### 3. Валидация правила

Правило валидируется перед сохранением:

- **Паттерн**: Проверка синтаксиса regex, длины (3-200 символов)
- **Стратегия**: Проверка наличия известного `kind` и валидных `params`
- **Уверенность**: Должна быть >= `confidence_threshold` (по умолчанию 0.85)
- **Дубликаты**: Проверка на существование правила с таким же паттерном

### 4. Сохранение правила

Если все проверки пройдены, правило сохраняется в `RuleStore`:

```python
new_rule = rule_store.add_llm_rule(
    signature=signature,
    suggest_rule=suggest_rule,
    confidence=confidence
)
```

## Конфигурация

### LearningConfig

Настройки автоматического обучения:

```python
learning_config = LearningConfig(
    enabled=True,  # Включить автоматическое обучение
    auto_learn=True,  # Автоматически сохранять правила
    use_separate_rule_generation=True,  # Использовать отдельный запрос
    rule_generation_fallback=True,  # Использовать fallback на suggest_rule
    confidence_threshold=0.85,  # Минимальная уверенность
    enable_duplicate_check=True,  # Проверка на дубликаты
    enable_pattern_validation=True,  # Валидация паттернов
    enable_strategy_validation=True  # Валидация стратегий
)
```

### Параметры

- **enabled**: Главный переключатель механизма обучения
- **auto_learn**: Автоматически добавлять валидированные правила в RuleStore
- **use_separate_rule_generation**: Использовать отдельный запрос для генерации правил (рекомендуется)
- **rule_generation_fallback**: Использовать `suggest_rule` из решения как fallback, если отдельная генерация не удалась
- **confidence_threshold**: Минимальная уверенность для принятия правила (0.0-1.0)
- **enable_duplicate_check**: Проверять дубликаты перед добавлением
- **enable_pattern_validation**: Валидировать regex паттерны перед добавлением
- **enable_strategy_validation**: Валидировать структуру стратегии перед добавлением

## Промпты

### RULE_GENERATION_PROMPT

Системный промпт для генерации правил включает:

- Описание задачи генерации правила
- Структуру правила (q_pattern, strategy)
- Руководство по выбору стратегии для разных типов полей
- Примеры для checkbox, text, number, radio, select, combobox
- Требования к regex паттернам (case-insensitive, мультиязычность)
- Формат ответа (JSON)

### FIELD_DECISION_ENGINE_PROMPT

Упрощенный промпт для принятия решений:

- Удалены инструкции по генерации правил
- Фокус только на принятии решения
- `suggest_rule` оставлен как `null` с комментарием

## Примеры использования

### Базовое использование

```python
from modal_flow.rules_engine import RulesEngine
from modal_flow.rules_store import RuleStore
from modal_flow.learning_config import LearningConfig
from modal_flow.llm_delegate_openai import OpenAILLMDelegate
from llm.client_factory import get_llm_client

# Создать конфигурацию обучения
learning_config = LearningConfig(
    enabled=True,
    auto_learn=True,
    use_separate_rule_generation=True
)

# Создать LLM delegate
llm_client = get_llm_client(app_config.llm)
llm_delegate = OpenAILLMDelegate(llm_client)

# Создать RulesEngine
rules_engine = RulesEngine(
    profile=profile,
    rule_store=rule_store,
    llm_delegate=llm_delegate,
    learning_config=learning_config
)

# Принять решение - правило будет сгенерировано автоматически
decision = await rules_engine.decide(
    question="Do you know Python?",
    field_type="checkbox",
    options=None
)
```

### Отключение генерации правил

```python
learning_config = LearningConfig(
    enabled=False  # Отключить автоматическое обучение
)
```

### Использование только fallback

```python
learning_config = LearningConfig(
    enabled=True,
    use_separate_rule_generation=False,  # Не использовать отдельный запрос
    rule_generation_fallback=True  # Использовать suggest_rule из решения
)
```

## Типы стратегий

### literal

Для checkbox полей с фиксированным значением:

```python
{
    "kind": "literal",
    "params": {"value": True}
}
```

### profile_key

Для text полей с данными из профиля:

```python
{
    "kind": "profile_key",
    "params": {"key": "address.city"}
}
```

### numeric_from_profile

Для number полей с данными из профиля:

```python
{
    "kind": "numeric_from_profile",
    "params": {"key": "years_experience.python"}
}
```

### one_of_options

Для radio/select полей с фиксированными опциями:

```python
{
    "kind": "one_of_options",
    "params": {"preferred": ["Yes", "Да"]}
}
```

### one_of_options_from_profile

Для radio/select полей с выбором на основе профиля:

```python
{
    "kind": "one_of_options_from_profile",
    "params": {
        "key": "work_authorization.US",
        "synonyms": {
            "yes": ["Yes", "Да"],
            "no": ["No", "Нет"]
        }
    }
}
```

### salary_by_currency

Для salary полей с валютой:

```python
{
    "kind": "salary_by_currency",
    "params": {
        "base_key_template": "salary_expectation.monthly_net_{currency}",
        "default_currency": "nis"
    }
}
```

## Валидация правил

### Правила валидации паттернов

- Минимальная длина: 3 символа
- Максимальная длина: 200 символов
- Валидный синтаксис regex
- Избегать опасных паттернов (например, `.*.*`)

### Правила валидации стратегий

- `kind` должен быть одним из доступных стратегий
- `params` должен быть словарем
- Параметры должны соответствовать требованиям стратегии

### Проверка дубликатов

Система проверяет, существует ли уже правило с таким же:
- `field_type`
- `q_pattern` (точное совпадение, case-insensitive)

## Отладка

### Логирование

Система логирует следующие события:

- Генерация правила через отдельный запрос
- Успешная генерация правила (pattern, strategy, confidence)
- Ошибки генерации правил
- Использование fallback на `suggest_rule`
- Валидация правил (успех/неудача)
- Сохранение правил в RuleStore
- Обнаружение дубликатов

### Просмотр сгенерированных правил

Правила сохраняются в файл, указанный в `RuleStore`:

```python
rule_store = RuleStore("config/rules.yaml")
# Правила будут сохранены в config/rules.yaml
```

### Проверка качества правил

1. Проверьте логи на наличие ошибок валидации
2. Просмотрите сохраненные правила в `config/rules.yaml`
3. Проверьте уверенность правил (confidence)
4. Убедитесь, что правила работают для похожих вопросов

## Известные ограничения

1. **Качество правил зависит от LLM**: Качество генерируемых правил зависит от способностей LLM понимать контекст и генерировать корректные regex паттерны.

2. **Время ответа**: Использование отдельного запроса увеличивает время ответа на одно поле (два запроса вместо одного).

3. **Валидация паттернов**: Система валидирует синтаксис regex, но не проверяет семантическую корректность паттерна.

4. **Дубликаты**: Проверка дубликатов основана на точном совпадении паттернов, что может не всегда работать для семантически эквивалентных паттернов.

## Рекомендации

1. **Начните с высокого порога уверенности**: Используйте `confidence_threshold=0.9` для начала, чтобы сохранять только высококачественные правила.

2. **Мониторьте логи**: Регулярно проверяйте логи на ошибки валидации и проблемы с генерацией правил.

3. **Проверяйте сохраненные правила**: Периодически просматривайте `config/rules.yaml` и удаляйте некорректные правила.

4. **Используйте fallback**: Включите `rule_generation_fallback=True` для повышения надежности.

5. **Настройте валидацию**: Включите все проверки валидации для обеспечения качества правил.

## Миграция

### С старой версии

Если вы использовали старую версию с `suggest_rule` в решении:

1. Обновите код для использования `generate_rule()`
2. Установите `use_separate_rule_generation=True` в `LearningConfig`
3. Убедитесь, что `rule_generation_fallback=True` для обратной совместимости
4. Проверьте, что правила генерируются корректно

### Обратная совместимость

Система поддерживает обратную совместимость:

- Поле `suggest_rule` в `LLMDecision` оставлено для совместимости
- Можно использовать `rule_generation_fallback=True` для использования `suggest_rule` из решения
- Старые правила в `RuleStore` продолжают работать

## Ссылки

- [Архитектура проекта](architecture.md)
- [Описание компонентов](components.md)
- [Интеграция с LLM](llm-integration.md)
- [Структура проекта](project-structure.md)




