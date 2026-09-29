import 'package:flutter/material.dart';
import 'package:pdfrx/pdfrx.dart';

import 'l10n/app_localizations.dart';
import 'src/ui/library_page.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Loads the PDF rendering backend before any viewer is built.
  await pdfrxFlutterInitialize();
  runApp(const RichChessEbooksApp());
}

class RichChessEbooksApp extends StatelessWidget {
  const RichChessEbooksApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      onGenerateTitle: (context) => AppLocalizations.of(context).appTitle,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF4E6E58),
        brightness: Brightness.light,
      ),
      darkTheme: ThemeData(
        colorSchemeSeed: const Color(0xFF4E6E58),
        brightness: Brightness.dark,
      ),
      home: const LibraryPage(),
    );
  }
}
