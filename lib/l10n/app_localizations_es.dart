// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Spanish Castilian (`es`).
class AppLocalizationsEs extends AppLocalizations {
  AppLocalizationsEs([String locale = 'es']) : super(locale);

  @override
  String get appTitle => 'Rich Chess Ebooks';

  @override
  String get openArchive => 'Abrir un archivo .rce';

  @override
  String get archiveExplanation =>
      'Un archivo contiene el libro tal como se publicó, más las jugadas que el pipeline extrajo de él.';

  @override
  String get chooseFile => 'Elegir un archivo';

  @override
  String get opening => 'Abriendo…';

  @override
  String couldNotOpen(String error) {
    return 'No se pudo abrir este archivo: $error';
  }

  @override
  String get previousPage => 'Página anterior';

  @override
  String get nextPage => 'Página siguiente';

  @override
  String pageOf(int page, int count) {
    return 'p. $page / $count';
  }

  @override
  String pageAlone(int page) {
    return 'p. $page';
  }

  @override
  String get goToPage => 'Ir a la página';

  @override
  String get pageNumber => 'Número de página';

  @override
  String get cancel => 'Cancelar';

  @override
  String get go => 'Ir';

  @override
  String get showMoveZones => 'Mostrar las zonas de las jugadas';

  @override
  String get hideMoveZones => 'Ocultar las zonas de las jugadas';

  @override
  String get nextPageWithMoves => 'Siguiente página con jugadas';

  @override
  String get aboutThisBook => 'Acerca del libro';

  @override
  String get summaryFile => 'Archivo';

  @override
  String get summaryNotation => 'Notación';

  @override
  String get summaryGames => 'Partidas';

  @override
  String get summaryMoves => 'Jugadas';

  @override
  String get summaryPagesWithMoves => 'Páginas con jugadas';

  @override
  String get summaryNeedsALook => 'Por revisar';

  @override
  String needsALookValue(int broken, int uncertain) {
    return '$broken ilegibles, $uncertain dudosas';
  }

  @override
  String get close => 'Cerrar';

  @override
  String get emptyArchive =>
      'Este archivo no contiene ninguna jugada. Vuelva a ejecutar el pipeline comprobando la notación detectada.';

  @override
  String get zoomOut => 'Alejar';

  @override
  String get zoomIn => 'Acercar';

  @override
  String get zoomLevel => 'Nivel de zoom';

  @override
  String get zoomWholePage => 'Página completa';

  @override
  String get zoomPageWidth => 'Ancho de página';

  @override
  String get panelHint =>
      'Toque una jugada o un diagrama de la página para ver aquí su posición.';

  @override
  String diagramOnPage(int page) {
    return 'Diagrama, página $page';
  }

  @override
  String get flipBoard => 'Girar el tablero';

  @override
  String get whiteToMove => 'Juegan las blancas';

  @override
  String get blackToMove => 'Juegan las negras';

  @override
  String get moveUnreadable =>
      'No se pudo leer esta jugada: el tablero muestra la última posición conocida antes de ella.';

  @override
  String moveRepaired(int confidence) {
    return 'Leída tras corregir un probable error de escaneo ($confidence % de confianza).';
  }
}
