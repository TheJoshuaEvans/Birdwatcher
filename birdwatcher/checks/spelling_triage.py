"""
Spelling triage: asking a model about words the spelling check flagged.

The spelling check cannot tell a typo from a course's own term, and often has
several suggestions or none. A model reads each word in its line and rules:
a typo (with the correction) or a word to keep (a name, term or code name that
belongs in the course's word list). A typo verdict becomes an ordinary Fix;
nothing here writes to the course.

Nothing here calls a model on its own: the caller asks, with a function that
sends one conversation (see triage), only when the user asks for it.

Joshua Evans, 2026-11-23 (written with Claude Opus 5.5)
"""

import json
import re
from dataclasses import dataclass

from birdwatcher.checks.spelling import (
    fixable_in_place,
    line_at,
    same_case,
    word_of,
    words_in,
)
from birdwatcher.core.ai import AiError
from birdwatcher.core.course_store import read_entries, write_entries
from birdwatcher.core.findings import Fix

TYPO, KEEP = "typo", "keep"  # the verdicts a model can give
WORDS_PER_REQUEST = 40  # words asked about in one request
CONTEXT_CHARS = 160  # at most this much of a word's line is sent with it
CHARS_PER_TOKEN = 4  # a rough rule for estimating tokens from text
ANSWER_TOKENS_PER_WORD = 30  # a rough allowance for one verdict in an answer
VERDICT_FILE = "spelling-verdicts.json"

RULES = """\
You check spelling in the course materials of a college programming course, \
written for beginning programmers. A spell checker flagged the words below. \
It does not know names, technical terms or code, so many flagged words are \
correct.

Judge each word by the line it appears on, and give one verdict:
- "typo": misspelled. Give the correction exactly as it belongs in that \
line, with any capitals it needs. British spellings are typos: the course \
uses American English.
- "keep": spelled correctly. A name, product, library, technical term, \
abbreviation or name from code. It belongs in the course's word list.

Answer with JSON only, no other text:
{"verdicts": [{"word": "<the word as given>", "verdict": "typo" or "keep", \
"correction": "<the correction>" or null, "reason": "<at most 12 words>"}]}
Give exactly one verdict for every word."""

RETRY = "That answer could not be used: {error} Answer again with the JSON only."
FENCED = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


@dataclass(frozen=True)
class Question:
    """
    A flagged word to ask about, with where it was first found.

    Attributes:
        word (str): The word as written there, e.g. "Sonet".
        path (str): The file it is in, relative to the course root.
        context (str): Its line, stripped and cut to at most CONTEXT_CHARS
            characters around the word.
    """

    word: str
    path: str
    context: str


@dataclass(frozen=True)
class Verdict:
    """
    A model's ruling on a word.

    Attributes:
        word (str): The word, lowercased.
        kind (str): TYPO or KEEP.
        correction (str | None): For a typo, the word as it should be written
            (with any capitals it needs, e.g. "Papert"); None for KEEP.
        reason (str): A short explanation for people.
        model (str): The model that gave it.
    """

    word: str
    kind: str
    correction: str | None
    reason: str
    model: str


@dataclass(frozen=True)
class Estimate:
    """
    What asking about some words will cost, before anything is sent.

    Attributes:
        words (int): Distinct words to ask about.
        requests (int): Requests needed (WORDS_PER_REQUEST per request).
        tokens (int): Rough total of tokens read and written.
    """

    words: int
    requests: int
    tokens: int


@dataclass(frozen=True)
class TriageResult:
    """
    The outcome of asking about some words.

    Attributes:
        verdicts (dict[str, Verdict]): Valid verdicts by lowercased word.
        unanswered (list[str]): Lowercased words asked about with no valid
            verdict, in the order asked.
        input_tokens (int): Tokens read, as the provider reported them (0 when
            it reported none).
        output_tokens (int): Tokens written, likewise.
        error (str | None): Why asking stopped early (the provider failed),
            or None. Verdicts from requests before the failure are kept.
    """

    verdicts: dict[str, Verdict]
    unanswered: list[str]
    input_tokens: int
    output_tokens: int
    error: str | None = None


class VerdictError(Exception):
    """A model's answer holds no readable verdicts; the message says why, in
    words the model can act on when it is asked again."""


def questions_for(course_dir, findings):
    """
    The questions to ask about some findings: one per distinct word.

    Args:
        course_dir (Path): The course's root folder.
        findings (Iterable[Finding]): Any findings; only spelling findings
            with a line are used.

    Returns:
        list[Question]: One per word, ignoring letter case, for its first
            finding in the order given, whose file supplies the context
            (empty context when the file or line is gone).
    """
    questions = {}
    for finding in findings:
        word = word_of(finding)
        if word is None or finding.line is None or word.lower() in questions:
            continue
        context = _context(course_dir / finding.path, finding.line, word)
        questions[word.lower()] = Question(word, finding.path, context)
    return list(questions.values())


def estimate(questions):
    """
    What asking about these questions will cost, without asking.

    Args:
        questions (Sequence[Question]): The questions.

    Returns:
        Estimate: The words, requests and rough tokens (the prompts' length
            plus an allowance for each answer, by CHARS_PER_TOKEN). No
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
            every request) and a user message listing each word with its file
            and line.
    """
    listed = "\n".join(
        f'- "{question.word}" in {question.path}: {question.context}'
        for question in questions
    )
    return [
        {"role": "system", "content": RULES},
        {"role": "user", "content": f"Words to judge:\n{listed}"},
    ]


def read_verdicts(text, questions, model):
    """
    The verdicts in a model's answer.

    The answer is JSON, possibly wrapped in a Markdown code fence or a
    sentence: {"verdicts": [{"word", "verdict", "correction", "reason"}]} or
    the bare list. An entry is dropped when its word was not asked about,
    its verdict is not TYPO or KEEP, or a typo's correction is missing, blank
    or the word itself unchanged.

    Args:
        text (str): The model's answer.
        questions (Sequence[Question]): The words asked about.
        model (str): The model that answered, recorded on each verdict.

    Returns:
        dict[str, Verdict]: By lowercased word (the first entry for a word
            wins).

    Raises:
        VerdictError: The answer holds no JSON, or JSON of another shape.
    """
    data = _json_in(text)
    entries = data.get("verdicts") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise VerdictError('It was not {"verdicts": [...]}.')
    asked = {question.word.lower() for question in questions}
    verdicts = {}
    for entry in entries:
        verdict = _verdict(entry, model)
        if verdict and verdict.word in asked and verdict.word not in verdicts:
            verdicts[verdict.word] = verdict
    return verdicts


def triage(questions, ask):
    """
    Ask a model about some words, WORDS_PER_REQUEST at a time.

    An answer with no readable verdicts is sent back once, with what was
    wrong, before its words count as unanswered. Asking stops at the first
    request that fails.

    Args:
        questions (Sequence[Question]): The words to ask about.
        ask (Callable[[list[dict[str, str]]], Reply]): Sends one
            conversation and returns the model's answer (core.ai.chat with a
            connection). Raises AiError when it fails.

    Returns:
        TriageResult: The verdicts, the words left unanswered (all of a
            failed request's and later requests' words included), the tokens
            used and any error.
    """
    verdicts, unanswered = {}, []
    tokens = [0, 0]  # read, written
    error = None

    def asked(messages):
        reply = ask(messages)
        tokens[0] += reply.input_tokens or 0
        tokens[1] += reply.output_tokens or 0
        return reply

    batches = _batches(questions)
    for number, batch in enumerate(batches):
        try:
            found = _ask_batch(batch, asked)
        except AiError as failure:
            error = str(failure)
            unanswered += [q.word.lower() for later in batches[number:] for q in later]
            break
        verdicts.update(found)
        unanswered += [q.word.lower() for q in batch if q.word.lower() not in found]
    return TriageResult(verdicts, unanswered, tokens[0], tokens[1], error)


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
        dict[str, Verdict]: By lowercased word; unreadable entries are left
            out. Empty when there are none.
    """
    verdicts = {}
    for entry in read_entries(path, course_dir):
        try:
            verdict = Verdict(
                word=entry["word"],
                kind=entry["kind"],
                correction=entry["correction"],
                reason=entry["reason"],
                model=entry["model"],
            )
        except (KeyError, TypeError):
            continue
        verdicts[verdict.word] = verdict
    return verdicts


def save_verdicts(path, course_dir, verdicts):
    """
    Remember the verdicts for one course folder, replacing what was
    remembered for it before; other folders' verdicts are kept.

    Args:
        path (Path): The verdict file.
        course_dir (Path): The course folder.
        verdicts (Mapping[str, Verdict]): Everything to remember.
    """
    entries = [
        {
            "word": verdict.word,
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


def _ask_batch(batch, ask):
    """Verdicts for one batch: the answer, or one retry after an unreadable
    one (then none). AiError passes through."""
    messages = messages_for(batch)
    reply = ask(messages)
    try:
        return read_verdicts(reply.text, batch, reply.model)
    except VerdictError as error:
        messages = [
            *messages,
            {"role": "assistant", "content": reply.text},
            {"role": "user", "content": RETRY.format(error=error)},
        ]
    reply = ask(messages)
    try:
        return read_verdicts(reply.text, batch, reply.model)
    except VerdictError:
        return {}


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


def _verdict(entry, model):
    """One entry as a Verdict, or None when it is unusable."""
    if not isinstance(entry, dict):
        return None
    word, kind = entry.get("word"), entry.get("verdict")
    if not isinstance(word, str) or not isinstance(kind, str):
        return None
    word, kind = word.strip(), kind.strip().lower()
    reason = entry.get("reason")
    reason = reason.strip() if isinstance(reason, str) else ""
    if kind == KEEP:
        return Verdict(word.lower(), KEEP, None, reason, model)
    correction = entry.get("correction")
    if kind != TYPO or not isinstance(correction, str):
        return None
    correction = correction.strip()
    if not correction or correction == word:
        return None
    return Verdict(word.lower(), TYPO, correction, reason, model)
