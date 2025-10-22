from playwright.async_api import Page, ElementHandle


async def change_text_input(
    container: Page | ElementHandle, selector: str, value: str
) -> None:
    """
    Changes the text of an input field. If a selector is provided,
    it finds the element within the container.
    Otherwise, the container itself is treated as the input element.
    """
    input_element: ElementHandle  # Declare the variable and its expected type

    if selector:
        # query_selector can return None, so we use a temporary variable
        found_element = await container.query_selector(selector)
        if not found_element:
            raise ValueError(f"Could not find element with selector {selector}")
        input_element = found_element
    else:
        # If no selector is provided, the container MUST be an ElementHandle.
        if not isinstance(container, ElementHandle):
            raise TypeError(
                "If no selector is provided, the container must be an ElementHandle, not a Page."
            )
        input_element = container  # mypy now knows container is an ElementHandle

    # Get the current value of the input
    previous_value = await input_element.input_value()

    # Only change the value if it's different
    if previous_value != value:
        # Click the input 3 times to select all text (similar to Ctrl+A)
        await input_element.click(click_count=3)
        # Type the new value
        await input_element.type(value)
