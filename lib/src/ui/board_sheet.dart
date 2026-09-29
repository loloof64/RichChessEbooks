import 'dart:async';

import 'package:chessground/chessground.dart';
import 'package:dartchess/dartchess.dart';
import 'package:flutter/material.dart';

import '../../l10n/app_localizations.dart';
import '../model/move.dart';
import '../model/rce_book.dart';

/// Shows the position a tapped move leads to, or the one a tapped diagram
/// prints, on a board that cannot be played on.
///
/// The board is deliberately static: the point is to see what the page is
/// talking about without losing your place in the book. Moving pieces around
/// belongs to an analysis screen, not here.
class BoardSheet extends StatefulWidget {
  const BoardSheet({required this.book, this.move, this.diagram, super.key})
    : assert((move == null) != (diagram == null), 'a move or a diagram');

  final RceBook book;

  /// What the board shows: one of the two.
  final MoveNode? move;
  final DiagramEntry? diagram;

  /// Opens the sheet for [move] or [diagram]. Returns when it is dismissed.
  static Future<void> show(
    BuildContext context, {
    required RceBook book,
    MoveNode? move,
    DiagramEntry? diagram,
  }) {
    return showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => BoardSheet(book: book, move: move, diagram: diagram),
    );
  }

  @override
  State<BoardSheet> createState() => _BoardSheetState();
}

class _BoardSheetState extends State<BoardSheet> {
  Side _orientation = Side.white;

  /// How long the note about a move the pipeline could not read stays up.
  static const _noticeFor = Duration(seconds: 4);

  late bool _noticeShown =
      widget.move != null && widget.move!.status != MoveStatus.ok;
  Timer? _noticeTimer;

  @override
  void initState() {
    super.initState();
    if (_noticeShown) {
      _noticeTimer = Timer(_noticeFor, () {
        if (mounted) setState(() => _noticeShown = false);
      });
    }
  }

  @override
  void dispose() {
    _noticeTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final move = widget.move;
    final diagram = widget.diagram;
    final label =
        move?.label ??
        AppLocalizations.of(context).diagramOnPage(diagram!.page);
    final fen = move != null ? widget.book.lastKnownFen(move) : diagram!.fen;
    // The UCI comes from the pipeline, so the highlight never depends on
    // re-deriving squares from SAN disambiguation.
    final lastMove = move?.uci == null || move?.fen == null
        ? null
        : Move.parse(move!.uci!);
    // Shown only where it is known: a diagram whose side nothing said reads
    // white in its FEN and must not claim it.
    final whiteToMove = move != null ? whiteToMoveIn(fen) : diagram!.whiteToMove;

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
                  child: Text(label, style: theme.textTheme.headlineSmall),
                ),
                if (whiteToMove != null) _SideToMove(whiteToMove: whiteToMove),
                IconButton(
                  tooltip: AppLocalizations.of(context).flipBoard,
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
            Stack(
              alignment: Alignment.bottomCenter,
              children: [
                _Board(fen: fen, lastMove: lastMove, orientation: _orientation),
                if (move != null)
                  IgnorePointer(
                    child: AnimatedOpacity(
                      opacity: _noticeShown ? 1 : 0,
                      duration: const Duration(milliseconds: 300),
                      child: Padding(
                        padding: const EdgeInsets.all(8),
                        child: _StatusBanner(move: move),
                      ),
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _Board extends StatelessWidget {
  const _Board({
    required this.fen,
    required this.lastMove,
    required this.orientation,
  });

  final String? fen;
  final Move? lastMove;
  final Side orientation;

  @override
  Widget build(BuildContext context) {
    final fen = this.fen;
    if (fen == null) {
      return const SizedBox.shrink();
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
            lastMove: lastMove,
            // The move just played, drawn over its two highlighted squares.
            shapes: {
              if (lastMove case NormalMove(:final from, :final to))
                Arrow(color: const Color(0x9915781B), orig: from, dest: to),
            },
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

/// Whose move it is on the board shown: a disc of that side's colour.
class _SideToMove extends StatelessWidget {
  const _SideToMove({required this.whiteToMove});

  final bool whiteToMove;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = AppLocalizations.of(context);
    final label = whiteToMove ? l10n.whiteToMove : l10n.blackToMove;
    return Semantics(
      label: label,
      excludeSemantics: true,
      child: Tooltip(
        message: label,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 16,
              height: 16,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: whiteToMove ? Colors.white : Colors.black,
                border: Border.all(color: theme.colorScheme.outline),
              ),
            ),
            const SizedBox(width: 6),
            Text(label, style: theme.textTheme.bodyMedium),
          ],
        ),
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
        // Opaque: it stands over the board.
        color: theme.colorScheme.surfaceContainerHighest,
        border: Border.all(color: colour),
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
                  ? AppLocalizations.of(context).moveUnreadable
                  : AppLocalizations.of(
                      context,
                    ).moveRepaired((move.confidence * 100).round()),
              style: theme.textTheme.bodySmall?.copyWith(color: colour),
            ),
          ),
        ],
      ),
    );
  }
}
