from playwright.async_api import Page

from core.selectors import selectors


async def upload_docs(page: Page, cv_path: str, cover_letter_path: str) -> None:
    """
    Uploads CV and Cover Letter if the corresponding upload fields are present.
    """
    # Find all document upload divs
    doc_divs = await page.query_selector_all(selectors["document_upload"])

    for doc_div in doc_divs:
        # Find the label and input elements within the div
        label_element = await doc_div.query_selector(selectors["document_upload_label"])
        input_element = await doc_div.query_selector(selectors["document_upload_input"])

        if label_element and input_element:
            # Get the text content of the label to determine the type of document
            label_text = await label_element.inner_text()

            if "resume" in label_text.lower() and cv_path:
                await input_element.set_input_files(cv_path)
            elif "cover" in label_text.lower() and cover_letter_path:
                await input_element.set_input_files(cover_letter_path)
