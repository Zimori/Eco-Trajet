from bench.latency import summarize


def test_summarize_percentiles():
    result = summarize([float(ms) for ms in range(1, 101)])
    assert result == {"n": 100, "p50": 50.5, "p95": 95.0}
