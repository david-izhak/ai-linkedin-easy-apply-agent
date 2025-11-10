# Discovery State: Маркеры прогресса дискавери

## Назначение
[deprecated] `discovery_state` ранее хранил устойчивые маркеры прогресса для процесса сбора вакансий (дискавери) при установленном лимите. Цель — исключить потери вакансий за счёт:
- детерминированного ключа поиска `search_key` для каждого набора фильтров;
- монотонного high‑water mark `last_seen_max_job_id` для «новых сверху»;
- порога «добора хвоста» `last_complete_sweep_before_id` для систематического прохода вниз при многократных запусках.

## Схема таблицы
```
[deprecated] CREATE TABLE IF NOT EXISTS discovery_state (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  search_key TEXT NOT NULL UNIQUE,
  last_seen_max_job_id INTEGER,
  last_complete_sweep_before_id INTEGER,
  updated_at TIMESTAMP NOT NULL
);
```

### Поля
- `search_key` — детерминированный хэш параметров поиска (например, SHA256 отсортированного JSON: `keywords`, `geoId`, `distance`, `f_WT`, `f_TPR`, `sortBy`, …). Один ключ → одно состояние.
- `last_seen_max_job_id` — максимальный когда‑либо виденный `job_id` для этого поиска (high‑water mark). Обновляется монотонно: `new = max(old, max(observed_ids_this_run))`.
- `last_complete_sweep_before_id` — минимальный встреченный `job_id`, до которого гарантированно дошли при «пролистывании вниз». Обновляется границей самого глубокого просмотра за запуск; если выдача исчерпана — фиксирует завершённый проход до этой границы.
- `updated_at` — время последнего обновления состояния.

## Алгоритм дискавери с лимитом L
1) Инициализация
- Построить `search_key` из параметров поиска.
- Прочитать состояние (`last_seen_max_job_id`, `last_complete_sweep_before_id`).

2) Сбор
- Идём по страницам: `start = 0, 25, 50, …`.
- На каждой странице собираем `(job_id, link, title, company)`.
- Отфильтровываем уже существующие `vacancies.id` (перед вставкой или полагаясь на `INSERT OR IGNORE`).
- Добавляем unseen, пока их количество < L, либо пока выдача не исчерпана.

3) Сохранение
- Вставить `unseen` в `vacancies` (`INSERT OR IGNORE`).
- Обновить маркеры:
  - `last_seen_max_job_id = max(last_seen_max_job_id, max(inserted_ids))`, если `unseen` не пуст.
  - `last_complete_sweep_before_id = min(all_observed_ids_this_run)`, где `all_observed_ids_this_run` — id, которые мы видели при пролистывании (даже если они уже были в БД). Если страницы закончились — это считается завершённым проходом до этой границы.

## Псевдокод обновления маркеров (UPSERT)
```
[deprecated] INSERT INTO discovery_state (search_key, last_seen_max_job_id, last_complete_sweep_before_id, updated_at)
VALUES (?, ?, ?, CURRENT_TIMESTAMP)
ON CONFLICT(search_key) DO UPDATE SET
  last_seen_max_job_id = MAX(discovery_state.last_seen_max_job_id, excluded.last_seen_max_job_id),
  last_complete_sweep_before_id = excluded.last_complete_sweep_before_id,
  updated_at = CURRENT_TIMESTAMP;
```

## Инварианты
- [deprecated] `last_seen_max_job_id` — монотонно не убывает.
- [deprecated] `last_complete_sweep_before_id` — отражает самую глубокую достигнутую нижнюю границу просмотра за последний запуск; может сдвигаться «вниз» (к меньшим id) по мере пролистывания.
- Дедупликация обеспечивается `vacancies.id PRIMARY KEY` и/или предварительной проверкой существования.

## Почему вакансии не теряются
- Мы набираем ровно L «новых для БД» (unseen), продолжая пагинацию, даже если на страницах встречаются в основном дубликаты.
- High‑water mark по id гарантирует, что всё «новое сверху» будет подобрано.
- Порог «добора хвоста» гарантирует систематический прогресс вниз при последующих запусках, даже если лимит мал и сверху постоянно появляются новые вакансии.

## Рекомендации по логированию
- Для каждого запуска логировать: `search_key`, количество страниц, собранные `unseen`, долю дубликатов, новые значения `last_seen_max_job_id` и `last_complete_sweep_before_id`.
- INFO — сводка запуска; DEBUG — подробная трассировка (URL страниц, счётчики и т.п.).
