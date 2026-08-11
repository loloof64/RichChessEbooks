import 'package:chessground/chessground.dart';
import 'package:dartchess/dartchess.dart';
import 'package:flutter/material.dart';

import '../model/move.dart';
import '../model/rce_book.dart';

/// Shows the position a tapped move leads to, on a board that cannot be played
/// on.
///
/// The board is deliberately static: the point is to see what the page is
/// talking about without losing your place in the book. Moving pieces around
/// belongs to an analysis screen, not here.
class BoardSheet extends StatefulWidget {
  const BoardSheet({required this.book, required this.move, super.key});

  final RceBook book;
  final MoveNode move;

  /// Opens the sheet for [move]. Returns when the user dismisses it.
  static Future<void> show(
    BuildContext context, {
    required RceBook book,
    required MoveNode move,
  }) {
    return showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => BoardSheet(book: book, move: move),
    );
  }

  @override
  State<BoardSheet> createState() => _BoardSheetState();
}

class _BoardSheetState extends State<BoardSheet> {
  Side _orientation = Side.white;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final move = widget.move;
    final game = widget.book.gameById(move.gameId);

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(move.label, style: theme.textTheme.headlineSmall),
                      if (game?.title != null)
                        Text(
                          game!.title!,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: theme.textTheme.bodySmall,
                        ),
                    ],
                  ),
                ),
                IconButton(
                  tooltip: 'Flip the board',
                  icon: const Icon(Icons.swap_vert),
                  onPressed: () => setState(() {
                    _orientation = _orientation == Side.white
                        ? Side.black
                        : Side.white;
                  }),
                ),
              ],
            ),
            const SizedBox(height: 12),
            _Board(move: move, orientation: _orientation),
            if (move.status != MoveStatus.ok) ...[
              const SizedBox(height: 12),
              _StatusBanner(move: move),
            ],
            if (move.comment != null) ...[
              const SizedBox(height: 12),
              ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 120),
                child: SingleChildScrollView(
                  child: Text(
                    move.comment!,
                    style: theme.textTheme.bodyMedium,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _Board extends StatelessWidget {
  const _Board({required this.move, required this.orientation});

  final MoveNode move;
  final Side orientation;

  @override
  Widget build(BuildContext context) {
    final fen = move.fen;
    if (fen == null) {
      return const _NoPosition();
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        // Cap the board so it stays fully visible next to the header and
        // comment on a phone in landscape.
        final size = constraints.maxWidth.clamp(0.0, 420.0);
        return Center(
          child: StaticChessboard(
            size: size,
            orientation: orientation,
            fen: fen,
            // The UCI comes from the pipeline, so the highlight never depends
            // on re-deriving squares from SAN disambiguation.
            lastMove: move.uci == null ? null : Move.parse(move.uci!),
            settings: const StaticChessboardSettings(
              enableCoordinates: true,
              animationDuration: Duration.zero,
            ),
          ),
        );
      },
    );
  }
}

class _NoPosition extends StatelessWidget {
  const _NoPosition();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        children: [
          Icon(Icons.help_outline, color: theme.colorScheme.error),
          const SizedBox(height: 8),
          Text(
            'No position for this move',
            style: theme.textTheme.titleMedium,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 4),
          Text(
            'The pipeline could not read it as a legal move, so it has no '
            'board to show yet.',
            style: theme.textTheme.bodySmall,
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}

class _StatusBanner extends StatelessWidget {
  const _StatusBanner({required this.move});

  final MoveNode move;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isBroken = move.status == MoveStatus.broken;
    final colour = isBroken
        ? theme.colorScheme.error
        : theme.colorScheme.tertiary;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: colour.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Icon(
            isBroken ? Icons.error_outline : Icons.info_outline,
            size: 18,
            color: colour,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              isBroken
                  ? 'This move could not be read; check it against the page.'
                  : 'Read after repairing a likely scanning error '
                        '(${(move.confidence * 100).round()}% confidence).',
              style: theme.textTheme.bodySmall?.copyWith(color: colour),
            ),
          ),
        ],
      ),
    );
  }
}
