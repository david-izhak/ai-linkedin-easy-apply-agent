# Генерация правил через отдельный LLM запрос

**Дата:** 2025-11-10  
**Версия:** 2.1.0  
**Тип изменения:** Feature

## Описание

Реализована автоматическая генерация правил для заполнения полей форм через отдельный запрос к LLM. Это улучшает качество генерируемых правил и упрощает взаимодействие с LLM.

## Изменения

### Новая функциональность

1. **Отдельный запрос для генерации правил**
   - Создан новый промпт `RULE_GENERATION_PROMPT` для генерации правил
   - Добавлен метод `generate_rule()` в `BaseLLMDelegate`
   - Реализована генерация правил в `OpenAILLMDelegate`

2. **Упрощение промпта принятия решений**
   - Упрощен `FIELD_DECISION_ENGINE_PROMPT`
   - Удалены инструкции по генерации правил из промпта принятия решений
   - Промпт теперь фокусируется только на принятии решений

3. **Новая модель данных**
   - Добавлена модель `RuleSuggestion` для структурированного представления правил
   - Включает `q_pattern`, `strategy`, и `confidence`

4. **Расширенная конфигурация**
   - Добавлены поля `use_separate_rule_generation` и `rule_generation_fallback` в `LearningConfig`
   - Добавлены соответствующие поля в `ModalFlowLearningSettings` в `config.py`
   - Обновлено создание `LearningConfig` в `ModalFlowResources` для передачи новых параметров
   - Поддержка fallback на `suggest_rule` из решения при неудаче отдельной генерации

### Обновленные компоненты

- `modal_flow/llm_delegate.py`: Добавлена модель `RuleSuggestion` и абстрактный метод `generate_rule()`
- `modal_flow/llm_delegate_openai.py`: Реализованы методы `generate_rule()` и `_build_rule_generation_prompt()`
- `modal_flow/rules_engine.py`: Интегрирована генерация правил через отдельный запрос
- `modal_flow/learning_config.py`: Добавлены новые параметры конфигурации
- `config.py`: Добавлены поля `use_separate_rule_generation` и `rule_generation_fallback` в `ModalFlowLearningSettings`
- `core/form_filler/modal_flow_resources.py`: Обновлено создание `LearningConfig` для передачи новых параметров
- `llm/prompts.py`: Добавлен `RULE_GENERATION_PROMPT`, упрощен `FIELD_DECISION_ENGINE_PROMPT`

### Обратная совместимость

- Поле `suggest_rule` в `LLMDecision` оставлено для обратной совместимости
- Поддержка fallback на `suggest_rule` из решения при включенном `rule_generation_fallback`
- Существующие правила в `RuleStore` продолжают работать

## Преимущества

1. **Более надежная генерация правил**: Специализированный промпт обеспечивает лучшее качество правил
2. **Упрощение взаимодействия с LLM**: Разделение задач упрощает промпты и улучшает результаты
3. **Гибкость**: Возможность отключения генерации правил или использования fallback
4. **Качество**: Валидация правил перед сохранением обеспечивает высокое качество

## Миграция

### Для существующих пользователей

Изменения обратно совместимы. Система будет работать с существующими правилами и конфигурацией.

### Рекомендуемые действия

1. Обновите `LearningConfig` для использования новой функциональности:
   ```python
   learning_config = LearningConfig(
       enabled=True,
       auto_learn=True,
       use_separate_rule_generation=True,  # Рекомендуется
       rule_generation_fallback=True
   )
   ```

2. Проверьте логи на наличие ошибок генерации правил

3. Просмотрите сгенерированные правила в `config/rules.yaml`

### Отключение новой функциональности

Если нужно вернуться к старому поведению:

```python
learning_config = LearningConfig(
    enabled=True,
    use_separate_rule_generation=False,  # Отключить отдельный запрос
    rule_generation_fallback=True  # Использовать suggest_rule из решения
)
```

## Тестирование

Добавлены комплексные тесты:

- Юнит-тесты для `RuleSuggestion` модели
- Юнит-тесты для `generate_rule()` метода
- Интеграционные тесты для `RulesEngine`
- Интеграционные тесты для полного цикла генерации и сохранения правил

Все тесты проходят успешно.

## Документация

- Создана документация `docs/modal-flow-rule-generation.md`
- Обновлена документация в `docs/components.md`
- Обновлена документация в `docs/llm-integration.md`
- Обновлена навигация в `docs/README.md`

## Примеры использования

### Базовое использование

```python
from modal_flow.learning_config import LearningConfig
from modal_flow.llm_delegate_openai import OpenAILLMDelegate
from llm.client_factory import get_llm_client

# Создать конфигурацию
learning_config = LearningConfig(
    enabled=True,
    auto_learn=True,
    use_separate_rule_generation=True
)

# Создать LLM delegate
llm_client = get_llm_client(app_config.llm)
llm_delegate = OpenAILLMDelegate(llm_client)

# Использовать в RulesEngine
rules_engine = RulesEngine(
    profile=profile,
    rule_store=rule_store,
    llm_delegate=llm_delegate,
    learning_config=learning_config
)
```

## Известные ограничения

1. **Время ответа**: Использование отдельного запроса увеличивает время ответа (два запроса вместо одного)
2. **Качество правил**: Зависит от способностей LLM генерировать корректные regex паттерны
3. **Валидация**: Система валидирует синтаксис regex, но не проверяет семантическую корректность

## Будущие улучшения

1. Кэширование результатов генерации правил
2. Улучшение валидации паттернов (семантический анализ)
3. Поддержка других LLM провайдеров для генерации правил
4. Метрики качества сгенерированных правил

## Ссылки

- [Документация по генерации правил](modal-flow-rule-generation.md)
- [Описание компонентов](components.md)
- [LLM интеграция](llm-integration.md)

