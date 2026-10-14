# Third-party notices

This project bundles or references the following third-party software.

## Fonts (bundled in `codeflow/assets/fonts/`)

Both fonts are licensed under the SIL Open Font License, Version 1.1. The full license text and copyright
notices are in the `OFL-*.txt` files next to the font files, and are embedded in every generated page's
font data as required for redistribution.

| Font | Copyright | License text |
|---|---|---|
| Schibsted Grotesk | The Schibsted-Grotesk Project Authors | `codeflow/assets/fonts/OFL-schibsted-grotesk.txt` |
| JetBrains Mono | The JetBrains Mono Project Authors | `codeflow/assets/fonts/OFL-jetbrains-mono.txt` |

The woff2 files are the Latin variable-font subsets distributed by [Fontsource](https://fontsource.org).

## Mermaid (loaded from a CDN; optionally embedded)

Generated pages draw diagrams with [Mermaid](https://github.com/mermaid-js/mermaid), MIT License,
Copyright (c) 2014 - 2022 Knut Sveidqvist. It is not stored in this repository. By default the page loads a
pinned version from the jsDelivr CDN. If you generate a page with `--inline-mermaid`, the library is embedded
in that page and the MIT license notice below applies to the embedded copy. The live demo in `docs/index.html`
is generated this way.

```
The MIT License (MIT)

Copyright (c) 2014 - 2022 Knut Sveidqvist

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and
to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions
of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED
TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
IN THE SOFTWARE.
```
