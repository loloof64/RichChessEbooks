import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_en.dart';
import 'app_localizations_es.dart';
import 'app_localizations_fr.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
    : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations)!;
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
        delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
      ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('en'),
    Locale('es'),
    Locale('fr'),
  ];

  /// No description provided for @appTitle.
  ///
  /// In en, this message translates to:
  /// **'Rich Chess Ebooks'**
  String get appTitle;

  /// No description provided for @openArchive.
  ///
  /// In en, this message translates to:
  /// **'Open a .rce archive'**
  String get openArchive;

  /// No description provided for @archiveExplanation.
  ///
  /// In en, this message translates to:
  /// **'An archive holds the book as it was published, plus the moves the pipeline extracted from it.'**
  String get archiveExplanation;

  /// No description provided for @chooseFile.
  ///
  /// In en, this message translates to:
  /// **'Choose a file'**
  String get chooseFile;

  /// No description provided for @opening.
  ///
  /// In en, this message translates to:
  /// **'Opening…'**
  String get opening;

  /// No description provided for @couldNotOpen.
  ///
  /// In en, this message translates to:
  /// **'Could not open this file: {error}'**
  String couldNotOpen(String error);

  /// No description provided for @previousPage.
  ///
  /// In en, this message translates to:
  /// **'Previous page'**
  String get previousPage;

  /// No description provided for @nextPage.
  ///
  /// In en, this message translates to:
  /// **'Next page'**
  String get nextPage;

  /// No description provided for @pageOf.
  ///
  /// In en, this message translates to:
  /// **'p. {page} / {count}'**
  String pageOf(int page, int count);

  /// No description provided for @pageAlone.
  ///
  /// In en, this message translates to:
  /// **'p. {page}'**
  String pageAlone(int page);

  /// No description provided for @goToPage.
  ///
  /// In en, this message translates to:
  /// **'Go to page'**
  String get goToPage;

  /// No description provided for @pageNumber.
  ///
  /// In en, this message translates to:
  /// **'Page number'**
  String get pageNumber;

  /// No description provided for @cancel.
  ///
  /// In en, this message translates to:
  /// **'Cancel'**
  String get cancel;

  /// No description provided for @go.
  ///
  /// In en, this message translates to:
  /// **'Go'**
  String get go;

  /// No description provided for @showMoveZones.
  ///
  /// In en, this message translates to:
  /// **'Show move zones'**
  String get showMoveZones;

  /// No description provided for @hideMoveZones.
  ///
  /// In en, this message translates to:
  /// **'Hide move zones'**
  String get hideMoveZones;

  /// No description provided for @nextPageWithMoves.
  ///
  /// In en, this message translates to:
  /// **'Next page with moves'**
  String get nextPageWithMoves;

  /// No description provided for @aboutThisBook.
  ///
  /// In en, this message translates to:
  /// **'About this book'**
  String get aboutThisBook;

  /// No description provided for @summaryFile.
  ///
  /// In en, this message translates to:
  /// **'File'**
  String get summaryFile;

  /// No description provided for @summaryNotation.
  ///
  /// In en, this message translates to:
  /// **'Notation'**
  String get summaryNotation;

  /// No description provided for @summaryGames.
  ///
  /// In en, this message translates to:
  /// **'Games'**
  String get summaryGames;

  /// No description provided for @summaryMoves.
  ///
  /// In en, this message translates to:
  /// **'Moves'**
  String get summaryMoves;

  /// No description provided for @summaryPagesWithMoves.
  ///
  /// In en, this message translates to:
  /// **'Pages with moves'**
  String get summaryPagesWithMoves;

  /// No description provided for @summaryNeedsALook.
  ///
  /// In en, this message translates to:
  /// **'Needs a look'**
  String get summaryNeedsALook;

  /// No description provided for @needsALookValue.
  ///
  /// In en, this message translates to:
  /// **'{broken} broken, {uncertain} uncertain'**
  String needsALookValue(int broken, int uncertain);

  /// No description provided for @close.
  ///
  /// In en, this message translates to:
  /// **'Close'**
  String get close;

  /// No description provided for @emptyArchive.
  ///
  /// In en, this message translates to:
  /// **'This archive holds no moves. Re-run the pipeline, checking the notation it detected.'**
  String get emptyArchive;

  /// No description provided for @zoomOut.
  ///
  /// In en, this message translates to:
  /// **'Zoom out'**
  String get zoomOut;

  /// No description provided for @zoomIn.
  ///
  /// In en, this message translates to:
  /// **'Zoom in'**
  String get zoomIn;

  /// No description provided for @zoomLevel.
  ///
  /// In en, this message translates to:
  /// **'Zoom level'**
  String get zoomLevel;

  /// No description provided for @zoomWholePage.
  ///
  /// In en, this message translates to:
  /// **'Whole page'**
  String get zoomWholePage;

  /// No description provided for @zoomPageWidth.
  ///
  /// In en, this message translates to:
  /// **'Page width'**
  String get zoomPageWidth;

  /// No description provided for @panelHint.
  ///
  /// In en, this message translates to:
  /// **'Tap a move on the page to see its position here.'**
  String get panelHint;

  /// No description provided for @flipBoard.
  ///
  /// In en, this message translates to:
  /// **'Flip the board'**
  String get flipBoard;

  /// No description provided for @moveUnreadable.
  ///
  /// In en, this message translates to:
  /// **'This move could not be read: the board shows the last position before it.'**
  String get moveUnreadable;

  /// No description provided for @moveRepaired.
  ///
  /// In en, this message translates to:
  /// **'Read after repairing a likely scanning error ({confidence}% confidence).'**
  String moveRepaired(int confidence);
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['en', 'es', 'fr'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'en':
      return AppLocalizationsEn();
    case 'es':
      return AppLocalizationsEs();
    case 'fr':
      return AppLocalizationsFr();
  }

  throw FlutterError(
    'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
    'an issue with the localizations generation tool. Please file an issue '
    'on GitHub with a reproducible sample app and the gen-l10n configuration '
    'that was used.',
  );
}
