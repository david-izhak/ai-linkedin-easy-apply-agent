# Исправление дублирования данных в базе

## Проблема

Вакансии сохранялись в базу данных **дважды**, что приводило к следующим логам:
```
core.database - INFO - Saved 20 new discovered jobs. Ignored 0 duplicates.
core.database - INFO - Saved 0 new discovered jobs. Ignored 20 duplicates.
```

## Причина

Двойное сохранение происходило в двух местах:

1. **Первое сохранение** в `actions/fetch_jobs.py` (строка 362):
   ```python
   database.save_discovered_jobs(unseen_collected)
   ```

2. **Второе сохранение** в `phases/discovery.py` (строка 129):
   ```python
   save_discovered_jobs(discovered_jobs_data)
   ```

Функция `fetch_job_links_user()` возвращала список найденных вакансий И сразу сохраняла их в базу данных. Затем вызывающий код в `run_discovery_phase()` получал тот же список и пытался сохранить его снова.

## Решение

Удалено дублирующее сохранение из `phases/discovery.py`:

### Изменения в `phases/discovery.py`:

1. Удален импорт `save_discovered_jobs` из `core.database`
2. Удален вызов `save_discovered_jobs(discovered_jobs_data)` 
3. Добавлен комментарий, что сохранение происходит внутри `fetch_job_links_user`

**До:**
```python
from core.database import save_discovered_jobs
# ...
discovered_jobs_data = await fetch_job_links_user(...)
save_discovered_jobs(discovered_jobs_data)
```

**После:**
```python
# Импорт save_discovered_jobs удален
# ...
discovered_jobs_data = await fetch_job_links_user(...)
# Note: discovered jobs are already saved inside fetch_job_links_user
logger.info(f"Discovery phase completed. Found {len(discovered_jobs_data)} new jobs.")
```

### Изменения в тестах

Обновлены unit-тесты в `tests/unit/phases/test_discovery.py`:
- Удалены моки для `save_discovered_jobs` (теперь не импортируется в discovery.py)
- Добавлены комментарии, объясняющие, что сохранение происходит внутри `fetch_job_links_user`

## Результат

После исправления вакансии сохраняются **только один раз** внутри функции `fetch_job_links_user()`.

Теперь в логах будет появляться только одна строка:
```
core.database - INFO - Saved 20 new discovered jobs. Ignored 0 duplicates.
```

## Тестирование

Все тесты проходят успешно:
- ✅ `tests/unit/phases/test_discovery.py` - 7 тестов
- ✅ `tests/unit/actions/test_fetch_jobs.py` - 13 тестов
- ✅ `tests/integration/test_database_flow.py` - 1 тест

## Архитектурное решение

Выбран подход, при котором функция `fetch_job_links_user()` сама отвечает за сохранение найденных вакансий. Это логично, так как:

1. **Принцип единственной ответственности**: функция, которая находит вакансии, также отвечает за их сохранение
2. **Меньше дублирования кода**: не нужно везде вызывать `save_discovered_jobs()` после `fetch_job_links_user()`
3. **Меньше вероятность ошибок**: невозможно забыть сохранить вакансии или сохранить их дважды

## Файлы, затронутые изменениями

- `phases/discovery.py` - удалено дублирующее сохранение
- `tests/unit/phases/test_discovery.py` - обновлены тесты

