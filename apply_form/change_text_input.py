import re
from playwright.async_api import Page, ElementHandle
import logging

logger = logging.getLogger(__name__)

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

    # Получаем текущее значение
    previous_value = await input_element.input_value()
    logger.debug("Previous value: %s", previous_value)

    # Нормализация для корректного сравнения (убираем пробелы, тире, плюсы для проверки)
    # Если вы уверены, что форматы идентичны, можно оставить простое сравнение
    def normalize(text):
        return re.sub(r'\D', '', text)

    # Проверяем, нужно ли менять значение
    if normalize(previous_value) != normalize(value):
        # Используем fill вместо type.
        # fill вызывает событие input, change и предварительно очищает поле.
        await input_element.fill(value)
