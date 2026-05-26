---
name: twitterapi-io
description: Access X/Twitter data via twitterapi.io — a third-party proxy API with pay-per-use pricing, no OAuth, and enriched tweet fields (viewCount, bookmarkCount, conversationId, nested quoted/retweeted objects).
version: 1.0.0
author: Hermes Agent
metadata:
  hermes:
    tags: [twitter, x, social-media, api, twitterapi-io]
---

# twitterapi.io

Third-party X/Twitter data API. No OAuth needed for reads — just an `X-API-Key` header. Pay-as-you-go, no rate-limit tiers (free tier: 1 req/5s).

## Authentication

Set the API key in config.yaml or provide inline:
```
X-API-Key: new1_03ba774bd5d7490cb30aaa8f63e6a135
```

Store in config:
```yaml
twitterapi_io:
  api_key: "new1_03ba774bd5d7490cb30aaa8f63e6a135"
```

## Base URL

```
https://api.twitterapi.io/twitter
```

## Pricing

| What | Cost |
|------|------|
| Tweets | $0.15 / 1k (batch or single) |
| User profiles | $0.18 / 1k |
| Follower IDs | $0.0045 / 1k |
| Full follower profiles | $0.01 / 1k |
| Minimum charge | $0.00015 per request |
| Free tier | 1 request per 5 seconds, 429 on exceed |

## Key Endpoints

### Get Tweets by IDs (batch)
```
GET /tweets?tweet_ids=ID1,ID2,ID3
```
Returns array of `tweets`. Accepts 1-100 IDs per call. $0.15/1k tweets.

### Advanced Search
```
GET /tweet/advanced_search?query=...&queryType=Latest&cursor=...
```
Parameters: `query`, `queryType` (Latest/Top), `max_results`, `cursor`. Paginated via `has_next_page` + `next_cursor`.

### Get User Last Tweets
```
GET /user/last_tweets?userName=nickjlange&limit=50
```
Returns recent tweets from a user handle.

### Get User by Username
```
GET /user/by/username?userName=nickjlange
```
Returns full user profile: bio, followers, following, metrics.

### Bookmarks (needs login_cookie)
```
GET /bookmarks/v2
```
Requires prior `/user/login_v2` call to get a login_cookie. Trial: $0.002/call.

### Get Trends
```
GET /trends?woeid=1
```
Global trends by Where On Earth ID.

### Community Endpoints
- `/community/{id}` — info
- `/community/{id}/tweets` — tweets
- `/community/{id}/members` — members

## Response Shape

Each tweet object includes:
```json
{
  "id": "1234567890",
  "text": "Tweet body...",
  "url": "https://x.com/user/status/1234567890",
  "retweetCount": 42,
  "replyCount": 5,
  "likeCount": 128,
  "quoteCount": 3,
  "viewCount": 15720,
  "bookmarkCount": 9,
  "createdAt": "Fri May 22 10:08:01 +0000 2026",
  "lang": "en",
  "isReply": true,
  "isQuote": false,
  "isRetweet": false,
  "inReplyToId": "1234567890",
  "inReplyToUserId": "85225861",
  "inReplyToUsername": "someone",
  "conversationId": "1234567890",
  "author": {
    "userName": "user",
    "name": "User Name",
    "id": "85225861",
    "followers": 5000,
    "following": 200,
    "profilePicture": "...",
    "description": "..."
  },
  "quoted_tweet": { ... },
  "retweeted_tweet": { ... }
}
```

## Comparison with Other X Data Sources

| | xapi.py (X API v2) | x_search (xAI) | twitterapi.io |
|---|---|---|---|
| HTTP Call to | api.x.com/2/... | api.x.ai/v1/responses | api.twitterapi.io/twitter/... |
| Auth | OAuth2 bearer | xAI key / SuperGrok OAuth | X-API-Key header |
| Cost/50 tweets | ~$0.005 or free | ~$0.10+ (LLM inference) | ~$0.0075 |
| Extra fields | few | prose + summaries | viewCount, bookmarks, conversationId, quoted/retweeted nested |
| List tweets | YES | via search | NO (no endpoint) |
| Rate limit | 900 req/15min | xAI limits | 1 req/5s (free) |

## Limitations

- **No list-tweets endpoint** — use xapi.py for that
- Free tier rate-limited: 1 req per 5 seconds
- Bookmarks/write operations need `login_cookie` from a separate login endpoint
- Third-party service — uptime and data freshness depends on twitterapi.io
- CreatedAt format is Unix-style string ("Fri May 22 10:08:01 +0000 2026"), not ISO 8601 like X API v2

## Pitfalls

- Param names are case-sensitive: `tweet_ids` not `tweetId` or `id`
- The `/twitter/` path segment is part of the URL — don't omit it
- Batch endpoint `/tweets` with `tweet_ids` accepts comma-separated IDs in a single query param
- 429 errors mean wait 6+ seconds; implements retry with backoff in wrapper scripts
- Engagement metrics are live snapshots — will differ from xapi.py cached values by timestamp
- **Trailing URL divergence**: The official X API v2 (`xapi.py`) appends `https://t.co/...` to the `text` field for outbound links; twitterapi.io strips them. Content is equivalent; the last few chars will differ. Always verify by comparing first 80–100 chars, not raw equality.
- `viewCount` returns null for very old tweets
- Use `queryType=Latest` for recency, `queryType=Top` for engagement-ranked searches