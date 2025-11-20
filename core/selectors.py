selectors = {
    # Easy apply button
    "easy_apply_button": 'a[data-view-name="job-apply-button"]:has-text("Easy Apply")',  # Основной селектор
    "easy_apply_button_fallback_1": 'a[data-view-name="job-apply-button"]',  # Фолбек 1: без текста
    "easy_apply_button_fallback_2": 'a[href*="/apply"]:has-text("Easy Apply")',  # Фолбек 2: по href
    "easy_apply_button_fallback_3": "div.jobs-apply-button--top-card button",  # Фолбек 3: старый селектор
    "easy_apply_button_by_data_view": "button[data-view-name='job-apply-button']",  # Кнопка Easy Apply по data-view-name
    "apply_button": 'a[data-view-name="job-apply-button"]:has-text("Apply")',  # Кнопка Apply (внешняя подача)

    # Easy apply form
    "checkbox": ".jobs-easy-apply-modal input[type='checkbox']",
    "fieldset": ".jobs-easy-apply-modal fieldset",
    "select": ".jobs-easy-apply-modal select",
    "submit": ".jobs-easy-apply-modal footer button[aria-label*='Submit']",
    "enabled_submit_or_next_button": ".jobs-easy-apply-modal footer button[aria-label*='Submit']:enabled, .jobs-easy-apply-modal  footer button[aria-label*='next']:enabled, .jobs-easy-apply-modal  footer button[aria-label*='Review']:enabled",
    "text_input": ".jobs-easy-apply-modal input[type='text'], .jobs-easy-apply-modal textarea",
    "home_city": ".jobs-easy-apply-modal input[id*='easyApplyFormElement'][id*='city-HOME-CITY']",
    "phone": ".jobs-easy-apply-modal input[id*='easyApplyFormElement'][id*='phoneNumber']",
    "document_upload": ".jobs-easy-apply-modal div[class*='jobs-document-upload']",
    "document_upload_label": "label[class*='jobs-document-upload']",
    "document_upload_input_type_file": "input[type='file']",
    "document_upload_input": "input[type='file'][id*='jobs-document-upload']",
    "radio_input": "input[type='radio']",
    "option": "option",
    "follow_company_checkbox": '.jobs-easy-apply-modal input[type="checkbox"][id*="follow-company-checkbox"]',

    # Login
    "login_indicator": "nav.global-nav",
    "captcha": "#captcha-internal",
    "email_input": "input#username",
    "password_input": "input#password",
    "login_submit": "button.btn__primary--large.from__button--floating",
    "skip_button": "button[text()='Skip']",

    # Job search results page
    "job_card_container": "div.job-card-container[data-job-id]",
    "job_card_container_in_list": ".scaffold-layout__list-item",
    "job_search_results_container": "div.jobs-search-results-list, div.scaffold-layout__list",  # Контейнер списка результатов поиска
    "job_count_subtitle": ".jobs-search-results-list__subtitle span[dir='ltr']",  # Подзаголовок со счетчиком вакансий
    "job_count_text": "small.jobs-search-results-list__text",  # Текст счетчика вакансий
    "job_count_header": ".results-context-header__job-count",  # Заголовок счетчика вакансий
    "show_more_button": ".infinite-scroller__show-more-button:enabled",
    "pagination_next_button": "button.jobs-search-pagination__button--next",  # Кнопка "Next" пагинации

    # Job card elements
    "job_card_link": "a.job-card-container__link",  # Ссылка на вакансию в карточке
    "job_card_title": "a.job-card-container__link strong",  # Заголовок вакансии в карточке
    "job_card_company": "div.artdeco-entity-lockup__subtitle span",  # Название компании в карточке

    # Job details page
    "job_description": 'div:has(> h2:has-text("About the job")) + p >> span[data-testid="expandable-text-box"]',
    "company_profile_link": 'a[href^="https://www.linkedin.com/company/"]',
    "company_description": 'div:has(> h2:has-text("About the company")) + div span[data-testid="expandable-text-box"]',
    "employment_type_details": 'div[data-view-name="job-detail-page"] button:has(svg#check-small)',

    # Company About page
    "company_about_overview": "section.org-about-module__margin-bottom p",
    "company_about_details_list": "dl.overflow-hidden",

    # Modal/Dialog
    "easy_apply_modal": ".jobs-easy-apply-modal",  # Модальное окно Easy Apply
    "dialog_role": '[role="dialog"]',  # Общий селектор для диалоговых окон

    # Loading indicators
    "loading_spinner": '[aria-busy="true"], [data-loading="true"]',  # Индикатор загрузки

    # Form elements (common)
    "label_for": "label[for='{id}']",  # Шаблон для label по id (используется динамически)
    "legend": "legend",  # Легенда fieldset
    "select_option": "option",  # Опция в select

    # Application status
    "applications_closed_text": "No longer accepting applications",  # Текст о закрытии приема заявок

    # Combobox/Listbox (for modal flow)
    "combobox_listbox_id_pattern": '[id^="triggered-expanded-"][role="listbox"]',  # Паттерн ID для LinkedIn typeahead listbox
    "combobox_listbox_class": 'div.basic-typeahead__triggered-content.fb-single-typeahead-entity__triggered-content[role="listbox"]',  # Класс для LinkedIn typeahead listbox
    "combobox_listbox_role": '[role="listbox"]:not(select)',  # Общий селектор для listbox (исключая select)
    "number_input": 'input[type="number"]',  # Поле ввода числа

    # Radio button form builder
    "radio_form_builder_title": "span[data-test-form-builder-radio-button-form-component__title]",  # Заголовок радио-кнопки в form builder

    # Data test attributes
    "data_test_selectable_option": '[data-test-text-selectable-option]',  # Элемент с data-test атрибутом для выбора опции

    # XPath patterns (for complex queries)
    "xpath_ancestor_with_class_or_id": 'xpath=ancestor::*[@class or @id][1]',  # XPath для поиска предка с class или id
    "xpath_ancestor_fieldset_legend": "xpath=ancestor::fieldset[1]/legend",  # XPath для legend в fieldset
    "xpath_ancestor_form_field": 'xpath=ancestor::*[contains(@class, \'form\') or contains(@class, \'field\') or contains(@class, \'input\')][1]//span[contains(@data-test, \'title\') or contains(@data-test, \'label\')]',  # XPath для поиска label в форме
}
