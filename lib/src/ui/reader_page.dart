import 'dart:math';

import 'package:flutter/material.dart';
import '../../l10n/app_localizations.dart';
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

  /// The move or diagram on the board, whichever was tapped last: shown in
  /// the side panel on a wide screen, and marked on the page either way.
  MoveNode? _selected;
  DiagramEntry? _selectedDiagram;

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
        viewerOverlayBuilder: (context, size, handleLinkTap) => [
          PdfViewerScrollThumb(
            controller: _controller,
            orientation: ScrollbarOrientation.right,
          ),
        ],
        pageOverlaysBuilder: (context, pageRectInViewer, page) =>
            buildMoveOverlays(
              book: book,
              page: page,
              pageRectInViewer: pageRectInViewer,
              showZones: _showZones,
              selectedMove: _selected,
              selectedDiagram: _selectedDiagram,
              onMoveTap: (move) => _select(context, wide, move: move),
              onDiagramTap: (diagram) =>
                  _select(context, wide, diagram: diagram),
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
            tooltip: AppLocalizations.of(context).previousPage,
            icon: const Icon(Icons.chevron_left),
            onPressed: _currentPage > 1 ? () => _turn(-1) : null,
          ),
          TextButton.icon(
            icon: const Icon(Icons.menu_book),
            label: Text(
              _controller.isReady
                  ? AppLocalizations.of(
                      context,
                    ).pageOf(_currentPage, _controller.pageCount)
                  : AppLocalizations.of(context).pageAlone(_currentPage),
            ),
            onPressed: () => _askPage(context),
          ),
          IconButton(
            tooltip: AppLocalizations.of(context).nextPage,
            icon: const Icon(Icons.chevron_right),
            onPressed:
                !_controller.isReady || _currentPage < _controller.pageCount
                ? () => _turn(1)
                : null,
          ),
          _ZoomControls(controller: _controller),
          IconButton(
            tooltip: _showZones
                ? AppLocalizations.of(context).hideMoveZones
                : AppLocalizations.of(context).showMoveZones,
            icon: Icon(_showZones ? Icons.visibility : Icons.visibility_off),
            onPressed: () => setState(() => _showZones = !_showZones),
          ),
          IconButton(
            tooltip: AppLocalizations.of(context).nextPageWithMoves,
            icon: const Icon(Icons.skip_next),
            onPressed: book.annotatedPages.isEmpty ? null : _goToNextAnnotated,
          ),
          IconButton(
            tooltip: AppLocalizations.of(context).aboutThisBook,
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
                  child: _selected == null && _selectedDiagram == null
                      ? const _PanelHint()
                      : SingleChildScrollView(
                          padding: const EdgeInsets.only(top: 16),
                          child: BoardSheet(
                            key: ValueKey(_selected ?? _selectedDiagram),
                            book: book,
                            move: _selected,
                            diagram: _selectedDiagram,
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

  Future<void> _select(
    BuildContext context,
    bool wide, {
    MoveNode? move,
    DiagramEntry? diagram,
  }) async {
    setState(() {
      _selected = move;
      _selectedDiagram = diagram;
    });
    if (wide) return;
    await BoardSheet.show(
      context,
      book: widget.book,
      move: move,
      diagram: diagram,
    );
    // The sheet is gone and the board with it: nothing is on it any more. A
    // tap made meanwhile has already replaced the selection and keeps it.
    if (mounted &&
        identical(_selected, move) &&
        identical(_selectedDiagram, diagram)) {
      setState(() {
        _selected = null;
        _selectedDiagram = null;
      });
    }
  }

  Future<void> _askPage(BuildContext context) async {
    final count = _controller.isReady ? _controller.pageCount : null;
    final page = await showDialog<int>(
      context: context,
      builder: (context) => _GoToPageDialog(pageCount: count),
    );
    if (page == null) return;
    await _show(page.clamp(1, count ?? page));
  }

  /// Go to [page]: centred where it fits the view at the current zoom, so a
  /// whole-page zoom keeps the whole page in sight; from its top otherwise.
  /// pdfrx's own top anchor adds margins of its own, and at a zoom fitting
  /// the page to the pixel the foot of the next page fell out of view.
  Future<void> _show(int page) {
    final fits =
        _controller.isReady &&
        (_controller.layout.pageLayouts[page - 1].height +
                    _controller.params.margin * 2) *
                _controller.currentZoom <=
            _controller.viewSize.height + 1;
    return _controller.goToPage(
      pageNumber: page,
      anchor: fits ? PdfPageAnchor.center : null,
    );
  }

  void _turn(int by) {
    final last = _controller.isReady
        ? _controller.pageCount
        : _currentPage + by;
    _show((_currentPage + by).clamp(1, last));
  }

  void _goToNextAnnotated() {
    final pages = widget.book.annotatedPages;
    final next = pages.firstWhere(
      (page) => page > _currentPage,
      // Past the last annotated page, wrap round to the first.
      orElse: () => pages.first,
    );
    _show(next);
  }

  void _showSummary(BuildContext context) {
    final book = widget.book;
    final manifest = book.manifest;
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(AppLocalizations.of(context).aboutThisBook),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _SummaryRow(
              AppLocalizations.of(context).summaryFile,
              manifest.sourceFilename,
            ),
            _SummaryRow(
              AppLocalizations.of(context).summaryNotation,
              manifest.notationStyle.name,
            ),
            _SummaryRow(
              AppLocalizations.of(context).summaryGames,
              '${book.games.length}',
            ),
            _SummaryRow(
              AppLocalizations.of(context).summaryMoves,
              '${book.allMoves.length}',
            ),
            _SummaryRow(
              AppLocalizations.of(context).summaryPagesWithMoves,
              '${book.annotatedPages.length}',
            ),
            _SummaryRow(
              AppLocalizations.of(context).summaryNeedsALook,
              AppLocalizations.of(
                context,
              ).needsALookValue(book.brokenCount, book.uncertainCount),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text(AppLocalizations.of(context).close),
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
            Icon(
              Icons.warning_amber,
              color: theme.colorScheme.onErrorContainer,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                AppLocalizations.of(context).emptyArchive,
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

  /// Menu values standing for a fit rather than a zoom level.
  static const _wholePage = -1.0;
  static const _pageWidth = -2.0;

  Future<void> _set(double zoom) {
    // A fit is the current page's own, framed by the viewer: an overall
    // scale applied about the view's centre left the page's foot cut off.
    final page = controller.pageNumber ?? 1;
    if (zoom == _wholePage) {
      // The zoom that fits the book's largest page, centred on this one:
      // fitted to the page on show, a taller page after it (Grivas' cover
      // is 630 points high, its text pages 654) lost its foot.
      final pages = controller.layout.pageLayouts;
      // The margin around each page is in document units, so it grows with
      // the zoom: it is part of what has to fit, not taken off the view.
      final margin = controller.params.margin * 2;
      final view = controller.viewSize;
      final fit = pages
          .map(
            (r) => min(
              view.width / (r.width + margin),
              view.height / (r.height + margin),
            ),
          )
          .reduce(min);
      return controller.goTo(
        controller.calcMatrixFor(
          pages[page - 1].center,
          zoom: fit,
          viewSize: view,
        ),
      );
    }
    if (zoom == _pageWidth) {
      return controller.goTo(
        controller.calcMatrixFitWidthForPage(pageNumber: page),
      );
    }
    return controller.setZoom(
      controller.centerPosition,
      zoom.clamp(controller.minScale, controller.maxScale),
    );
  }

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
              tooltip: AppLocalizations.of(context).zoomOut,
              icon: const Icon(Icons.zoom_out),
              onPressed: ready ? () => controller.zoomDown() : null,
            ),
            PopupMenuButton<double>(
              tooltip: AppLocalizations.of(context).zoomLevel,
              enabled: ready,
              onSelected: _set,
              itemBuilder: (context) {
                return [
                  PopupMenuItem(
                    value: _wholePage,
                    child: Text(AppLocalizations.of(context).zoomWholePage),
                  ),
                  PopupMenuItem(
                    value: _pageWidth,
                    child: Text(AppLocalizations.of(context).zoomPageWidth),
                  ),
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
              tooltip: AppLocalizations.of(context).zoomIn,
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
          AppLocalizations.of(context).panelHint,
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
      title: Text(AppLocalizations.of(context).goToPage),
      content: TextField(
        controller: _field,
        autofocus: true,
        keyboardType: TextInputType.number,
        decoration: InputDecoration(
          hintText: count == null
              ? AppLocalizations.of(context).pageNumber
              : '1 – $count',
        ),
        onSubmitted: (_) => _submit(),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: Text(AppLocalizations.of(context).cancel),
        ),
        FilledButton(
          onPressed: _submit,
          child: Text(AppLocalizations.of(context).go),
        ),
      ],
    );
  }
}
