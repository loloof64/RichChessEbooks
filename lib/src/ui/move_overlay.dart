import 'package:flutter/material.dart';
import 'package:pdfrx/pdfrx.dart';

import '../model/move.dart';
import '../model/rce_book.dart';

/// How far beyond the printed ink the tap zone extends, in PDF points.
///
/// A move token is around 20 x 10 points; at typical reading zoom that is a
/// small target for a finger, so the zone is padded a little. Much more than
/// this and neighbouring moves on the same line start to overlap.
const double kTapPaddingInPoints = 2.0;

/// Builds the clickable zones for one page of the book.
///
/// `pdfrx` hands these widgets to a [Stack] already positioned and sized to the
/// rendered page, so the only conversion left is the scale between PDF points
/// and the page's on-screen size. Zoom and scroll are absorbed by the viewer,
/// which is what keeps the zones aligned at any magnification.
List<Widget> buildMoveOverlays({
  required RceBook book,
  required PdfPage page,
  required Rect pageRectInViewer,
  required ValueChanged<MoveNode> onMoveTap,
  required bool showZones,
}) {
  final moves = book.movesOnPage(page.pageNumber);
  if (moves.isEmpty) return const [];

  final pageSize = Size(page.width, page.height);
  final renderedSize = pageRectInViewer.size;

  return [
    for (final move in moves)
      Positioned.fromRect(
        rect: move.bbox
            .inflate(kTapPaddingInPoints)
            .toPageRect(pageSize: pageSize, renderedSize: renderedSize),
        child: _MoveZone(
          move: move,
          showZone: showZones,
          onTap: () => onMoveTap(move),
        ),
      ),
  ];
}

class _MoveZone extends StatelessWidget {
  const _MoveZone({
    required this.move,
    required this.showZone,
    required this.onTap,
  });

  final MoveNode move;
  final bool showZone;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return PdfOverlayInteractionRegion(
      // Returning true consumes the tap. Panning and pinch-zooming still
      // reach the viewer: this region never enters the gesture arena, the
      // viewer classifies the gesture first and only dispatches taps here.
      onTap: (_) {
        onTap();
        return true;
      },
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: showZone
              ? _tint(context, move).withValues(alpha: 0.22)
              : Colors.transparent,
          borderRadius: BorderRadius.circular(2),
          border: showZone
              ? Border.all(color: _tint(context, move), width: 0.8)
              : null,
        ),
      ),
    );
  }

  static Color _tint(BuildContext context, MoveNode move) {
    final scheme = Theme.of(context).colorScheme;
    return switch (move.status) {
      MoveStatus.ok => scheme.primary,
      MoveStatus.uncertain => scheme.tertiary,
      MoveStatus.broken => scheme.error,
    };
  }
}
