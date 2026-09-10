"""Answer rules for this specific survey (see readme.md for the source of truth)."""

# Questions where a fixed answer must be picked, matched by a substring of the
# question text; the answer is matched against the text of the answer's label.
FIXED_TEXT_RULES = [
    {
        "match": "Укажите вид организации",
        "answer": "Культурно-досуговое учреждение",
    },
    {
        "match": "удовлетворены работой учреждения культуры в целом",
        "answer": "Полностью удовлетворен",
    },
]

# Matrix (table) question: 0-based column index for the "5" rating.
MATRIX_DEFAULT_COLUMN = 4
# Last row of the matrix: randomly pick between "5" and "затрудняюсь ответить".
MATRIX_LAST_ROW_COLUMNS = (4, 5)


def find_fixed_answer(question_text: str):
    for rule in FIXED_TEXT_RULES:
        if rule["match"] in question_text:
            return rule["answer"]
    return None


def match_option(options: list, answer_text: str):
    """Finds the option whose label matches `answer_text`.

    Prefers an exact label match, so a rule like "Полностью удовлетворен" can
    never be satisfied by a longer neighbouring option.
    """
    for option in options:
        if option.label.strip() == answer_text:
            return option
    for option in options:
        if answer_text in option.label:
            return option
    return None
