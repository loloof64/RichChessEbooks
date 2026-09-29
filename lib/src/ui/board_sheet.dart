import 'dart:async';

import 'package:chessground/chessground.dart';
import 'package:dartchess/dartchess.dart';
import 'package:flutter/material.dart';
import '../../l10n/app_localizations.dart';

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

  /// How long the note about a move the pipeline could not read stays up.
  static const _noticeFor = Duration(seconds: 4);

  late bool _noticeShown = widget.move.status != MoveStatus.ok;
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
                  child: Text(move.label, style: theme.textTheme.headlineSmall),
                ),
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
                _Board(
                  move: move,
                  fen: widget.book.lastKnownFen(move),
                  orientation: _orientation,
                ),
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
  const _Board({required this.move, required this.fen, required this.orientation});

  final MoveNode move;
  final String? fen;
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
            // The UCI comes from the pipeline, so the highlight never depends
            // on re-deriving squares from SAN disambiguation.
            lastMove: move.uci == null || move.fen == null ? null : Move.parse(move.uci!),
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
                  : AppLocalizations.of(context)
                      .moveRepaired((move.confidence * 100).round()),
              style: theme.textTheme.bodySmall?.copyWith(color: colour),
            ),
          ),
        ],
      ),
    );
  }
}
