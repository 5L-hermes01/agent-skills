# HN Brief — Historical Date Navigation

hn-brief.com has a built-in date picker that lets you load any past date's digest. This is essential for the popularity tracker and any backfill work.

## Date Picker Pattern

1. **Open date picker**: Click the `📅` button in the top-right of the page banner
2. **Navigate months**: Use `◀` (previous) / `▶` (next) buttons to cycle months
3. **Select a day**: Click any numbered day within the current month's grid
4. **Switch view**: After the page loads for that date, click the `"articles"` button for detailed per-story summaries with points/comments

## Browser Steps

```python
# Open hn-brief
browser_navigate("https://hn-brief.com")

# Open date picker
browser_click("@e8")  # The 📅 button ref varies per session

# Navigate to target month — ◀ is usually @e1, ▶ is @e2
# From the date picker snapshot, look for:
#   - button "◀" [ref=@eN]  -- previous month
#   - StaticText "Month YYYY" -- current month display
#   - button "▶" [ref=@eN]  -- next month
browser_click("@e1")  # repeat to go multiple months back

# Click target day — each day is a clickable element with StaticText "NN"
# Days are usually refs @e6 through ~@e36 in sequential order
# Day 1 = @e6, Day 2 = @e7, ..., Day 31 = @e36
browser_click("@e29")  # e.g., for day 24

# Switch to articles view for detailed story data including points/comments
browser_click("@e13")  # The "articles" button ref

# Scroll and extract
browser_scroll("down")
browser_console(expression="document.body.innerText")
```

## Notes

- The date picker refs shift each session (browser Use generates fresh IDs). Always use `browser_snapshot` to discover the current refs.
- The pattern is: find 📅 button → find ◀ button → find day numbers → find "articles" button
- Old dates load the same format as today — points and comments are current values, not snapshots from publication date
- Non-existent dates (e.g., future dates, dates before hn-brief existed) will still load but show empty content
- The `browser_scroll("down")` is important — long date lists may be cut off in the initial viewport
