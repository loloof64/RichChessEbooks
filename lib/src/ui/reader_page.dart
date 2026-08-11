import 'package:flutter/material.dart';
import 'package:pdfrx/pdfrx.dart';

import '../model/rce_book.dart';
import 'board_sheet.dart';
import 'move_overlay.dart';

/// The book, rendered as it was published, with a clickable zone over every
/// move the pipeline found.
class ReaderPage extends StatefulWidget {
  const ReaderPage({required this.book, super.key});

  final RceBook book;

  @override
  State<ReaderPage> createState() => _ReaderPageState();
}

class _ReaderPageState extends State<ReaderPage> {
  final _controller = PdfViewerController();

  /// Whether the tap zones are tinted. Off by default: the point is to read
  /// the book, and a page speckled with coloured boxes is not a book. Turning
  /// it on is how you check the pipeline's alignment, and how you find the
  /// moves it flagged.
  bool _showZones = false;

  int _currentPage = 1;

  @override
  Widget build(BuildContext context) {
    final book = widget.book;

    return Scaffold(
      appBar: AppBar(
        title: Text(
          book.manifest.sourceFilename,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        actions: [
          IconButton(
            tooltip: _showZones ? 'Hide move zones' : 'Show move zones',
            icon: Icon(_showZones ? Icons.visibility : Icons.visibility_off),
            onPressed: () => setState(() => _showZones = !_showZones),
          ),
          IconButton(
            tooltip: 'Next page with moves',
            icon: const Icon(Icons.skip_next),
            onPressed: book.annotatedPages.isEmpty ? null : _goToNextAnnotated,
          ),
          IconButton(
            tooltip: 'About this book',
            icon: const Icon(Icons.info_outline),
            onPressed: () => _showSummary(context),
          ),
        ],
      ),
      body: PdfViewer.file(
        book.sourceFilePath,
        controller: _controller,
        params: PdfViewerParams(
          onPageChanged: (page) => _currentPage = page ?? _currentPage,
          pageOverlaysBuilder: (context, pageRectInViewer, page) =>
              buildMoveOverlays(
                book: book,
                page: page,
                pageRectInViewer: pageRectInViewer,
                showZones: _showZones,
                onMoveTap: (move) =>
                    BoardSheet.show(context, book: book, move: move),
              ),
        ),
      ),
      bottomNavigationBar: book.allMoves.isEmpty
          ? const _EmptyBookBanner()
          : null,
    );
  }

  void _goToNextAnnotated() {
    final pages = widget.book.annotatedPages;
    final next = pages.firstWhere(
      (page) => page > _currentPage,
      // Past the last annotated page, wrap round to the first.
      orElse: () => pages.first,
    );
    _controller.goToPage(pageNumber: next);
  }

  void _showSummary(BuildContext context) {
    final book = widget.book;
    final manifest = book.manifest;
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('About this book'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _SummaryRow('File', manifest.sourceFilename),
            _SummaryRow('Notation', manifest.notationStyle.name),
            _SummaryRow('Games', '${book.games.length}'),
            _SummaryRow('Moves', '${book.allMoves.length}'),
            _SummaryRow('Pages with moves', '${book.annotatedPages.length}'),
            _SummaryRow('Needs a look', '${book.brokenCount} broken, '
                '${book.uncertainCount} uncertain'),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }
}

class _SummaryRow extends StatelessWidget {
  const _SummaryRow(this.label, this.value);

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 140,
            child: Text(label, style: Theme.of(context).textTheme.bodySmall),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}

class _EmptyBookBanner extends StatelessWidget {
  const _EmptyBookBanner();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Material(
      color: theme.colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Icon(Icons.warning_amber, color: theme.colorScheme.onErrorContainer),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                'This archive holds no moves. Re-run the pipeline, checking '
                'the notation it detected.',
                style: TextStyle(color: theme.colorScheme.onErrorContainer),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
