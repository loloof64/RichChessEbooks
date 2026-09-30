// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for French (`fr`).
class AppLocalizationsFr extends AppLocalizations {
  AppLocalizationsFr([String locale = 'fr']) : super(locale);

  @override
  String get appTitle => 'Rich Chess Ebooks';

  @override
  String get openArchive => 'Ouvrir une archive .rce';

  @override
  String get archiveExplanation =>
      'Une archive contient le livre tel qu\'il a été publié, et les coups que le pipeline en a extraits.';

  @override
  String get chooseFile => 'Choisir un fichier';

  @override
  String get opening => 'Ouverture…';

  @override
  String couldNotOpen(String error) {
    return 'Impossible d\'ouvrir ce fichier : $error';
  }

  @override
  String get previousPage => 'Page précédente';

  @override
  String get nextPage => 'Page suivante';

  @override
  String pageOf(int page, int count) {
    return 'p. $page / $count';
  }

  @override
  String pageAlone(int page) {
    return 'p. $page';
  }

  @override
  String get goToPage => 'Aller à la page';

  @override
  String get pageNumber => 'Numéro de page';

  @override
  String get cancel => 'Annuler';

  @override
  String get go => 'Aller';

  @override
  String get showMoveZones => 'Afficher les zones des coups';

  @override
  String get hideMoveZones => 'Masquer les zones des coups';

  @override
  String get nextPageWithMoves => 'Page suivante avec des coups';

  @override
  String get aboutThisBook => 'À propos du livre';

  @override
  String get summaryFile => 'Fichier';

  @override
  String get summaryNotation => 'Notation';

  @override
  String get summaryGames => 'Parties';

  @override
  String get summaryMoves => 'Coups';

  @override
  String get summaryPagesWithMoves => 'Pages avec des coups';

  @override
  String get summaryNeedsALook => 'À vérifier';

  @override
  String needsALookValue(int broken, int uncertain) {
    return '$broken illisibles, $uncertain incertains';
  }

  @override
  String get close => 'Fermer';

  @override
  String get emptyArchive =>
      'Cette archive ne contient aucun coup. Relancez le pipeline en vérifiant la notation détectée.';

  @override
  String get zoomOut => 'Dézoomer';

  @override
  String get zoomIn => 'Zoomer';

  @override
  String get zoomLevel => 'Niveau de zoom';

  @override
  String get zoomWholePage => 'Page entière';

  @override
  String get zoomPageWidth => 'Pleine largeur';

  @override
  String get panelHint =>
      'Cliquez sur un coup ou un diagramme de la page pour voir sa position ici.';

  @override
  String diagramOnPage(int page) {
    return 'Diagramme, page $page';
  }

  @override
  String get flipBoard => 'Retourner l\'échiquier';

  @override
  String get whiteToMove => 'Trait aux Blancs';

  @override
  String get blackToMove => 'Trait aux Noirs';

  @override
  String get moveUnreadable => 'Ce coup n\'a pas pu être lu.';

  @override
  String moveRepaired(int confidence) {
    return 'Lu après correction d\'une erreur de lecture probable ($confidence % de confiance).';
  }
}
