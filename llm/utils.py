def format_prompt(template: str, **kwargs: str) -> str:
    """
    Lightweight string formatter that replaces `{key}` placeholders without
    interpreting other braces in the template.
    """
    result = template
    for key, value in kwargs.items():
        if not isinstance(value, str):
            value = str(value)
        result = result.replace(f"{{{key}}}", value)
    return result

