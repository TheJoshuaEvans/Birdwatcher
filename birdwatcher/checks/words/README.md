# Built-in word lists

Words the spelling check knows in every course, from the dictionaries VS Code's
Code Spell Checker uses: the `@cspell/dict-*` packages on npm, by Street Side
Software, under the MIT license (each package's license is in `licenses/`).
Refresh them with `uv run python tools/update_word_lists.py`.

`birdwatcher.txt` is kept by hand, for words those dictionaries miss that
any course might use (libraries, data science, everyday tech words); the
refresh leaves it alone. Names and a course's own terms belong in that
course's `cspell.json` instead.

| Package | Version | License | Words |
|---|---|---|---|
| @cspell/dict-software-terms | 5.4.9 | MIT | 4230 |
| @cspell/dict-python | 4.5.3 | MIT | 10559 |
| @cspell/dict-node | 5.0.9 | MIT | 4436 |
| @cspell/dict-typescript | 3.2.3 | MIT | 3685 |
| @cspell/dict-html | 4.0.16 | MIT | 3237 |
| @cspell/dict-css | 4.1.2 | MIT | 1209 |
| @cspell/dict-fullstack | 3.2.9 | MIT | 502 |
| @cspell/dict-companies | 3.2.14 | MIT | 2318 |
| @cspell/dict-data-science | 2.0.17 | MIT | 309 |
| @cspell/dict-filetypes | 3.0.18 | MIT | 397 |
