from koherent.pipeline.judge import (
    JUDGE_SYSTEM_PROMPT,
    JudgeResult,
    build_judge_user_prompt,
    parse_judge_output,
    unsupported_rate,
)


def test_system_prompt_contains_fake_client_json_marker():
    assert "Return ONLY JSON" in JUDGE_SYSTEM_PROMPT


def test_user_prompt_contains_answer_and_context():
    prompt = build_judge_user_prompt("the answer", "[1] ctx")
    assert "the answer" in prompt
    assert "[1] ctx" in prompt


def test_parses_valid_judge_json():
    raw = (
        '{"claims": [{"text": "a", "verdict": "supported"},'
        ' {"text": "b", "verdict": "unsupported"}]}'
    )
    result: JudgeResult = parse_judge_output(raw)
    assert result.parse_error is False
    assert [c.supported for c in result.claims] == [True, False]


def test_parses_json_wrapped_in_code_fence():
    raw = '```json\n{"claims": [{"text": "a", "verdict": "supported"}]}\n```'
    result = parse_judge_output(raw)
    assert result.parse_error is False
    assert len(result.claims) == 1


def test_malformed_output_sets_parse_error():
    result = parse_judge_output("I think the answer is mostly fine.")
    assert result.parse_error is True
    assert result.claims == []


def test_unknown_verdict_sets_parse_error():
    result = parse_judge_output('{"claims": [{"text": "a", "verdict": "maybe"}]}')
    assert result.parse_error is True


def test_unsupported_rate_across_results():
    results = [
        parse_judge_output('{"claims": [{"text": "a", "verdict": "supported"}]}'),
        parse_judge_output(
            '{"claims": [{"text": "b", "verdict": "unsupported"},'
            ' {"text": "c", "verdict": "supported"}]}'
        ),
        parse_judge_output("garbage"),  # excluded from the denominator
    ]
    assert unsupported_rate(results) == 1 / 3


def test_unsupported_rate_with_no_parseable_claims_is_none():
    assert unsupported_rate([parse_judge_output("garbage")]) is None
    assert unsupported_rate([]) is None
