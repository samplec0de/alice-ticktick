"""Expected response strings for E2E assertions.

Duplicated from alice_ticktick.dialogs.responses to avoid importing the main
package (which pulls in aliceio and other heavy dependencies not needed for E2E).
"""

WELCOME = "Слушаю!"
UNKNOWN = "Команда не распознана. Скажите «помощь», чтобы узнать, что я умею."
DELETE_CANCELLED = "Удаление отменено."
TASK_NAME_REQUIRED = "Как назвать задачу? Скажите название."
DURATION_MISSING_START_TIME = "Во сколько начинается? Скажите время."
GOODBYE = "До встречи! Удачного дня!"
