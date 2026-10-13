PDF-embeddable fonts for CyberQuest certificates.

- ComicNeue-Regular.ttf / ComicNeue-Bold.ttf
  Comic Neue, Copyright 2014 The Comic Neue Project Authors
  (https://github.com/crozynski/comicneue). SIL Open Font License 1.1,
  full text in OFL-ComicNeue.txt.
  Used to match the CyberQuest web body/display look in generated PDFs.

- NotoSansBengali-Regular.ttf / NotoSansBengali-Bold.ttf
  Noto Sans Bengali, Copyright The Noto Project Authors
  (https://github.com/notofonts/bengali). SIL Open Font License 1.1,
  full text in OFL-NotoSansBengali.txt. Downloaded unmodified from
  notofonts/notofonts.github.io (fonts/NotoSansBengali/hinted/ttf).
  Used only for characters Comic Neue cannot draw (for example Bengali
  names), rendered through MuPDF's HTML engine so conjuncts are shaped.

The OFL allows bundling and embedding these fonts in documents. Keep the
license files next to the fonts and do not sell the font files on their own.

Cinzel (used on the marketing demo certificate) was not vendored here due to
download availability; the generator falls back to Comic Neue Bold, then Helvetica.
