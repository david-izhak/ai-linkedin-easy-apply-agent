selectors = {
    # "easy_apply_button_enabled": "button.jobs-apply-button:enabled", # outdated
    "easy_apply_button": "div.jobs-apply-button--top-card button", # резервный вариант поиска кнопки
    # "easy_apply_button": 'button:has-text("Easy Apply"):not([aria-label*="{:companyName}"])',

    # Job search form
    # "keyword_input": 'input[id*="jobs-search-box-keyword-id"]', # outdated
    # "location_input": 'input[id*="jobs-search-box-location-id"]', # outdated

    # Easy apply form
    "checkbox": ".jobs-easy-apply-modal input[type='checkbox']",
    "fieldset": ".jobs-easy-apply-modal fieldset",
    "select": ".jobs-easy-apply-modal select",
    # "next_button": ".jobs-easy-apply-modal footer button[aria-label*='next'], footer button[aria-label*='Review']", # outdated
    "submit": ".jobs-easy-apply-modal footer button[aria-label*='Submit']",
    "enabled_submit_or_next_button": ".jobs-easy-apply-modal footer button[aria-label*='Submit']:enabled, .jobs-easy-apply-modal  footer button[aria-label*='next']:enabled, .jobs-easy-apply-modal  footer button[aria-label*='Review']:enabled",
    "text_input": ".jobs-easy-apply-modal input[type='text'], .jobs-easy-apply-modal textarea",
    "home_city": ".jobs-easy-apply-modal input[id*='easyApplyFormElement'][id*='city-HOME-CITY']",
    "phone": ".jobs-easy-apply-modal input[id*='easyApplyFormElement'][id*='phoneNumber']",
    "document_upload": ".jobs-easy-apply-modal div[class*='jobs-document-upload']",
    "document_upload_label": "label[class*='jobs-document-upload']",
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

    # fetch jobs list page
    # "search_result_list": ".jobs-search-results-list", # outdated
    # "search_result_list_text": "small.jobs-search-results-list__text", # outdated
    # "search_result_list_subtitle": ".jobs-search-results-list__subtitle span[dir='ltr']",  # outdated. С помощью этого селектора можно найти общее количество найденных по запросу вакансии.
    # "search_result_list_item": ".jobs-search-results-list li.jobs-search-results__list-item", # It doesn't work. There is no such selector on the page with a jobs list.
    "job_card_container": "div.job-card-container[data-job-id]",
    "job_card_container_in_list": ".scaffold-layout__list-item",
    # "search_result_list_item_link": "a.job-card-container__link, a.job-card-list__title--link, a.job-card-list__title",  # outdated
    # "search_result_list_item_company_name": "div.artdeco-entity-lockup__subtitle span, div.job-card-container__company-name, a.job-card-container__company-name",  # outdated
    # "applied_to_job_feedback": ".artdeco-inline-feedback",  # outdated

    # Job details page
    "job_description": "div#job-details",
    "company_profile_link": "div.job-details-jobs-unified-top-card__company-name a",
    "company_description": ".jobs-company__company-description",
    "job_criteria_list": ".jobs-description-section__body .jobs-description-details__list-item",

    # Company About page
    "company_about_overview": "section.org-about-module__margin-bottom p",
    "company_about_details_list": "dl.overflow-hidden",

    # fetch guest (if needed in future)
    # "job_count": ".results-context-header__job-count", # outdated
    "show_more_button": ".infinite-scroller__show-more-button:enabled",
    # "search_result_list_item_guest": ".jobs-search__results-list li", # It doesn't work. There is no such selector on the page with a jobs list.
    # "search_result_list_item_title_guest": ".base-search-card__title", # outdated
    # "search_result_list_item_subtitle_guest": ".base-search-card__subtitle", # outdated
    # "search_result_list_item_location_guest": ".job-search-card__location", # outdated
}
