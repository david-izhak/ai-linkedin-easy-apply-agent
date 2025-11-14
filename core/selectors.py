selectors = {
    # Easy apply button
    "easy_apply_button": 'a[data-view-name="job-apply-button"]:has-text("Easy Apply")',  # Основной селектор
    "easy_apply_button_fallback_1": 'a[data-view-name="job-apply-button"]',  # Фолбек 1: без текста
    "easy_apply_button_fallback_2": 'a[href*="/apply"]:has-text("Easy Apply")',  # Фолбек 2: по href
    "easy_apply_button_fallback_3": "div.jobs-apply-button--top-card button",  # Фолбек 3: старый селектор

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
    "job_card_container": "div.job-card-container[data-job-id]",
    "job_card_container_in_list": ".scaffold-layout__list-item",

    # Job details page
    "job_description": 'div:has(> h2:has-text("About the job")) + p >> span[data-testid="expandable-text-box"]',
    "company_profile_link": 'a[href^="https://www.linkedin.com/company/"]',
    "company_description": 'div:has(> h2:has-text("About the company")) + div span[data-testid="expandable-text-box"]',
    "employment_type_details": 'div[data-view-name="job-detail-page"] button:has(svg#check-small)',

    # Company About page
    "company_about_overview": "section.org-about-module__margin-bottom p",
    "company_about_details_list": "dl.overflow-hidden",

    # fetch guest (if needed in future)
    "show_more_button": ".infinite-scroller__show-more-button:enabled",
}
