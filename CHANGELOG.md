# Changelog

Every release of the reader app is listed here, newest first. The release workflow
publishes the section matching the pushed tag as the release notes, so a version must
have its section before it is tagged.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions
follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/loloof64/RichChessEbooks/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/loloof64/RichChessEbooks/releases/tag/v0.1.0
