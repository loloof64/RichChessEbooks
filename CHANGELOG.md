# Changelog

Every release of the reader app is listed here, newest first. The release workflow
publishes the section matching the pushed tag as the release notes, so a version must
have its section before it is tagged.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions
follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-10-02

### Added

- The move the board is showing is marked on the page with a highlighter stroke; a
  tapped diagram gets an orange frame. The mark shows even with the tap zones hidden.

### Changed

- Only a move that could not be read shows a notice over the board; repaired moves no
  longer do, and the notice no longer describes the board.
- The window opens tall enough to show an A4 page at 100 %.
- The `rce` pipeline reads many more moves correctly, especially in scanned books, shows
  which step it is on, and offers to update itself when a newer version is on GitHub.

### Fixed

- "Whole page" now fits the whole page, including books whose pages differ in size;
  the foot of the page is no longer cut off, including when turning pages.
- A book whose file name has no `.pdf` extension now opens.

## [0.1.0] - 2026-09-30

First release of the reader.

### Added

- Open a `.rce` archive produced by the `rce` pipeline, and read the book exactly as it
  was published.
- Tap a move to see the position it leads to on a static board, with the move
  highlighted.
- Tap zones that stay aligned with the page at any zoom and while scrolling.
- Eye icon: tint the tap zones to show what the pipeline read cleanly, repaired, or
  could not read.
- Skip icon: jump to the next page carrying moves.
- Interface in English, French and Spanish.
- Packages for Linux (AppImage, deb, rpm), Windows (installer, msi, portable zip) and
  macOS (dmg, zip).

[Unreleased]: https://github.com/loloof64/RichChessEbooks/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/loloof64/RichChessEbooks/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/loloof64/RichChessEbooks/releases/tag/v0.1.0
