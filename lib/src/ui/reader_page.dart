import 'package:flutter/material.dart';
import 'package:pdfrx/pdfrx.dart';

import '../model/move.dart';
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

  /// Whether the tap zones are tinted. On by default: without them nothing
  /// says where to tap. Turning them off gives the page back as printed.
  bool _showZones = true;

  int _currentPage = 1;

  /// The move shown in the side panel, on a screen wide enough for one.
  MoveNode? _selected;

  /// Below this width the board opens as a bottom sheet over the page.
  static const _sidePanelMinWidth = 900.0;
  static const _sidePanelWidth = 400.0;

  @override
  Widget build(BuildContext context) {
    final book = widget.book;
    final wide = MediaQuery.sizeOf(context).width >= _sidePanelMinWidth;

    final viewer = PdfViewer.file(
      book.sourceFilePath,
      controller: _controller,
      params: PdfViewerParams(
        onPageChanged: (page) =>
            setState(() => _currentPage = page ?? _currentPage),
        pageOverlaysBuilder: (context, pageRectInViewer, page) =>
            buildMoveOverlays(
              book: book,
              page: page,
              pageRectInViewer: pageRectInViewer,
              showZones: _showZones,
              onMoveTap: (move) => wide
                  ? setState(() => _selected = move)
                  : BoardSheet.show(context, book: book, move: move),
            ),
      ),
    );

    return Scaffold(
      appBar: AppBar(
        title: Text(
          book.manifest.sourceFilename,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        actions: [
          IconButton(
            tooltip: 'Previous page',
            icon: const Icon(Icons.chevron_left),
            onPressed: _currentPage > 1 ? () => _turn(-1) : null,
          ),
          TextButton.icon(
            icon: const Icon(Icons.menu_book),
            label: Text(_controller.isReady
                ? 'p. $_currentPage / ${_controller.pageCount}'
                : 'p. $_currentPage'),
            onPressed: () => _askPage(context),
          ),
          IconButton(
            tooltip: 'Next page',
            icon: const Icon(Icons.chevron_right),
            onPressed: !_controller.isReady ||
                    _currentPage < _controller.pageCount
                ? () => _turn(1)
                : null,
          ),
          _ZoomControls(controller: _controller),
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
      body: wide
          ? Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(child: viewer),
                const VerticalDivider(width: 1),
                SizedBox(
                  width: _sidePanelWidth,
                  child: _selected == null
                      ? const _PanelHint()
                      : SingleChildScrollView(
                          padding: const EdgeInsets.only(top: 16),
                          child: BoardSheet(
                            key: ValueKey(_selected),
                            book: book,
                            move: _selected!,
                          ),
                        ),
                ),
              ],
            )
          : viewer,
      bottomNavigationBar: book.allMoves.isEmpty
          ? const _EmptyBookBanner()
          : null,
    );
  }

  Future<void> _askPage(BuildContext context) async {
    final count = _controller.isReady ? _controller.pageCount : null;
    final page = await showDialog<int>(
      context: context,
      builder: (context) => _GoToPageDialog(pageCount: count),
    );
    if (page == null) return;
    await _controller.goToPage(pageNumber: page.clamp(1, count ?? page));
  }

  void _turn(int by) {
    final last = _controller.isReady ? _controller.pageCount : _currentPage + by;
    _controller.goToPage(pageNumber: (_currentPage + by).clamp(1, last));
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

/// Zoom out, a menu of zoom levels showing the current one, zoom in.
class _ZoomControls extends StatelessWidget {
  const _ZoomControls({required this.controller});

  final PdfViewerController controller;

  static const _levels = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0];

  Future<void> _set(double zoom) => controller.setZoom(
        controller.centerPosition,
        zoom.clamp(controller.minScale, controller.maxScale),
      );

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        final ready = controller.isReady;
        return Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            IconButton(
              tooltip: 'Zoom out',
              icon: const Icon(Icons.zoom_out),
              onPressed: ready ? () => controller.zoomDown() : null,
            ),
            PopupMenuButton<double>(
              tooltip: 'Zoom level',
              enabled: ready,
              onSelected: _set,
              itemBuilder: (context) {
                final alternative = controller.alternativeFitScale;
                final whole = alternative == null || alternative > controller.coverScale
                    ? controller.coverScale
                    : alternative;
                final width = controller.viewSize.width / controller.documentSize.width;
                return [
                  PopupMenuItem(
                    value: whole,
                    child: const Text('Whole page'),
                  ),
                  PopupMenuItem(value: width, child: const Text('Page width')),
                  const PopupMenuDivider(),
                  for (final level in _levels)
                    PopupMenuItem(
                      value: level,
                      child: Text('${(level * 100).round()} %'),
                    ),
                ];
              },
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 4),
                child: Text(
                  ready ? '${(controller.currentZoom * 100).round()} %' : '– %',
                ),
              ),
            ),
            IconButton(
              tooltip: 'Zoom in',
              icon: const Icon(Icons.zoom_in),
              onPressed: ready ? () => controller.zoomUp() : null,
            ),
          ],
        );
      },
    );
  }
}

class _PanelHint extends StatelessWidget {
  const _PanelHint();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Text(
          'Tap a move on the page to see its position here.',
          textAlign: TextAlign.center,
          style: theme.textTheme.bodyMedium,
        ),
      ),
    );
  }
}

/// Asks for a page number. Owns its text controller, so that the controller
/// outlives the dialog's closing animation.
class _GoToPageDialog extends StatefulWidget {
  const _GoToPageDialog({required this.pageCount});

  final int? pageCount;

  @override
  State<_GoToPageDialog> createState() => _GoToPageDialogState();
}

class _GoToPageDialogState extends State<_GoToPageDialog> {
  final _field = TextEditingController();

  @override
  void dispose() {
    _field.dispose();
    super.dispose();
  }

  void _submit() => Navigator.of(context).pop(int.tryParse(_field.text));

  @override
  Widget build(BuildContext context) {
    final count = widget.pageCount;
    return AlertDialog(
      title: const Text('Go to page'),
      content: TextField(
        controller: _field,
        autofocus: true,
        keyboardType: TextInputType.number,
        decoration: InputDecoration(
          hintText: count == null ? 'Page number' : '1 – $count',
        ),
        onSubmitted: (_) => _submit(),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(onPressed: _submit, child: const Text('Go')),
      ],
    );
  }
}
