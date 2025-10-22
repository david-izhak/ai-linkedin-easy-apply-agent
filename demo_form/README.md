# README: Тестовый стенд для Modal Flow Engine

## Описание

Этот тестовый стенд имитирует процесс LinkedIn Easy Apply с несколькими модальными окнами для тестирования функциональности `ModalFlowRunner`.

## Структура

- `index.html` - HTML страница с тестовыми формами
- `test_data.json` - Тестовые данные и маппинги полей
- `test_runner.py` - Скрипт для запуска автоматизированного теста

## Использование

### Ручной тест

1. Откройте `demo_form/index.html` в браузере
2. Нажмите кнопку "Start Test Flow"
3. Заполните формы вручную и проверьте работу навигации

### Автоматизированный тест

```bash
python demo_form/test_runner.py
```

Скрипт автоматически:
- Загрузит профиль из `config/profile_example.json`
- Загрузит правила из `config/rules.yaml`
- Откроет тестовый стенд в браузере
- Запустит `ModalFlowRunner` для автоматического заполнения форм

## Покрытие тестов

Тестовый стенд включает:

### Типы полей:
- ✅ Text input (phone, location, bio)
- ✅ Number input (years of experience, salary)
- ✅ Radio buttons (work authorization, relocate)
- ✅ Checkboxes (skills)
- ✅ Select dropdown (communication method)
- ✅ Textarea (bio with character limit)

### Валидация:
- ✅ Required fields
- ✅ Pattern validation (phone number)
- ✅ Min/max values (years, salary)
- ✅ Maxlength (bio - 500 characters)

### Динамические элементы:
- ✅ Lazy fields (relocation location appears when "Yes" is selected)
- ✅ Loading spinners
- ✅ Error messages

### Многошаговый процесс:
- ✅ 4 модальных окна
- ✅ Кнопки Next/Continue/Review
- ✅ Кнопка Submit на последнем шаге
- ✅ Кнопки Back для навигации назад

## Ожидаемое поведение

При правильной работе `ModalFlowRunner` должен:

1. **Modal 1 (Contact Information):**
   - Заполнить телефон (из профиля или дефолт)
   - Заполнить локацию из `preferred_location`
   - Выбрать "Yes" для work authorization (по правилу)

2. **Modal 2 (Experience):**
   - Заполнить years of Python experience из `years_experience.python`
   - Заполнить salary из `salary_expectation.monthly_net_usd`
   - Выбрать "Yes" для relocate (по правилу или эвристике)

3. **Modal 3 (Additional Information):**
   - Заполнить GitHub из `links.github`
   - Заполнить bio из `short_bio_en`
   - Выбрать опции из dropdown

4. **Modal 4 (Review & Submit):**
   - Показать сводку заполненных данных
   - Нажать Submit

## Отладка

Если тест не проходит:

1. Проверьте логи в консоли браузера (F12)
2. Проверьте логи Python скрипта
3. Убедитесь, что файлы конфигурации существуют:
   - `config/profile_example.json`
   - `config/rules.yaml`
   - `config/normalizer_rules.yaml`

4. Проверьте, что все зависимости установлены:
   ```bash
   pip install playwright pydantic rapidfuzz pyyaml
   playwright install chromium
   ```



