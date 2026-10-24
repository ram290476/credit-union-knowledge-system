# Notes

## Snapshot ingestion

`ingest(snapshot)` keeps the whole history of each page. A later snapshot does not erase an earlier copy of the same URL. Pages are keyed by a canonical URL (host without `www.`, no fragment, no trailing slash) so the same document can be followed across downloads.

Markdown is split into passages and into facts. Table rows keep their tier text in the label, and the column header decides whether a percent is APY, APR, dividend rate, or another metric. Short prose such as `6-month certificate APY: 2.95%` or a fee line becomes a fact too. Qualifiers record term, model-year window, balance tier, jumbo, special, and a few product words. Illustrative payment sentences are stored and tagged `example` so a later step can discount them. The fact `template` blanks out amounts so two snapshots of the same sentence can be compared without treating the number as part of the identity.

`snapshot_as_of` is available on the store now because the timeline is known at ingest. `answer()` does not apply it until answer generation is implemented.

The participant website snapshots are not in this repository. CI smokes five synthetic snapshots with the kit's snapshot ids and dates.

## API keys

None. Ingestion does not call a language model or any other network service.

## Not in this change

Conflict grouping and the choice of a winning value are issue #3. Retrieval, citations, abstention when a question is unsupported, and `as_of` inside `answer()` are issue #4. The practice-question score is issue #5.
