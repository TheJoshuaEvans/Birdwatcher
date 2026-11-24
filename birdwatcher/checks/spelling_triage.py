"""
Spelling triage: asking a model about words the spelling check flagged.

The spelling check cannot tell a typo from a course's own term, and often has
several suggestions or none. A model reads each word in its line and rules:
a typo (with the correction) or a word to keep (a name, term or code name that
belongs in the course's word list). A typo verdict becomes an ordinary Fix;
nothing here writes to the course.

Only spelling errors are asked about (asks_ai): warnings and info have a fix
from the dictionary. A verdict belongs to a word in its line, not to the
word: the same misspelling can mean different things in different places. A
line that is edited no longer has one.

Nothing here calls a model on its own: the caller asks, with a function that
sends one conversation (see triage), only when the user asks for it.

Joshua Evans, 2026-11-23 (written with Claude Opus 5.5)
"""

import json
import logging
import re
from dataclasses import dataclass, field

from birdwatcher.checks.spelling import (
    fixable_in_place,
    line_at,
    same_case,
    word_of,
    words_in,
)
from birdwatcher.core.ai import AiError
from birdwatcher.core.course_store import read_entries, write_entries
from birdwatcher.core.findings import Fix, Severity

TYPO, KEEP = "typo", "keep"  # the verdicts a model can give
WORDS_PER_REQUEST = 40  # questions (a word in its line) asked in one request
CONTEXT_CHARS = 160  # at most this much of a word's line is sent with it
CHARS_PER_TOKEN = 4  # a rough rule for estimating tokens from text
ANSWER_TOKENS_PER_WORD = 30  # a rough allowance for one verdict in an answer
VERDICT_FILE = "spelling-verdicts.json"

RULES = """\
You check spelling in the course materials of a college programming course, \
written for beginning programmers. A spell checker flagged the words below. \
It does not know names, technical terms or code, so many flagged words are \
correct.

The items are numbered. Judge each word by its own line only (the same word \
can mean different things in different lines), and give one verdict:
- "typo": misspelled. Give the correction exactly as it belongs in that \
line, with any capitals it needs. British spellings are typos: the course \
uses American English.
- "keep": spelled correctly, or misspelled on purpose. A name, product, \
library, technical term, abbreviation or name from code. It belongs in the \
course's word list.

Answer with JSON only, no other text:
{"verdicts": [{"id": <the item's number>, "word": "<the word as given>", \
"verdict": "typo" or "keep", "correction": "<the correction>" or null, \
"reason": "<at most 12 words>"}]}
Give exactly one verdict for every item."""

RETRY = "That answer could not be used: {error} Answer again with the JSON only."
FENCED = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Question:
    """
    A flagged word in its line, to ask about.

    Attributes:
        word (str): The word as written there, e.g. "Sonet".
        path (str): The file it is in (the first, when the same line is in
            several), relative to the course root.
        context (str): Its line, stripped and cut to at most CONTEXT_CHARS
            characters around the word.
    """

    word: str
    path: str
    context: str

    @property
    def key(self):
        """tuple[str, str]: (the word lowercased, the context): what a
        verdict on it is found by."""
        return (self.word.lower(), self.context)


@dataclass(frozen=True)
class Verdict:
    """
    A model's ruling on a word in its line.

    Attributes:
        word (str): The word, lowercased.
        context (str): The line it rules on, as in Question.context.
        kind (str): TYPO or KEEP.
        correction (str | None): For a typo, the word as it should be written
            (with any capitals it needs, e.g. "Papert"); None for KEEP.
        reason (str): A short explanation for people.
        model (str): The model that gave it.
    """

    word: str
    context: str
    kind: str
    correction: str | None
    reason: str
    model: str

    @property
    def key(self):
        """tuple[str, str]: (word, context), as Question.key."""
        return (self.word, self.context)


@dataclass(frozen=True)
class Estimate:
    """
    What asking some questions will cost, before anything is sent.

    Attributes:
        questions (int): Questions to ask (words in their lines).
        requests (int): Requests needed (WORDS_PER_REQUEST per request).
        tokens (int): Rough total of tokens read and written.
    """

    questions: int
    requests: int
    tokens: int


@dataclass(frozen=True)
class TriageResult:
    """
    The outcome of asking about some words.

    Attributes:
        verdicts (dict[tuple[str, str], Verdict]): Valid verdicts by
            Question.key.
        unanswered (list[str]): The lowercased word of each question with no
            valid verdict, in the order asked.
        input_tokens (int): Tokens read, as the provider reported them (0 when
            it reported none).
        output_tokens (int): Tokens written, likewise.
        error (str | None): Why asking stopped early (a failure that would
            repeat, such as a refused key or a rate limit), or None. Verdicts
            from requests before it are kept.
        failures (list[str]): Requests given up after failing twice while
            asking carried on, each as "request N of M: <reason>".
        stopped (bool): Whether asking was stopped on request (should_stop)
            before every request was sent.
    """

    verdicts: dict[tuple[str, str], Verdict]
    unanswered: list[str]
    input_tokens: int
    output_tokens: int
    error: str | None = None
    failures: list[str] = field(default_factory=list)
    stopped: bool = False


class VerdictError(Exception):
    """A model's answer holds no readable verdicts; the message says why, in
    words the model can act on when it is asked again."""


def asks_ai(finding):
    """
    Whether the AI is asked about a finding: only spelling errors, the words
    with no suggestion or several, which the dictionary cannot fix. Warnings
    and info have a fix of their own (or need none), so they are never sent.

    Args:
        finding (Finding): Any finding.

    Returns:
        bool: True for a spelling finding of severity ERROR.
    """
    return word_of(finding) is not None and finding.severity == Severity.ERROR


def questions_for(course_dir, findings):
    """
    The questions to ask about some findings: one per finding, in order.

    Args:
        course_dir (Path): The course's root folder.
        findings (Iterable[Finding]): Any findings; only spelling findings
            with a line are used.

    Returns:
        list[Question]: Each finding's word in its line (empty context when
            the file or line is gone).
    """
    return [
        Question(word_of(finding), finding.path, context_for(course_dir, finding))
        for finding in findings
        if word_of(finding) is not None and finding.line is not None
    ]


def context_for(course_dir, finding):
    """
    A spelling finding's line, as a question sends it (Question.context).

    Args:
        course_dir (Path): The course's root folder.
        finding (Finding): A spelling finding.

    Returns:
        str: Its line, stripped and cut around the word; "" when the finding
            has no line or word, or the file or line is gone.
    """
    word = word_of(finding)
    if word is None or finding.line is None:
        return ""
    return _context(course_dir / finding.path, finding.line, word)


def verdict_for(course_dir, finding, verdicts):
    """
    The verdict on a spelling finding's word in its line, as it is now.

    Args:
        course_dir (Path): The course's root folder.
        finding (Finding): Any finding.
        verdicts (Mapping[tuple[str, str], Verdict]): Verdicts by key.

    Returns:
        Verdict | None: None for another check's finding, or when the word
            has no verdict in that line (never asked, or the line changed).
    """
    key = verdict_key(course_dir, finding)
    return None if key is None else verdicts.get(key)


def verdict_key(course_dir, finding):
    """
    The key a verdict on a spelling finding is found by, as its line is now
    (what verdict_for looks up; for callers that keep keys between files'
    changes).

    Args:
        course_dir (Path): The course's root folder.
        finding (Finding): Any finding.

    Returns:
        tuple[str, str] | None: As Question.key; None for another check's
            finding.
    """
    word = word_of(finding)
    if word is None:
        return None
    return (word.lower(), context_for(course_dir, finding))


def estimate(questions):
    """
    What asking about these questions will cost, without asking.

    Args:
        questions (Sequence[Question]): The questions.

    Returns:
        Estimate: The questions, requests and rough tokens (the prompts'
            length plus an allowance for each answer, by CHARS_PER_TOKEN). No
            questions cost nothing.
    """
    batches = _batches(questions)
    sent = sum(
        len(message["content"]) for batch in batches for message in messages_for(batch)
    )
    tokens = sent // CHARS_PER_TOKEN + ANSWER_TOKENS_PER_WORD * len(questions)
    return Estimate(len(questions), len(batches), tokens)


def messages_for(questions):
    """
    The conversation that asks about some words.

    Args:
        questions (Sequence[Question]): The words, at most WORDS_PER_REQUEST.

    Returns:
        list[dict[str, str]]: A system message with the rules (the same for
            every request) and a user message listing the questions,
            numbered from 1, each word with its file and line.
    """
    listed = "\n".join(
        f'{number}. "{question.word}" in {question.path}: {question.context}'
        for number, question in enumerate(questions, start=1)
    )
    return [
        {"role": "system", "content": RULES},
        {"role": "user", "content": f"Words to judge:\n{listed}"},
    ]


def read_verdicts(text, questions, model):
    """
    The verdicts in a model's answer.

    The answer is JSON, possibly wrapped in a Markdown code fence or a
    sentence: {"verdicts": [{"id", "word", "verdict", "correction",
    "reason"}]} or the bare list. An entry answers the question its id
    numbers (from 1, as messages_for numbers them; a number in a string
    counts too), when that question's word is the entry's word, ignoring
    letter case; an entry without an id answers the one question with its
    word, if only one has it. Other entries are dropped, and so are those
    whose verdict is not TYPO or KEEP, or whose typo's correction is
    missing, blank or the word itself unchanged.

    Args:
        text (str): The model's answer.
        questions (Sequence[Question]): The questions, in the order asked.
        model (str): The model that answered, recorded on each verdict.

    Returns:
        dict[tuple[str, str], Verdict]: By Question.key (the first entry for
            a question wins).

    Raises:
        VerdictError: The answer holds no JSON, or JSON of another shape.
    """
    data = _json_in(text)
    entries = data.get("verdicts") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise VerdictError('It was not {"verdicts": [...]}.')
    by_word = {}
    for question in questions:
        by_word.setdefault(question.word.lower(), []).append(question)
    verdicts = {}
    for entry in entries:
        question = _question_answered(entry, questions, by_word)
        verdict = None if question is None else _verdict(entry, question, model)
        if verdict is not None and verdict.key not in verdicts:
            verdicts[verdict.key] = verdict
    return verdicts


def triage(questions, ask, on_request=None, should_stop=None):
    """
    Ask a model about some words, WORDS_PER_REQUEST at a time.

    Before each request, should_stop() is asked: True stops asking (a request
    already sent is never interrupted), leaving the remaining words
    unanswered. Then on_request(number, total) is told which request is
    being sent, from 1.

    An answer with no readable verdicts is sent back once, with what was
    wrong, before its words count as unanswered. A request that fails in a
    way another try may avoid (AiError.retry_may_help) is sent again once;
    failing again, its words count as unanswered, the reason goes to
    failures, and asking carries on with the next request. Any other
    failure stops asking.

    Args:
        questions (Sequence[Question]): The words to ask about.
        ask (Callable[[list[dict[str, str]]], Reply]): Sends one
            conversation and returns the model's answer (core.ai.chat with a
            connection). Raises AiError when it fails.
        on_request (Callable[[int, int], object] | None): Told each request's
            number and the number of requests, before it is sent.
        should_stop (Callable[[], bool] | None): Asked before each request;
            None never stops.

    Returns:
        TriageResult: The verdicts, the words left unanswered (a skipped
            request's words, and on a stop all the remaining words), the
            tokens used, the skipped requests' reasons and any stop.
    """
    verdicts, unanswered, failures = {}, [], []
    tokens = [0, 0]  # read, written
    error, stopped = None, False
    should_stop = should_stop or (lambda: False)
    on_request = on_request or (lambda number, total: None)

    def asked(messages):
        reply = ask(messages)
        tokens[0] += reply.input_tokens or 0
        tokens[1] += reply.output_tokens or 0
        return reply

    batches = _batches(questions)
    for number, batch in enumerate(batches):
        where = f"request {number + 1} of {len(batches)}"
        if should_stop():
            _log.info("stopped before %s", where)
            stopped = True
            unanswered += [q.word.lower() for later in batches[number:] for q in later]
            break
        on_request(number + 1, len(batches))
        words = ", ".join(question.word for question in batch)
        _log.info("%s: %d words: %s", where, len(batch), words)
        try:
            found = _ask_batch_twice(batch, asked, where)
        except AiError as failure:
            if failure.retry_may_help:  # failed twice: skip it, carry on
                _log.warning("%s failed again, skipped: %s", where, failure)
                failures.append(f"{where}: {failure}")
                found = {}
            else:
                _log.warning("%s failed, asking stops: %s", where, failure)
                error = str(failure)
                unanswered += [
                    q.word.lower() for later in batches[number:] for q in later
                ]
                break
        verdicts.update(found)
        unanswered += [q.word.lower() for q in batch if q.key not in found]
    _log.info(
        "triage done: %d verdicts, %d words unanswered%s",
        len(verdicts),
        len(unanswered),
        f": {', '.join(unanswered)}" if unanswered else "",
    )
    return TriageResult(
        verdicts, unanswered, tokens[0], tokens[1], error, failures, stopped
    )


def ai_fix(course_dir, finding, verdict):
    """
    The fix a typo verdict gives a spelling finding.

    A fix is offered only where the spelling check itself could fix a word:
    in prose (not code: renaming one use of a name breaks code), standing
    alone, and the first occurrence of its text on the line. The correction
    takes the word's capital when the correction is all lowercase;
    otherwise it is used as given.

    Args:
        course_dir (Path): The course's root folder.
        finding (Finding): A spelling finding.
        verdict (Verdict | None): The verdict on its word.

    Returns:
        Fix | None: The replacement on the finding's line, or None (no
            verdict, a KEEP verdict, another check's finding, the word in
            code, or the file or line gone).
    """
    word = word_of(finding)
    if word is None or finding.line is None:
        return None
    if verdict is None or verdict.kind != TYPO or not verdict.correction:
        return None
    found = line_at(course_dir, finding.path, finding.line)
    if found is None:
        return None
    line, code_spans = found
    located = next((w for w in words_in(line) if w.text == word), None)
    if located is None or not fixable_in_place(located, line, code_spans):
        return None
    correction = verdict.correction
    if correction.islower():
        correction = same_case(word, correction)
    return Fix(finding.line, word, correction)


def load_verdicts(path, course_dir):
    """
    The verdicts remembered for one course folder.

    Args:
        path (Path): The verdict file.
        course_dir (Path): The course folder.

    Returns:
        dict[tuple[str, str], Verdict]: By key; unreadable entries, and
            entries without their line, are left out. Empty when there are
            none.
    """
    verdicts = {}
    for entry in read_entries(path, course_dir):
        try:
            verdict = Verdict(
                word=entry["word"],
                context=entry["context"],
                kind=entry["kind"],
                correction=entry["correction"],
                reason=entry["reason"],
                model=entry["model"],
            )
        except (KeyError, TypeError):
            continue
        verdicts[verdict.key] = verdict
    return verdicts


def save_verdicts(path, course_dir, verdicts):
    """
    Remember the verdicts for one course folder, replacing what was
    remembered for it before; other folders' verdicts are kept.

    Args:
        path (Path): The verdict file.
        course_dir (Path): The course folder.
        verdicts (Mapping[tuple[str, str], Verdict]): Everything to remember.
    """
    entries = [
        {
            "word": verdict.word,
            "context": verdict.context,
            "kind": verdict.kind,
            "correction": verdict.correction,
            "reason": verdict.reason,
            "model": verdict.model,
        }
        for verdict in verdicts.values()
    ]
    write_entries(path, course_dir, entries)


def _batches(questions):
    return [
        list(questions[start : start + WORDS_PER_REQUEST])
        for start in range(0, len(questions), WORDS_PER_REQUEST)
    ]


def _ask_batch_twice(batch, ask, where):
    """_ask_batch, sent once more after a failure another try may avoid."""
    try:
        return _ask_batch(batch, ask, where)
    except AiError as failure:
        if not failure.retry_may_help:
            raise
        _log.warning("%s failed, asking again: %s", where, failure)
    return _ask_batch(batch, ask, where)


def _ask_batch(batch, ask, where):
    """Verdicts for one batch: the answer, or one retry after an unreadable
    one (then none). AiError passes through. `where` names the request in
    the log."""
    messages = messages_for(batch)
    reply = ask(messages)
    try:
        return _read_logged(reply, batch, where)
    except VerdictError as error:
        _log.warning(
            "%s: unusable answer (%s), asking again:\n%s", where, error, reply.text
        )
        messages = [
            *messages,
            {"role": "assistant", "content": reply.text},
            {"role": "user", "content": RETRY.format(error=error)},
        ]
    reply = ask(messages)
    try:
        return _read_logged(reply, batch, where)
    except VerdictError as error:
        _log.warning(
            "%s: unusable again (%s), giving up:\n%s", where, error, reply.text
        )
        return {}


def _read_logged(reply, batch, where):
    """read_verdicts, logging how many of the answer's verdicts were usable."""
    verdicts = read_verdicts(reply.text, batch, reply.model)
    _log.info("%s: %d usable verdicts from %s", where, len(verdicts), reply.model)
    return verdicts


def _context(file, number, word):
    """The word's line, stripped and cut around the word to CONTEXT_CHARS."""
    try:
        lines = file.read_text(encoding="utf-8", errors="replace").split("\n")
    except OSError:
        return ""
    if not 1 <= number <= len(lines):
        return ""
    line = lines[number - 1].strip()
    if len(line) <= CONTEXT_CHARS:
        return line
    column = max(line.find(word), 0)
    start = max(0, column - (CONTEXT_CHARS - len(word)) // 2)
    return line[start : start + CONTEXT_CHARS]


def _json_in(text):
    """The JSON in an answer: the whole text, a fenced block, or the span
    from the first { or [ to the last } or ]."""
    candidates = [text, *FENCED.findall(text)]
    for opening, closing in ("{}", "[]"):
        start, end = text.find(opening), text.rfind(closing)
        if 0 <= start < end:
            candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except ValueError:
            continue
    raise VerdictError("It held no JSON.")


def _question_answered(entry, questions, by_word):
    """The question an entry answers (see read_verdicts), or None."""
    if not isinstance(entry, dict) or not isinstance(entry.get("word"), str):
        return None
    word = entry["word"].strip().lower()
    number = entry.get("id")
    if isinstance(number, str) and number.strip().isdigit():
        number = int(number)
    if isinstance(number, int) and not isinstance(number, bool):
        if 1 <= number <= len(questions):
            question = questions[number - 1]
            return question if question.word.lower() == word else None
        return None
    same_word = by_word.get(word, [])
    return same_word[0] if len(same_word) == 1 else None


def _verdict(entry, question, model):
    """An entry as the Verdict on its question, or None when unusable."""
    kind = entry.get("verdict")
    if not isinstance(kind, str):
        return None
    kind = kind.strip().lower()
    reason = entry.get("reason")
    reason = reason.strip() if isinstance(reason, str) else ""
    word, context = question.key
    if kind == KEEP:
        return Verdict(word, context, KEEP, None, reason, model)
    correction = entry.get("correction")
    if kind != TYPO or not isinstance(correction, str):
        return None
    correction = correction.strip()
    if not correction or correction == question.word:
        return None
    return Verdict(word, context, TYPO, correction, reason, model)
