import responses

from wsj_reader.article import get_article


@responses.activate
def test_article_extracts_articledata(fake_env, fx):
    url = "https://www.wsj.com/finance/test-article-one-aaaa1111"
    responses.add(responses.GET, url, body=fx("article_page.html"),
                  status=200, content_type="text/html")
    out = get_article(url)
    assert out["article_id"] == "WP-WSJ-0000000001"
    assert out["headline"] == "Synthetic test article one"
    assert out["byline"] == "By Test Author"
    assert out["section"] == "Finance"
    assert out["flashline"] == "Finance"
    assert out["summary"] == "Synthetic short summary."
    assert isinstance(out["body"], list)
