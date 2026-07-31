# ArXiv Digest Workflows

Custom digest workflows for the arxiv skill. These are environment-specific and
not part of the upstream skill.

---

## Ad-Hoc Paper List Workflow

When the user provides a specific list of arXiv papers (IDs, URLs, or titles)
instead of asking for daily discovery, use this workflow:

### Step 1: Parse the input
Extract arXiv IDs from the user's input. Handle:
- Full URLs: `https://arxiv.org/abs/2402.03300` → `2402.03300`
- Versioned IDs: `2402.03300v1` → `2402.03300`
- Comma or newline-separated lists.

### Step 2: Fetch metadata for specific IDs
Use the arXiv API `id_list` parameter to fetch all papers in one request (max
50 IDs per request):

```bash
curl -s "https://export.arxiv.org/api/query?id_list=2402.03300,2401.12345" | python3 -c "
import sys, xml.etree.ElementTree as ET
ns = {'a': 'http://www.w3.org/2005/Atom'}
root = ET.parse(sys.stdin).getroot()
papers = []
for entry in root.findall('a:entry', ns):
    title = entry.find('a:title', ns).text.strip().replace('\n', ' ')
    arxiv_id = entry.find('a:id', ns).text.strip().split('/abs/')[-1].split('v')[0]
    published = entry.find('a:published', ns).text[:10]
    authors = ', '.join(a.find('a:name', ns).text for a in entry.findall('a:author', ns))
    summary = entry.find('a:summary', ns).text.strip()
    cats = ', '.join(c.get('term') for c in entry.findall('a:category', ns))
    papers.append({'id': arxiv_id, 'title': title, 'authors': authors, 'published': published, 'summary': summary, 'categories': cats})
    print(f'PAPER|{arxiv_id}||{title}||{authors}||{published}||{summary}||{cats}')
"
```

### Step 3: Popularity, Themes, and Jargon
- Fetch Semantic Scholar citation metrics for each paper (skip if published
  <48h ago to avoid rate limits; default to 0).
- Classify each paper using the `unified-digest-themes` skill taxonomy.
- Decode jargon using the `jargon` skill (respecting saturation filters and
  per-digest deduplication).

### Step 4: Format output
Format identically to the daily digest, but use a custom header:
"Ad-Hoc arXiv Digest — [N] Papers". Group by theme, include citation counts,
jargon notes, and a raw links section at the end.

---

## Daily Digest Workflow with Dedup

For cron-driven daily digests, avoid repeating papers across days using a
cache file at `research/arxiv/references/shown_papers.json`.

**Cache format:**
```json
{
  "version": 1,
  "category": "cs.CL",
  "shown_papers": {
    "2605.30334": "2026-06-13",
    "2605.28819": "2026-05-28"
  }
}
```

Each entry maps arXiv ID (version-stripped) → date first shown.

**Workflow:**

### Step 0: Load cache
```bash
cat /opt/data/skills/research/arxiv/references/shown_papers.json
```
If missing, treat as empty `{"shown_papers": {}}`.

### Step 1: Fetch papers (wide window)
Pull 20 papers instead of 10 to have headroom after dedup:
```bash
curl -s "https://export.arxiv.org/api/query?search_query=cat:cs.CL&sortBy=submittedDate&sortOrder=descending&max_results=20"
```
Strip version suffixes from IDs (2605.28819v1 → 2605.28819).

### Step 2: Dedup against cache
Split fetched papers into:
- **New**: arXiv IDs not in `shown_papers`
- **Seen**: arXiv IDs already in `shown_papers`

Target: display 10 papers total.

| New count | Behavior |
|-----------|----------|
| ≥10 | Show 10 newest new papers |
| 1–9 | Show all new papers + fill remaining slots with most recent seen papers, each marked `(previously featured)` |
| 0 | Show header "No new papers submitted today. Recently featured:" + 10 most recent from cache, all marked `(previously featured)` |

If zero new papers, consider marking the entire digest delivery as
low-priority or skip if the channel has sufficient other content.

### Step 3: Update cache
After displaying papers, add all newly-shown papers to `shown_papers` with
today's date. Write to the consumption directory only:
```
/opt/data/skills/research/arxiv/references/shown_papers.json
```

### Step 4: Prune stale entries
Remove cache entries older than 30 days to keep the file small.
