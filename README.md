# LinkedIn Easy Apply Bot (Python)

This is a Python port of the LinkedIn Easy Apply bot originally written in TypeScript using Puppeteer. It automates the process of searching for jobs on LinkedIn and applying using the "Easy Apply" feature.

## Prerequisites

*   **Python 3.7+**: Ensure you have Python installed on your system.
*   **LinkedIn Account**: You need a valid LinkedIn account. The bot will log in using your credentials.

## Installation

1. **Clone or download** this repository.
2.  **Create a Virtual Environment (Recommended)**:
    ```bash
    python -m venv venv
    ```
3.  **Activate the Virtual Environment**:
    *   On Windows:
        ```bash
        venv\Scripts\activate
        ```
    *   On macOS/Linux:
        ```bash
        source venv/bin/activate
        ```
4.  **Install Dependencies**:
    ```bash
    pip install playwright langdetect
    ```
5.  **Install Playwright Browsers**:
    ```bash
    playwright install
    ```
    This command downloads the necessary browser binaries (Chromium, Firefox, WebKit) required by Playwright.

## Configuration

1.  **Copy the Sample Configuration**:
    ```bash
    copy sample_config.py config.py  # On Windows
    # Or
    cp sample_config.py config.py    # On macOS/Linux
    ```
    *Note: The original `sample_config.ts` was ported to `config.py`.*

2.  **Edit `config.py`**:
    Open `config.py` in a text editor and fill in your LinkedIn credentials and job search/application preferences.
    *   `LINKEDIN_EMAIL`: Your LinkedIn email address.
    *   `LINKEDIN_PASSWORD`: Your LinkedIn password.
    *   `KEYWORDS`: Keywords to search for in job titles (e.g., "python developer").
    *   `LOCATION`: Location to search for jobs (e.g., "New York", "Remote").
    *   `WORKPLACE`: Preferences for On-Site, Remote, Hybrid.
    *   `JOB_TITLE`: Regular expression to match desired job titles.
    *   `JOB_DESCRIPTION`: Regular expression to match or exclude certain terms in job descriptions.
    *   `JOB_DESCRIPTION_LANGUAGES`: List of languages for job descriptions (e.g., ["english", "spanish"] or ["any"]).
    *   `PHONE`, `CV_PATH`, `COVER_LETTER_PATH`, `HOME_CITY`: Personal details and file paths for documents.
    *   `YEARS_OF_EXPERIENCE`, `LANGUAGE_PROFICIENCY`, `BOOLEANS`, `TEXT_FIELDS`, `MULTIPLE_CHOICE_FIELDS`: Data to fill in the application forms.
    *   `SINGLE_PAGE`: Set to `True` or `False` depending on whether you want to reuse a single page for applications (might be less reliable) or create a new page for each application.

## Usage

1.  **Ensure your virtual environment is activated**.
2.  **Navigate to the project directory** in your terminal.
3.  **Run the script**:
    *   To run the bot and fill the forms **without submitting**:
        ```bash
        python main.py
        ```
    *   To run the bot and **submit** the applications:
        ```bash
        python main.py SUBMIT
        ```
4.  **Manual Steps**: The script will attempt to log in automatically. If prompted for 2FA or if a Captcha appears, you will need to complete these steps manually. The script will wait for your input after the login step before proceeding to search for jobs.

## Important Notes

*   **LinkedIn's Terms of Service**: Please use this bot responsibly and in accordance with LinkedIn's Terms of Service. Excessive or aggressive automation might lead to your account being restricted or banned.
*   **Browser Visibility**: The script launches a visible browser window (`headless=False`) by default. You can change this in `main.py` if you prefer a headless run, but debugging might be harder.
*   **Selectors**: The script relies on CSS selectors to find elements on the LinkedIn website. If LinkedIn updates its UI, the selectors in `selectors.py` might need to be updated.
*   **Errors**: The bot tries to handle common errors, but unexpected changes on the website or network issues can cause failures. Monitor the console output for errors.

## Project Structure

*   `main.py`: The main script that orchestrates the entire process.
*   `config.py`: Contains all user-specific configuration settings.
*   `selectors.py`: Stores CSS selectors for various elements on LinkedIn pages.
*   `login.py`: Handles the LinkedIn login process.
*   `fetch_jobs.py`: Contains logic for searching and filtering job listings.
*   `apply.py`: Orchestrates the application process for a single job.
*   `apply_form/`: A package containing modules for filling different types of application form fields.
    *   `fill_fields.py`: Main orchestrator for filling fields.
    *   `fill_boolean.py`: Fills checkboxes and boolean radio/selects.
    *   `fill_multiple_choice_fields.py`: Fills multi-option select dropdowns.
    *   `fill_text_fields.py`: Fills text inputs and textareas.
    *   `insert_home_city.py`: Inserts home city.
    *   `insert_phone.py`: Inserts phone number.
    *   `uncheck_follow_company.py`: Unchecks the 'Follow company' box.
    *   `upload_docs.py`: Uploads CV and Cover Letter.
    *   `wait_for_no_error.py`: Waits for error messages to disappear.
    *   `click_next_button.py`: Clicks the 'Next' or 'Review' button.
*   `utils.py`: Contains utility functions like asking the user for input and waiting.
