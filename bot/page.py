"""LimeSurvey page model: what a survey page contains and what must be posted back."""
from __future__ import annotations

import urllib.parse

from bot import dom

# The organisation gate ("Вы оставляете оценку деятельности...") is a SigmaPro
# add-on shown once per fresh session, before the LimeSurvey engine itself.
ORG_GATE_CLASS = "ap-org-welcome-button"
COMPLETED_CLASS = "completed-wrapper"
QUESTION_CLASS = "question-container"
QUESTION_TEXT_CLASS = "question-text"
WELCOME_ID = "welcome-container"
SUBMIT_BUTTON_ID = "ls-button-submit"


class Option:
    """One radio answer, together with the text of its visible label."""

    __slots__ = ("name", "value", "input_id", "label")

    def __init__(self, name: str, value: str, input_id: str, label: str) -> None:
        self.name = name
        self.value = value
        self.input_id = input_id
        self.label = label

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Option {self.name}={self.value!r} {self.label!r}>"


class MatrixRow:
    """One line of a matrix question: its wording plus the options on that line.

    Indexable, so callers that only care about picking a column can treat it as
    the plain list of options it used to be.
    """

    __slots__ = ("label", "options")

    def __init__(self, label: str, options: list) -> None:
        self.label = label
        self.options = options

    def __len__(self) -> int:
        return len(self.options)

    def __getitem__(self, index):
        return self.options[index]


class Question:
    def __init__(self, node: dom.Node, labels: dict) -> None:
        self._node = node
        self._labels = labels
        text_node = node.find(class_name=QUESTION_TEXT_CLASS)
        self.text = text_node.text() if text_node else ""

    @property
    def is_matrix(self) -> bool:
        return self._node.find("table") is not None

    def options(self) -> list:
        return [self._to_option(node) for node in self._node.find_all("input", type="radio")]

    def matrix_rows(self) -> list:
        """Rows of a matrix question, in the page's own order."""
        rows = []
        for row in self._node.find_all("tr"):
            radios = row.find_all("input", type="radio")
            if not radios:
                continue
            header = row.find("th")
            rows.append(
                MatrixRow(
                    header.text() if header is not None else "",
                    [self._to_option(node) for node in radios],
                )
            )
        return rows

    def _to_option(self, node: dom.Node) -> Option:
        input_id = node.get("id", "")
        return Option(
            name=node.get("name", ""),
            value=node.get("value", ""),
            input_id=input_id,
            label=self._labels.get(input_id, ""),
        )


class SurveyPage:
    def __init__(self, url: str, html: str) -> None:
        self.url = url
        self.html = html
        self.root = dom.parse(html)
        self._labels = {
            label.get("for"): label.text()
            for label in self.root.find_all("label")
            if label.get("for")
        }
        self._form = self.root.find("form")

    # ---------- what kind of page is this ----------
    @property
    def is_completed(self) -> bool:
        return self.root.find(class_name=COMPLETED_CLASS) is not None

    @property
    def is_welcome(self) -> bool:
        return self.root.find(id=WELCOME_ID) is not None

    @property
    def org_gate_url(self):
        """Absolute URL of the "Продолжить" link on the organisation gate, if shown."""
        link = self.root.find("a", class_name=ORG_GATE_CLASS)
        if link is None or not link.get("href"):
            return None
        return urllib.parse.urljoin(self.url, link.get("href"))

    @property
    def has_form(self) -> bool:
        return self._form is not None

    # ---------- what to post back ----------
    @property
    def action_url(self) -> str:
        action = self._form.get("action", "") if self._form else ""
        return urllib.parse.urljoin(self.url, action) if action else self.url

    def base_fields(self) -> dict:
        """Hidden state LimeSurvey expects back verbatim (post key, step, relevance...).

        Disabled inputs are skipped: a browser never submits those, and the
        `java*` mirrors of each answer field are all disabled.
        """
        fields = {}
        if self._form is None:
            return fields
        for node in self._form.find_all("input"):
            name = node.get("name")
            if not name or "disabled" in node.attrs:
                continue
            if (node.get("type") or "text").lower() != "hidden":
                continue
            fields[name] = node.get("value", "")
        return fields

    @property
    def submit_move(self) -> str:
        """Value of the "Далее"/"Отправить" button -- LimeSurvey routes on it."""
        button = self.root.find("button", id=SUBMIT_BUTTON_ID)
        if button is not None and button.get("value"):
            return button.get("value")
        return "movenext"

    def questions(self) -> list:
        return [
            Question(node, self._labels)
            for node in self.root.find_all(class_name=QUESTION_CLASS)
        ]

    def rejected_questions(self) -> list:
        """Texts of the questions LimeSurvey refused to accept.

        When a page comes back rejected (a mandatory answer missing, say), the
        engine re-renders it with `input-error` on the offending containers --
        that is the only reliable signal, as the explanatory message sits in a
        sibling element that is not always present.
        """
        texts = []
        for node in self.root.find_all(class_name="input-error"):
            text_node = node.find(class_name=QUESTION_TEXT_CLASS)
            if text_node is not None:
                texts.append(text_node.text())
        return texts
