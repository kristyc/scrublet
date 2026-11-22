# ADR 0003: One name matcher, merged from both apps

Status: accepted (22 Nov 2026)

## Decision

`tacitkit.printed.matches(text, values, whole)` finds known values as documents print them.

- **The first app's matcher is the base, unchanged:**
  - folded matching that ignores case, punctuation, spacing and line breaks;
  - a long prefix for a name cut at a field width;
  - each 4+ letter word of a name alone;
  - a short word only with its marker (A/P, BIN, BINTI, BT and the rest);
  - numbers by their digits, even inside a longer run;
  - letter edges, except for a whole value of 8+ characters glued into the text around it.
- **Added from the second app's matcher, for names of 2+ words with no digits:**
  - any word order, up to 4 words (past that, listed and reversed only);
  - initials on the listed and reversed orders. An initial is a capital with no letter after
    it, at least one 3+ letter word stays whole, and markers are left out. These forms need
    letter edges.
- **Values in `whole`** (a linked app's phrases and holder names) match only as the whole
  phrase, exactly as before. A company phrase must not hide every "Malaysian".
- **The rule kept from the second app:** a lone word beside a name that was hidden ("the
  wrapped piece"). It needs layout or row context, so it stays with that app's document code.
- **Not adopted:** the second app's "no boundary at either end" for words. Glued matching
  applies only to whole values of 8+ characters, so a short word never matches inside another
  word.

## Verification

- On every corpus text, with and without `whole`, every hit the first app's matcher returns is
  returned. With `whole`, the hits are identical. Without it, there are 4 extra hits, all
  reordered or initialled names.
- `variants()` is unchanged.
- **Speed:** with 4,000 letter-only names, it takes about 11 ms per text against 6 ms before.
  The first app's `variants` cache held 4,096 entries, which is below its own 5,000-value cap.
  Past that cap every call recomputed it, which made it about 4 times slower. Both caches now
  hold 8,192.
