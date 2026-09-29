import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:rich_chess_ebooks/l10n/app_localizations.dart';
import 'package:rich_chess_ebooks/src/model/manifest.dart';
import 'package:rich_chess_ebooks/src/model/move.dart';
import 'package:rich_chess_ebooks/src/model/rce_book.dart';
import 'package:rich_chess_ebooks/src/ui/board_sheet.dart';

import 'support/fixture.dart';

void main() {
  final book = RceBook(
    manifest: const RceManifest(
      schemaVersion: '1.2.0',
      sourcePath: 'source/book.pdf',
      sourceFilename: 'book.pdf',
      mediaType: 'application/pdf',
      sourceSha256: '0',
      notationStyle: NotationStyle.figurineUnicode,
    ),
    games: [
      GameEntry.fromJson(const {
        'id': 'g1',
        'initial_fen': 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
        'root_move_id': 'g1-m1',
      }),
    ],
    moves: sampleMoves.map(MoveNode.fromJson).toList(),
    sourceFilePath: '/tmp/book.pdf',
  );

  testWidgets('shows whose move it is in the side panel', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: Align(
            alignment: Alignment.topLeft,
            child: SizedBox(
              width: 360,
              child: SingleChildScrollView(
                child: BoardSheet(book: book, move: book.allMoves.first),
              ),
            ),
          ),
        ),
      ),
    );

    expect(tester.takeException(), isNull);
    expect(find.text('Black to move'), findsOneWidget);
  });

  testWidgets('switches from move to move and to a diagram', (tester) async {
    final diagram = DiagramEntry.fromJson(const {
      'page': 13,
      'bbox': {'x': 100, 'y': 200, 'w': 180, 'h': 180},
      'fen': '8/8/8/8/8/8/8/K6k b - - 0 1',
    });
    Future<void> show(MoveNode? move, DiagramEntry? d) => tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: SizedBox(
            width: 360,
            child: SingleChildScrollView(
              child: BoardSheet(key: ValueKey(move ?? d), book: book, move: move, diagram: d),
            ),
          ),
        ),
      ),
    );
    for (final move in book.allMoves) {
      await show(move, null);
      await tester.pump(const Duration(seconds: 5));
      expect(tester.takeException(), isNull, reason: move.id);
    }
    await show(null, diagram);
    expect(tester.takeException(), isNull);
  });
}
