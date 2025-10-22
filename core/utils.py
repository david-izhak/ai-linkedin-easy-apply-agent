import time

def ask_user(prompt: str) -> str:
    """
    Asks the user for input and returns the response.
    """
    print(prompt, end="")
    return input()


def wait(time_ms: int):
    """
    Waits for a specified amount of time in milliseconds.
    """
    time.sleep(time_ms / 1000.0)
