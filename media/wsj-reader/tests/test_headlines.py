import re

import responses

from wsj_reader.headlines import get_headlines


@responses.activate
def test_headlines_extracts_print_edition(fake_env, fx):
    url_re = re.compile(r"https://www\.wsj\.com/print-edition/\d{8}/frontpage")
    responses.add(responses.GET, url_re, body=fx("print_edition.html"),
                  status=200, content_type="text/html")
    out = get_headlines(edition_date="20260608", limit=10)
    assert out["schema_version"] == 1
    assert out["edition_date"] == "20260608"
    urls = [a["url"] for a in out["articles"]]
    assert "https://www.wsj.com/finance/test-article-one-aaaa1111" in urls
    assert "https://www.wsj.com/business/test-business-cccc3333" in urls
    # Section labels assigned correctly
    front = [a for a in out["articles"] if a["section"] == "front"]
    biz = [a for a in out["articles"] if a["section"] == "business"]
    assert len(front) == 2
    assert len(biz) == 1


@responses.activate
def test_headlines_section_filter(fake_env, fx):
    url_re = re.compile(r"https://www\.wsj\.com/print-edition/\d{8}/frontpage")
    responses.add(responses.GET, url_re, body=fx("print_edition.html"),
                  status=200, content_type="text/html")
    out = get_headlines(edition_date="20260608", section="business")
    assert len(out["articles"]) == 1
    assert out["articles"][0]["section"] == "business"


@responses.activate
def test_headlines_walks_back_when_no_articles(fake_env, fx, monkeypatch):
    """When today's edition is empty, the resolver tries earlier dates."""
    # Empty edition response (no articles).
    empty_html = (
        '<html><script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"articles":[]}}}'
        '</script></html>'
    )
    # Today returns empty, yesterday returns the fixture.
    url_re = re.compile(r"https://www\.wsj\.com/print-edition/(\d{8})/frontpage")
    call_count = {"n": 0}

    def cb(request):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return (200, {"content-type": "text/html"}, empty_html)
        return (200, {"content-type": "text/html"}, fx("print_edition.html"))

    responses.add_callback(responses.GET, url_re, callback=cb)
    out = get_headlines(max_days_back=2)
    assert call_count["n"] == 2
    assert len(out["articles"]) >= 1
