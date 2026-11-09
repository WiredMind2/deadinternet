# Third-party notices

## `src/deadinternet/propose/lint.py` and `src/deadinternet/propose/slop.json`

Copyright (c) 2026 Jake Schincariol

These files are adapted from
[instagram-agent-skill](https://github.com/Jakeschincariol/instagram-agent-skill),
distributed under the MIT License (below).

- `slop.json` is vendored verbatim.
- `lint.py` adapts `skills/ig-reel/hookscore.py`, `skills/ig-caption/caption.py`,
  and `skills/ig-human/detect.py`: the CLI and rendering were removed and the
  checks kept as pure functions for the propose evaluate loop. One upstream bug
  was fixed in transit: the unit alternatives in `NUMBER_RE` were non-raw
  strings, so their `\b` escapes were literal backspace characters and never
  matched; here they are real word boundaries.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
