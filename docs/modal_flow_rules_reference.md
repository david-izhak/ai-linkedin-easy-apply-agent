# Справочник по rule-based прохождению модального окна LinkedIn Easy Apply

## Обзор высокого уровня

- **Оркестрация.** `FormFillCoordinator` собирает пути к резюме/cover letter и делегирует обработку модального окна объекту `ModalFlowFormFiller` вместе с контекстом вакансии и конфигурацией приложения (`AppConfig`).
- **Modal flow runner.** Класс `ModalFlowFormFiller` создает `ModalFlowRunner`, подготавливая профиль кандидата, хранилище правил, нормализатор вопросов, LLM-делегат и настройки обучения. Runner управляет всеми шагами модального окна: загрузкой документов, заполнением полей, навигацией между шагами и отправкой формы.
- **Правила и стратегии.** Решения для каждого поля принимает `RulesEngine`, который нормализует вопрос, формирует сигнатуру поля, находит подходящее правило (`RuleStore`), исполняет стратегию и, при необходимости, обращается к эвристикам или LLM.
- **Тип-специфическое заполнение.** `ModalFlowRunner` содержит выделенные обработчики для радиокнопок, чекбоксов, выпадающих списков, комбобоксов, числовых и текстовых полей. Каждый обработчик вызывает `RulesEngine.decide`, а затем применяет решение к конкретному UI-элементу.

```44:78:core/form_filler/modal_flow_impl.py
            runner = ModalFlowRunner(
                page=page,
                profile=self._resources.profile,
                rule_store=self._resources.rule_store,
                normalizer=self._resources.normalizer,
                llm_delegate=self._resources.llm_delegate,
                learning_config=self._resources.learning_config,
                logger=self._logger,
            )

            outcome: Any = await runner.run(
                max_steps=self._max_steps,
                should_submit=job_context.should_submit,
                job_context=job_context.to_job_payload(),
                document_paths=document_paths,
                lazy_generator=lazy_generator,
            )
```

## Загрузка зависимостей modal flow

- `ModalFlowResources` лениво подгружает профиль кандидата (`CandidateProfile`), правила (`RuleStore`), нормализатор (`QuestionNormalizer`) и конфигурацию обучения (`LearningConfig`). Все пути берутся из `AppConfig.modal_flow`.
- LLM-делегат (`OpenAILLMDelegate`) создается только если включен в конфигурации и имеются ключи.

```36:94:core/form_filler/modal_flow_resources.py
    def profile(self) -> CandidateProfile:
        if self._profile is None:
            profile_path = Path(self._modal_flow_config.profile_path)
            self._logger.debug("Loading candidate profile from %s", profile_path)
            store = ProfileStore(profile_path)
            self._profile = store.load()
        return self._profile

    @property
    def rule_store(self) -> RuleStore:
        if self._rule_store is None:
            rules_path = Path(self._modal_flow_config.rules_path)
            self._logger.debug("Loading rules from %s", rules_path)
            self._rule_store = RuleStore(rules_path)
        return self._rule_store
```

## Основной цикл выполнения ModalFlowRunner

1. `run()` ждет исчезновения спиннеров и ищет активное модальное окно.
2. Извлекает процент прогресса (если доступен) и сравнивает его с предыдущим шагом, чтобы понять, сменился ли диалог.
3. Делает диагностические скриншоты, затем вызывает `_fill_modal` с флагом `is_same_dialog` для пропуска уже заполненных полей.
4. После заполнения ищет кнопку Submit/Next, учитывая dry-run режим.
5. Обнаруживает ошибки валидации и останавливается по достижении `max_steps`.

```350:377:modal_flow/modal_flow.py
    async def _fill_modal(self, modal: Locator, is_same_dialog: bool = False):
        self.logger.info(f"[MODAL_FILL] Starting to fill modal fields (is_same_dialog={is_same_dialog})")
        if is_same_dialog:
            self.logger.warning(
                "[MODAL_FILL] Same dialog detected after navigation. "
                "Skipping fields that are already filled."
            )

        if self._document_uploader:
            self.logger.info("[MODAL_FILL] Handling document upload")
            await self._document_uploader.handle_modal(modal)

        self.logger.info("[MODAL_FILL] Processing radio groups")
        await self._handle_radio_groups(modal, is_same_dialog=is_same_dialog)
        self.logger.info("[MODAL_FILL] Processing checkboxes")
        await self._handle_checkboxes(modal, is_same_dialog=is_same_dialog)
        self.logger.info("[MODAL_FILL] Processing comboboxes")
        await self._handle_comboboxes(modal, is_same_dialog=is_same_dialog)
        self.logger.info("[MODAL_FILL] Processing number inputs")
        await self._handle_number_inputs(modal, is_same_dialog=is_same_dialog)
        self.logger.info("[MODAL_FILL] Processing textboxes")
        await self._handle_textboxes(modal, is_same_dialog=is_same_dialog)
        self.logger.info("[MODAL_FILL] Finished filling modal fields")
```

### Повторный шаг (unchanged dialog)

- Если после клика `Next` процент заполнения не меняется (например, форма осталась на шаге `44%`), `ModalFlowRunner` считает, что диалог не сменился, и повторно вызывает `_fill_modal` с `is_same_dialog=True`.
- В этом режиме обработчики радиокнопок, чекбоксов, селектов/комбобоксов и текстовых полей проверяют текущее состояние элементов (`is_checked`, выбранная опция, `input_value`) и пропускают уже заполненные поля.
- В логах появляются сообщения вида `[DIALOG_CHECK] Dialog did not change...` и `[CHECKBOX]/[TEXTBOX] Skipping already filled ...`, что помогает диагностировать зависания из-за валидации.

### Загрузка документов

- `ModalDocumentUploader` ищет блоки LinkedIn типа `jobs-document-upload`, отличает резюме и cover letter по тексту/ARIA, и прикрепляет файлы из `DocumentPaths` или генерирует cover letter на лету через `CoverLetterLazyGenerator`.

```128:187:modal_flow/document_upload.py
class ModalDocumentUploader:
    """Detects document upload sections and attaches files automatically."""

    async def handle_modal(self, modal: Locator) -> None:
        if self._state.is_finished(
            self._document_paths, has_lazy_cover=self._lazy_generator is not None
        ):
            return

        upload_sections = modal.locator("div[class*='jobs-document-upload']")
        count = await upload_sections.count()

        for idx in range(count):
            section = upload_sections.nth(idx)
            await self._process_section(section)

        await self._process_loose_inputs(modal)
```

## Архитектура правил

### Хранилище правил (`RuleStore`)

- Правила хранятся в `config/rules.yaml` в едином массиве `rules`.
- При поиске учитываются `scope.site`, тип поля, регулярное выражение `signature.q_pattern` (case-insensitive) и отпечаток опций (`options_fingerprint`).

```80:139:modal_flow/rules_store.py
    def find(self, signature: FieldSignature) -> Optional[Dict[str, Any]]:
        for rule in self.data.get("rules", []):
            rule_scope = rule.get("scope", {})
            rule_sig = rule.get("signature", {})

            site = rule_scope.get("site", "*")
            if site != "*" and site != signature.site:
                continue

            if rule_sig.get("field_type") != signature.field_type:
                continue

            q_pattern = rule_sig.get("q_pattern", "").strip()
            if q_pattern:
                match = re.search(q_pattern, signature.q_norm, re.IGNORECASE)
                if not match:
                    continue

            opts_fp = rule_sig.get("options_fingerprint")
            if opts_fp and opts_fp != signature.opts_fp:
                continue

            return rule
```

### Структура правил в YAML

- Каждое правило содержит `scope` (форма, локаль, сайт), `signature` (тип поля, шаблон вопроса, отпечаток опций), `constraints` и `strategy`.
- Пример обязательного radio-вопроса о визовой поддержке:

```20:37:config/rules.yaml
- constraints:
    required: true
  id: rule_001
  scope:
    form_kind: job_apply
    locale:
    - en
    - ru
    site: '*'
  signature:
    field_type: radio
    q_pattern: (visa|work authorization|разрешение на работу|legal authorization)
  strategy:
    kind: one_of_options
    params:
      synonyms:
        'No':
        - 'no'
        - нет
        'Yes':
        - 'yes'
        - да
        - authorized
        - i am authorized
```

### Нормализация вопросов

- `QuestionNormalizer` чистит текст, загружает словари синонимов, ключевые слова типов вопросов, карты навыков и валют.
- Конфигурация нормализатора задается в `config/normalizer_rules.yaml` — например, карта синонимов для ответов Yes/No и для навыков.
- После очистки нормализатор убирает случаи, когда строка состоит из двух идентичных половин (типичный эффект дублирования legend + label).

```8:34:config/normalizer_rules.yaml
synonyms:
  Yes:
    - "yes"
    - "y"
    - "true"
    - "да"
  No:
    - "no"
    - "n"
    - "false"
    - "нет"

skill_synonyms:
  gcp:
    - "google cloud platform"
    - "google cloud"
  aws:
    - "amazon web services"
```

### Формирование `options_fingerprint`

- Fingerprint рассчитывается функцией `options_fingerprint` из `modal_flow/field_signature.py`. Она нормализует каждую опцию (нижний регистр, схлопывание пробелов, обрезка краевых пробелов), сортирует список, объединяет строки символом `|`, после чего вычисляет SHA1-хэш и добавляет префикс `sha1:`.

```12:27:modal_flow/field_signature.py
def options_fingerprint(options: List[str]) -> str:
    if not options:
        return ""
    normalized = [" ".join(o.lower().split()) for o in options]
    blob = "|".join(sorted(normalized))
    hash_obj = hashlib.sha1(blob.encode("utf-8"))
    return "sha1:" + hash_obj.hexdigest()
```

- `RulesEngine.decide` формирует `FieldSignature` и передает fingerprint только тогда, когда список опций не пустой (radio/select/combobox).

```101:116:modal_flow/rules_engine.py
        opts_fp = options_fingerprint(options) if options else None
        signature = FieldSignature(
            field_type=field_type,
            q_norm=q_norm,
            opts_fp=opts_fp,
            site=site,
            form_kind=form_kind,
            locale=locale
        )
```

- Источники опций:
  - Radio: `_handle_radio_groups` собирает тексты вариантов через `_get_radio_option_text`.
  - Select: `_handle_comboboxes` и `_handle_selects` (часть `_handle_comboboxes` и цикл по `modal.locator("select")`) читают все `<option>`.
  - Combobox: `_process_single_combobox` извлекает варианты из `listbox`.
  - Checkbox/text/number: fingerprint не рассчитывается (список опций отсутствует).

- Fingerprint нужен для точного сопоставления правил, когда два вопроса совпадают по тексту, но отличаютcя набором опций. В `RuleStore.find` правило игнорируется, если `signature.options_fingerprint` не совпадает с сохраненным хэшем.

```80:134:modal_flow/rules_store.py
            opts_fp = rule_sig.get("options_fingerprint")
            if opts_fp and opts_fp != signature.opts_fp:
                continue
```

- **Пример.** Для списка опций `["Yes", "No", "Prefer not to say "]` fingerprint будет вычислен из строки `"no|prefer not to say|yes"` и сохранен как `sha1:9e6d4e0f...`. Это помогает отличить поле с тремя вариантами от аналогичного вопроса, где опций только две.

### Решение поля (`RulesEngine`)

1. Нормализует вопрос (`normalize_text`), формирует `FieldSignature`.
2. Пытается найти правило в `RuleStore`.
3. Исполняет стратегию из `modal_flow.strategies`.
4. Если правило не найдено или вернуло некорректное значение — включает эвристики (чекбоксы по навыкам, зарплата по валюте) и LLM.
5. LLM-ответы могут порождать новые правила через механизм автоматического обучения (`LearningConfig`).

```101:180:modal_flow/rules_engine.py
        q_norm = self.normalizer.normalize_text(question)
        signature = FieldSignature(
            field_type=field_type,
            q_norm=q_norm,
            opts_fp=opts_fp,
            site=site,
            form_kind=form_kind,
            locale=locale
        )

        rule = self.rule_store.find(signature)
        if rule:
            strategy_kind = rule.get("strategy", {}).get("kind")
            params = rule.get("strategy", {}).get("params", {})
            strategy = create_strategy(
                strategy_kind=strategy_kind,
                params=params,
                normalizer=self.normalizer,
                logger=self.logger
            )
            decision = strategy.get_value(
                profile=self.profile,
                a_field={"question": question, "options": options},
            )
```

### Поддерживаемые стратегии

- **`literal`** — возвращает фиксированное значение (`value`).
- **`profile_key`** — берет значение по ключу из профиля (`Profile.get_nested_value`), например `personal.firstName`.
- **`numeric_from_profile`** — извлекает числовое значение и приводит к целому (подходит для «лет опыта»).
- **`one_of_options`** — выбирает опцию, сопоставляя синонимы или список предпочтительных значений.
- **`one_of_options_from_profile`** — сопоставляет значение из профиля с опциями (через карту синонимов).
- **`salary_by_currency`** — определяет валюту из вопроса и выбирает зарплату из профиля по шаблону ключа.

## Обработка типов полей

### Радиокнопки

- Группируются по `name`, извлекается текст вопроса и опций.
- `RulesEngine.decide(..., field_type="radio")` определяет целевой вариант.
- Выбранная опция прокликивается и проверяется через `expect(...).to_be_checked()`.

```420:525:modal_flow/modal_flow.py
        for name, items in groups.items():
            question = await self._infer_group_question(items[0])
            options = []
            option_map = {}
            for item in items:
                option_text = await self._get_radio_option_text(item)
                if option_text:
                    options.append(option_text)
                    normalized_option = self.normalizer.normalize_string(option_text).lower()
                    option_map[normalized_option] = item

            decision = await self.rules_engine.decide(
                question=question,
                field_type="radio",
                options=options
            )
            selected_option = decision if decision else (options[0] if options else None)

            if selected_option:
                normalized_target_option = self.normalizer.normalize_string(selected_option).lower()
                matched_radio = option_map.get(normalized_target_option)
                if matched_radio:
                    await matched_radio.check(force=True)
                    await expect(matched_radio).to_be_checked()
```

### Чекбоксы

- Для каждого чекбокса берется текст метки, вызывается `RulesEngine.decide` с типом `checkbox`.
- Возвращенное truthy значение ведет к `check(force=True)`; стратегию можно настроить через правила (например, `literal` для фиксированной галочки).
- Вопрос для LLM формируется как конкатенация легенды группы и конкретной метки опции: `legend: … . label: …`. Это позволяет LLM различать элементы одной группы.

```535:554:modal_flow/modal_flow.py
    async def _handle_checkboxes(self, modal: Locator):
        boxes = modal.get_by_role("checkbox")
        for i in range(count):
            cb = boxes.nth(i)
            label = await self._label_for(cb)
            decision = await self.rules_engine.decide(
                question=label,
                field_type="checkbox",
                options=None
            )
            should_check = bool(decision)
            if should_check:
                await cb.check(force=True)
                await expect(cb).to_be_checked()
```

### Выпадающие списки (`select`)

- Собираются все опции, создается fingerprint для поиска правил.
- После решения правило/LLM значение нормализуется и выбирается через `select_option`.

```568:604:modal_flow/modal_flow.py
        selects = modal.locator("select")
        for i in range(select_count):
            sel = selects.nth(i)
            question = await self._label_for(sel)
            options = [await opt_loc.inner_text() for opt_loc in await sel.locator("option").all()]
            decision = await self.rules_engine.decide(
                question=question, field_type="select", options=options
            )
            selected_option = decision if decision else (options[0] if options else None)
            if selected_option:
                normalized_target_option = self.normalizer.normalize_string(selected_option)
                for opt_loc in option_locators:
                    current_option_text = await opt_loc.inner_text()
                    normalized_current_option = self.normalizer.normalize_string(current_option_text)
                    if normalized_current_option == normalized_target_option:
                        found_option_value = await opt_loc.get_attribute("value")
                        await sel.select_option(value=found_option_value)
                        break
```

### Комбобоксы (typeahead)

- `RulesEngine` выдает строку поиска; поле очищается, заполняется, открывается список вариантов.
- `_process_single_combobox` ищет лучший матч (exact, startswith, contains) и кликает по нему; при отсутствии списка поле заполняется как текст.

```609:848:modal_flow/modal_flow.py
        initial_decision = await self.rules_engine.decide(
            question=question,
            field_type="combobox",
            options=None
        )
        if not initial_decision:
            self.logger.warning(f"No decision for combobox '{question}', skipping")
            return
        search_text = str(initial_decision).strip()
        await combo.click(force=True)
        await combo.clear()
        await combo.fill(search_text)
        listbox = modal.locator('[role="listbox"]:not(select)')
        option_locators = await listbox.get_by_role("option").all()
        best_match = self._find_best_match(search_text, options)
        if best_match:
            for opt_loc in option_locators:
                opt_text = await opt_loc.inner_text()
                if opt_text and opt_text.strip().lower() == best_match.lower():
                    await opt_loc.click(timeout=1000)
                    break
```

### Числовые поля

- Извлекаются атрибуты (placeholder, min/max) для логирования.
- `RulesEngine` решает с типом `number`; строка приводится к целому (`str(int(value))`).

```898:938:modal_flow/modal_flow.py
        number_inputs = modal.locator('input[type="number"]')
        for i in range(count):
            num_input = number_inputs.nth(i)
            question = await self._label_for(num_input)
            decision = await self.rules_engine.decide(
                question=question,
                field_type="number",
                options=None
            )
            value = decision if decision else "0"
            if isinstance(value, (int, float)):
                value = str(int(value))
            elif str(value).replace(".", "").isdigit():
                value = str(int(float(value)))
            else:
                value = "0"
            await num_input.fill(value)
```

### Текстовые поля

- Определяется реальный тип поля (`number`/`text`) по атрибутам.
- Значение берется из правил/LLM; для текстовых полей fallback — `N/A`.

```948:979:modal_flow/modal_flow.py
        tbs = modal.get_by_role("textbox").and_(
            modal.locator(':not([role="combobox"])')
        )
        for i in range(count):
            tb = tbs.nth(i)
            question = await self._label_for(tb)
            input_type = (await tb.get_attribute("type") or "").lower()
            inputmode = (await tb.get_attribute("inputmode") or "").lower()
            field_type = "number" if (input_type == "number" or inputmode in ("numeric", "decimal")) else "text"
            decision = await self.rules_engine.decide(
                question=question,
                field_type=field_type,
                options=None
            )
            value = decision if decision else ("N/A" if field_type == "text" else "0")
            if field_type == "number":
                value = str(int(value) if str(value).isdigit() else 0)
            await tb.fill(str(value))
```

## Данные профиля кандидата

- `CandidateProfile` загружается из JSON/ YAML; предоставляет метод `get_nested_value`, который понимает пути с точками и индексацией массивов.
- Пример данных, используемых правилами: годы опыта, каналы связи, локация, ссылки.

```4:77:config/profile_example.json
  "years_experience": {
    "ai": 2,
    "architecture": 7,
    "docker": 7,
    "python": 7,
    "spring_framework": 9
  },
  "contact": {
    "phone": "+972-53-548-7266",
    "email": "itskovdi@gmail.com",
    "preferred_communication": "Email",
    "linkedin": "https://www.linkedin.com/in/david-izhak/"
  },
  "availability": {
    "notice_period_days": 10,
    "relocate_willingness": "Yes",
    "preferred_location": "Tel Aviv, Israel"
  }
```

## Автообучение и fallback к LLM

- Если правило не найдено или вернуло некорректное значение, `RulesEngine` пробует встроенные эвристики (например, чекбокс навыка ставится, если навык есть в профиле, зарплата — по валюте).
- При включенном LLM `RulesEngine` делегирует решение с контекстом поля и профиля, а затем (при достаточной уверенности) может сгенерировать и валидацией (`RuleSuggestionValidator`) добавить новое правило в `RuleStore`.
- Конфигурация обучения управляется `LearningConfig` (порог уверенности, дедупликация, режим ревью).

## Практические рекомендации по расширению

- **Добавление правила:** обновите `config/rules.yaml`, указав уникальный `id`, корректный `q_pattern` и стратегию с параметрами. Используйте `options_fingerprint`, если набор опций стабилен.
- **Новые синонимы/навыки:** обновите `config/normalizer_rules.yaml`, чтобы нормализатор видел новые термины (особенно для чекбоксов и радио-вопросов).
- **Обновление профиля:** убедитесь, что необходимые значения (например, `years_experience.python`) присутствуют в профиле кандидата; стратегии `profile_key` и `numeric_from_profile` используют точные ключи.
- **Отладка:** включите подробный лог уровня DEBUG — в логах `ModalFlowRunner` и `RulesEngine` печатаются нормализованные вопросы, выбранные стратегии и решения.

### Поддерживаемые типы полей

- `radio` — группы радиокнопок.
- `checkbox` — чекбоксы.
- `select` — нативные выпадающие списки (`<select>`).
- `combobox` — поля с подсказками (typeahead).
- `number` — числовые инпуты (`input[type="number"]`).
- `text` — текстовые поля (`input[type="text"]`, `textarea`).
- `multiselect` — присутствует в `FieldSignature`, но пока не имеет обработчика в `ModalFlowRunner`.

### Важные замечания

- Для полей без `preferred` в `one_of_options` после изменения стратегии возвращается `None`, и решение переходит к эвристикам/LLM; чтобы выбор был детерминирован, задавайте `preferred`.
- Отпечатки опций (`options_fingerprint`) задавайте только для полей с фиксированным набором вариантов; если оставить `null`, правило будет работать, но без защиты от похожих вопросов с другим набором опций.
- `multiselect` пока не обрабатывается в `ModalFlowRunner`; если планируете поддержку таких полей, потребуется добавить соответствующий обработчик.
- Автозаполнение документов (резюме/cover letter) выполняется вне правил, через `ModalDocumentUploader`.

Документ охватывает весь путь данных от конфигурации профиля и правил до заполнения конкретного UI-элемента, позволяя быстро ориентироваться в rule-based системе прохождения модального окна.

