# Notes

## Snapshot ingestion

`ingest(snapshot)` keeps the whole history of each page. A later snapshot does not erase an earlier copy of the same URL. Pages are keyed by a canonical URL (host without `www.`, no fragment, no trailing slash) so the same document can be followed across downloads.

Markdown is split into passages and into facts. Table rows keep their tier text in the label, and the column header decides whether a percent is APY, APR, dividend rate, or another metric. Short prose such as `6-month certificate APY: 2.95%` or a fee line becomes a fact too. Qualifiers record term, model-year window, balance tier, jumbo, special, and a few product words. Illustrative payment sentences are stored and tagged `example` so a later step can discount them. The fact `template` blanks out amounts so two snapshots of the same sentence can be compared without treating the number as part of the identity.

`snapshot_as_of` is available on the store now because the timeline is known at ingest. `answer()` does not apply it until answer generation is implemented.

The participant website snapshots are not in this repository. CI smokes five synthetic snapshots with the kit's snapshot ids and dates.

## Conflict resolution

`conflicts()` compares facts already stored by `ingest`. A group is one metric plus the term, tier, jumbo/special flag, Roth versus traditional, and model-year window. Balance tiers stay apart because the tier text is part of that identity. APY and dividend on the same row are different metrics; dividend is not reported on its own because it moves with the APY. Facts tagged `example`, and labels longer than a table row, are left out. A spread of more than eight points is treated as two offers, not one fact that changed.

When two model-year windows overlap by at least half of the shorter window, they are the same rate table recorded with a shifted range, such as a calculator still showing 2023–2026 next to a rate sheet showing 2024–2027. Windows that barely touch, such as 2021–2023 and 2023–2026, stay separate, and so do 2021–2023 and 2024–2027.

The winner is chosen from the newest `taken_on`. If that snapshot has several pages, a path containing rate, fee, or pricing beats a path containing calculator, promo, news, blog, guidance, or offer. The resolution string is the value or values on that winning page. A page that lists two tiers under one heading is not reported as a conflict unless some other page or earlier snapshot states a number the winning page does not.

A cell that literally says APR or APY keeps that metric when the column header disagrees. That is what lets a stale calculator table titled "yield" line up with the rate sheet.

## API keys

None. Ingestion and conflict resolution do not call a language model or any other network service.

## Answers

`answer()` calls `snapshot_as_of` and ignores every later snapshot. That is why "as of May 2026" can still report a certificate APY that has since changed, without mentioning the newer number.

Within the chosen snapshot, a rate question is a filter over facts: metric, term, model-year window, jumbo or special, Roth versus traditional, and balance tier. The surviving fact with the highest page score wins. Auto questions prefer `auto-motorcycle-loans`. Mortgage questions prefer `home-loans`. Calculators, switch pages, and guidance pages are scored down so a copied stale table does not win. A program cell that says "30-Year ... $100,000 or less" stays a label, so the loan amount does not erase the term.

Passage answers are used for facts that are not a single rate: hours, addresses, recognition, branch counts, wallets, membership, and phone or URL instructions. The branch count is the number in the boilerplate of the article with the latest dateline in its header, which is where "22" and "23" disagree. Hours, Forbes, and Hy-Vee answers are copied from the page text rather than filled in from memory.

Abstention is the sentence "I don't know; that isn't listed. Please contact us." with `confident=False` and no digits. It is what a 7/1 ARM rate, a construction-loan rate, and Mullan Avenue lobby hours get, because those pages name the topic and do not publish the number.

## Not in this change

The practice-question score is issue #5.
