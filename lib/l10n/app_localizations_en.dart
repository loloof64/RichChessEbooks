// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get appTitle => 'Rich Chess Ebooks';

  @override
  String get openArchive => 'Open a .rce archive';

  @override
  String get archiveExplanation =>
      'An archive holds the book as it was published, plus the moves the pipeline extracted from it.';

  @override
  String get chooseFile => 'Choose a file';

  @override
  String get opening => 'Opening…';

  @override
  String couldNotOpen(String error) {
    return 'Could not open this file: $error';
  }

  @override
  String get previousPage => 'Previous page';

  @override
  String get nextPage => 'Next page';

  @override
  String pageOf(int page, int count) {
    return 'p. $page / $count';
  }

  @override
  String pageAlone(int page) {
    return 'p. $page';
  }

  @override
  String get goToPage => 'Go to page';

  @override
  String get pageNumber => 'Page number';

  @override
  String get cancel => 'Cancel';

  @override
  String get go => 'Go';

  @override
  String get showMoveZones => 'Show move zones';

  @override
  String get hideMoveZones => 'Hide move zones';

  @override
  String get nextPageWithMoves => 'Next page with moves';

  @override
  String get aboutThisBook => 'About this book';

  @override
  String get summaryFile => 'File';

  @override
  String get summaryNotation => 'Notation';

  @override
  String get summaryGames => 'Games';

  @override
  String get summaryMoves => 'Moves';

  @override
  String get summaryPagesWithMoves => 'Pages with moves';

  @override
  String get summaryNeedsALook => 'Needs a look';

  @override
  String needsALookValue(int broken, int uncertain) {
    return '$broken broken, $uncertain uncertain';
  }

  @override
  String get close => 'Close';

  @override
  String get emptyArchive =>
      'This archive holds no moves. Re-run the pipeline, checking the notation it detected.';

  @override
  String get zoomOut => 'Zoom out';

  @override
  String get zoomIn => 'Zoom in';

  @override
  String get zoomLevel => 'Zoom level';

  @override
  String get zoomWholePage => 'Whole page';

  @override
  String get zoomPageWidth => 'Page width';

  @override
  String get panelHint =>
      'Tap a move or a diagram on the page to see its position here.';

  @override
  String diagramOnPage(int page) {
    return 'Diagram, page $page';
  }

  @override
  String get flipBoard => 'Flip the board';

  @override
  String get whiteToMove => 'White to move';

  @override
  String get blackToMove => 'Black to move';

  @override
  String get moveUnreadable =>
      'This move could not be read: the board shows the last position before it.';

  @override
  String moveRepaired(int confidence) {
    return 'Read after repairing a likely scanning error ($confidence% confidence).';
  }
}
