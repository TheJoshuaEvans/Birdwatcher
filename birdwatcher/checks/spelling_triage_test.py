"""
Contract tests for birdwatcher.checks.spelling_triage.

The model is a fake `ask` function, so no test touches the network.

Joshua Evans, 2026-11-23 (written with Claude Opus 5.5)
"""

import json

import pytest

from birdwatcher.checks.spelling import CHECK
from birdwatcher.checks.spelling_triage import (
    CONTEXT_CHARS,
    KEEP,
    TYPO,
    WORDS_PER_REQUEST,
    Estimate,
    Question,
    Verdict,
    VerdictError,
    ai_fix,
    estimate,
    load_verdicts,
    messages_for,
    questions_for,
    read_verdicts,
    save_verdicts,
    triage,
)
from birdwatcher.core.ai import AiError, Reply
from birdwatcher.core.findings import Finding, Fix, Severity

MODEL = "google/gemma-4-31b-it:free"


def spelling(word, path="docs/page.md", line=1):
    return Finding(
        CHECK, Severity.ERROR, path, line, f"'{word}' is not in the dictionary."
    )


def write(course, path, text):
    file = course / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")
    return file


def question(word, context="", path="docs/page.md"):
    return Question(word, path, context or f"A line with {word} in it.")


def answer(*entries):
    return json.dumps({"verdicts": list(entries)})


def typo(word, correction, reason="a misspelling"):
    return {"word": word, "verdict": "typo", "correction": correction, "reason": reason}


def keep(word, reason="a course term"):
    return {"word": word, "verdict": "keep", "correction": None, "reason": reason}


def reply(text, input_tokens=100, output_tokens=20):
    return Reply(text, MODEL, input_tokens, output_tokens, 1.5)


class FakeModel:
    """Answers each conversation with the next prepared answer (a Reply, or
    an exception to raise) and records the conversations."""

    def __init__(self, *answers):
        self.conversations = []
        self._answers = list(answers)

    def __call__(self, messages):
        self.conversations.append(messages)
        answered = self._answers.pop(0)
        if isinstance(answered, Exception):
            raise answered
        return answered


# questions_for


def test_one_question_per_word_ignoring_case(tmp_path):
    write(tmp_path, "docs/a.md", "The Sonet model.\nAnother sonet here.\n")
    findings = [
        spelling("Sonet", "docs/a.md", 1),
        spelling("sonet", "docs/a.md", 2),
    ]
    assert questions_for(tmp_path, findings) == [
        Question("Sonet", "docs/a.md", "The Sonet model.")
    ]


def test_other_checks_and_findings_without_a_line_are_left_out(tmp_path):
    write(tmp_path, "docs/a.md", "The Sonet model.\n")
    findings = [
        Finding("broken-link", Severity.ERROR, "docs/a.md", 1, "'Sonet' is broken"),
        spelling("Sonet", "docs/a.md", None),
    ]
    assert questions_for(tmp_path, findings) == []


def test_a_long_line_is_cut_around_the_word(tmp_path):
    line = "lead " * 60 + "sckit" + " tail" * 60
    write(tmp_path, "docs/a.md", line + "\n")
    [asked] = questions_for(tmp_path, [spelling("sckit", "docs/a.md", 1)])
    assert len(asked.context) <= CONTEXT_CHARS
    assert "sckit" in asked.context


def test_a_gone_file_gives_an_empty_context(tmp_path):
    assert questions_for(tmp_path, [spelling("sckit", "docs/gone.md", 3)]) == [
        Question("sckit", "docs/gone.md", "")
    ]


# estimate


def test_nothing_to_ask_costs_nothing():
    assert estimate([]) == Estimate(0, 0, 0)


def test_the_estimate_counts_words_and_requests():
    questions = [question(f"word{i}") for i in range(WORDS_PER_REQUEST + 1)]
    cost = estimate(questions)
    assert (cost.words, cost.requests) == (WORDS_PER_REQUEST + 1, 2)
    assert cost.tokens > estimate(questions[:1]).tokens > 0


# messages_for


def test_the_rules_are_the_same_and_the_words_change():
    first = messages_for([question("sckit", "from sckit-learn import tree")])
    second = messages_for([question("Sonet", "Ask Claude Sonet.", "docs/b.md")])
    assert [m["role"] for m in first] == ["system", "user"]
    assert first[0] == second[0]
    for text in ("Sonet", "Ask Claude Sonet.", "docs/b.md"):
        assert text in second[1]["content"]
    assert "sckit" not in second[1]["content"]


# read_verdicts


def test_verdicts_are_read_by_lowercased_word():
    asked = [question("Sonet"), question("subwords")]
    text = answer(typo("Sonet", "Sonnet", "the Claude model"), keep("subwords"))
    assert read_verdicts(text, asked, MODEL) == {
        "sonet": Verdict("sonet", TYPO, "Sonnet", "the Claude model", MODEL),
        "subwords": Verdict("subwords", KEEP, None, "a course term", MODEL),
    }


@pytest.mark.parametrize(
    "wrap",
    [
        lambda body: f"```json\n{body}\n```",
        lambda body: f"Here are my verdicts:\n{body}\nHope that helps!",
        lambda body: json.dumps(json.loads(body)["verdicts"]),
    ],
    ids=["code-fence", "in-a-sentence", "bare-list"],
)
def test_verdicts_are_found_in_common_wrappings(wrap):
    text = wrap(answer(typo("sckit", "scikit")))
    assert read_verdicts(text, [question("sckit")], MODEL)["sckit"].correction == (
        "scikit"
    )


def test_unusable_entries_are_dropped():
    asked = [question("sckit"), question("runing"), question("thaat")]
    text = answer(
        typo("other", "words"),  # not asked about
        {"word": "sckit", "verdict": "maybe", "correction": "scikit", "reason": ""},
        typo("runing", " "),  # blank correction
        typo("thaat", "thaat"),  # unchanged
    )
    assert read_verdicts(text, asked, MODEL) == {}


def test_a_keep_verdict_has_no_correction():
    text = answer({**keep("Papert"), "correction": "Papert"})
    verdict = read_verdicts(text, [question("Papert")], MODEL)["papert"]
    assert verdict.correction is None


@pytest.mark.parametrize(
    "text",
    ["I think they are all typos.", '{"answer": 42}', "42"],
    ids=["no-json", "wrong-shape", "a-number"],
)
def test_an_answer_with_no_verdicts_is_an_error(text):
    with pytest.raises(VerdictError):
        read_verdicts(text, [question("sckit")], MODEL)


# triage


def test_words_are_asked_in_batches_and_tokens_add_up():
    questions = [question(f"wordy{i}") for i in range(WORDS_PER_REQUEST + 1)]
    first = answer(*(keep(q.word) for q in questions[:WORDS_PER_REQUEST]))
    second = answer(keep(questions[-1].word))
    model = FakeModel(reply(first, 100, 20), reply(second, 50, None))
    result = triage(questions, model)
    assert len(model.conversations) == 2
    assert questions[-1].word in model.conversations[1][-1]["content"]
    assert len(result.verdicts) == WORDS_PER_REQUEST + 1
    assert (result.input_tokens, result.output_tokens) == (150, 20)
    assert (result.unanswered, result.error) == ([], None)


def test_words_the_model_skipped_are_unanswered():
    model = FakeModel(reply(answer(keep("subwords"))))
    result = triage([question("subwords"), question("Sonet")], model)
    assert list(result.verdicts) == ["subwords"]
    assert result.unanswered == ["sonet"]


def test_an_unreadable_answer_is_sent_back_once():
    model = FakeModel(reply("Sure! sckit is a typo."), reply(answer(keep("sckit"))))
    result = triage([question("sckit")], model)
    assert len(model.conversations) == 2
    retry = model.conversations[1]
    assert retry[-2] == {"role": "assistant", "content": "Sure! sckit is a typo."}
    assert retry[-1]["role"] == "user"
    assert list(result.verdicts) == ["sckit"]


def test_a_second_unreadable_answer_leaves_its_words_unanswered():
    model = FakeModel(reply("no"), reply("still no"))
    result = triage([question("sckit")], model)
    assert len(model.conversations) == 2
    assert (result.verdicts, result.unanswered) == ({}, ["sckit"])
    assert result.error is None


def test_a_failed_request_stops_asking_and_keeps_earlier_verdicts():
    questions = [question(f"wordy{i}") for i in range(2 * WORDS_PER_REQUEST + 1)]
    first = answer(*(keep(q.word) for q in questions[:WORDS_PER_REQUEST]))
    model = FakeModel(reply(first), AiError("OpenRouter limited the rate."))
    result = triage(questions, model)
    assert len(model.conversations) == 2
    assert len(result.verdicts) == WORDS_PER_REQUEST
    assert len(result.unanswered) == WORDS_PER_REQUEST + 1
    assert result.error == "OpenRouter limited the rate."


def test_nothing_to_ask_sends_nothing():
    model = FakeModel()
    result = triage([], model)
    assert model.conversations == []
    assert (result.verdicts, result.unanswered) == ({}, [])


# ai_fix


def verdict(word, kind=TYPO, correction=None):
    return Verdict(word.lower(), kind, correction, "reason", MODEL)


def test_a_typo_in_prose_gets_a_fix(tmp_path):
    write(tmp_path, "docs/a.md", "Intro\nWe use Claude Sonet here.\n")
    finding = spelling("Sonet", "docs/a.md", 2)
    fix = ai_fix(tmp_path, finding, verdict("Sonet", correction="Sonnet"))
    assert fix == Fix(2, "Sonet", "Sonnet")


def test_a_lowercase_correction_takes_the_words_capital(tmp_path):
    write(tmp_path, "docs/a.md", "Analyatics matter.\n")
    finding = spelling("Analyatics", "docs/a.md", 1)
    fix = ai_fix(tmp_path, finding, verdict("Analyatics", correction="analytics"))
    assert fix == Fix(1, "Analyatics", "Analytics")


def test_a_correction_with_capitals_is_used_as_given(tmp_path):
    write(tmp_path, "docs/a.md", "As pappert said.\n")
    finding = spelling("pappert", "docs/a.md", 1)
    fix = ai_fix(tmp_path, finding, verdict("pappert", correction="Papert"))
    assert fix == Fix(1, "pappert", "Papert")


@pytest.mark.parametrize(
    ("path", "text", "line"),
    [
        ("docs/a.md", "Text\n```python\nimport sckit\n```\n", 3),
        ("docs/a.md", "Run `import sckit` first.\n", 1),
        ("docs/a.py", "import sckit\n", 1),
        ("docs/a.md", "Call sckit_tree now.\n", 1),
    ],
    ids=["code-block", "inline-code", "code-file", "part-of-a-name"],
)
def test_a_typo_in_code_gets_no_fix(tmp_path, path, text, line):
    write(tmp_path, path, text)
    finding = spelling("sckit", path, line)
    assert ai_fix(tmp_path, finding, verdict("sckit", correction="scikit")) is None


def test_no_fix_without_a_typo_verdict(tmp_path):
    write(tmp_path, "docs/a.md", "We use subwords.\n")
    finding = spelling("subwords", "docs/a.md", 1)
    assert ai_fix(tmp_path, finding, None) is None
    assert ai_fix(tmp_path, finding, verdict("subwords", KEEP)) is None


def test_no_fix_for_another_check_or_a_gone_line(tmp_path):
    write(tmp_path, "docs/a.md", "We use Sonet.\n")
    other = Finding("headings", Severity.ERROR, "docs/a.md", 1, "'Sonet' heading")
    gone = spelling("Sonet", "docs/a.md", 7)
    sonnet = verdict("Sonet", correction="Sonnet")
    assert ai_fix(tmp_path, other, sonnet) is None
    assert ai_fix(tmp_path, gone, sonnet) is None


# load_verdicts and save_verdicts


def test_verdicts_are_remembered_per_course(tmp_path):
    store = tmp_path / "verdicts.json"
    one, two = tmp_path / "one", tmp_path / "two"
    sonet = {"sonet": Verdict("sonet", TYPO, "Sonnet", "the model", MODEL)}
    subwords = {"subwords": Verdict("subwords", KEEP, None, "a term", MODEL)}
    save_verdicts(store, one, sonet)
    save_verdicts(store, two, subwords)
    assert load_verdicts(store, one) == sonet
    assert load_verdicts(store, two) == subwords


def test_nothing_remembered_is_empty(tmp_path):
    assert load_verdicts(tmp_path / "verdicts.json", tmp_path) == {}
