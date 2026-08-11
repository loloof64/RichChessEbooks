import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:plugin_platform_interface/plugin_platform_interface.dart';
import 'package:rich_chess_ebooks/src/model/manifest.dart';
import 'package:rich_chess_ebooks/src/model/move.dart';
import 'package:rich_chess_ebooks/src/rce/rce_archive.dart';

import 'support/fixture.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory cacheRoot;

  setUp(() {
    cacheRoot = Directory.systemTemp.createTempSync('rce_test_');
    PathProviderPlatform.instance = _FakePathProvider(cacheRoot.path);
  });

  tearDown(() {
    if (cacheRoot.existsSync()) cacheRoot.deleteSync(recursive: true);
  });

  group('RceArchive.openBytes', () {
    test('reads the manifest, the games and the moves', () async {
      final book = await RceArchive.openBytes(
        buildFixtureArchive(),
        cacheKey: 'book',
      );

      expect(book.manifest.notationStyle, NotationStyle.figurineUnicode);
      expect(book.manifest.sourceFilename, 'book.pdf');
      expect(book.manifest.pageCount, 210);
      expect(book.games, hasLength(1));
      expect(book.games.single.title, 'Ruy Lopez, illustrative game');
      expect(book.allMoves, hasLength(5));
    });

    test('unpacks the source document and leaves it byte-identical', () async {
      final book = await RceArchive.openBytes(
        buildFixtureArchive(),
        cacheKey: 'book',
      );

      final unpacked = File(book.sourceFilePath);
      expect(unpacked.existsSync(), isTrue);
      expect(unpacked.readAsBytesSync(), fakePdfBytes);
    });

    test('rejects an archive whose source does not match its hash', () async {
      expect(
        () => RceArchive.openBytes(
          buildFixtureArchive(corruptHash: true),
          cacheKey: 'book',
        ),
        throwsA(
          isA<RceFormatException>().having(
            (e) => e.message,
            'message',
            contains('damaged'),
          ),
        ),
      );
    });

    test('refuses EPUB, whose coordinates mean nothing to this reader', () {
      expect(
        () => RceArchive.openBytes(
          buildFixtureArchive(mediaType: 'application/epub+zip'),
          cacheKey: 'book',
        ),
        throwsA(isA<RceFormatException>()),
      );
    });

    test('reports a file that is not a ZIP at all', () {
      expect(
        () => RceArchive.openBytes(fakePdfBytes, cacheKey: 'book'),
        throwsA(
          isA<RceFormatException>().having(
            (e) => e.message,
            'message',
            contains('not a readable .rce archive'),
          ),
        ),
      );
    });

    test('parses a broken move without a position', () async {
      final book = await RceArchive.openBytes(
        buildFixtureArchive(),
        cacheKey: 'book',
      );

      final broken = book.moveById('g1-m5')!;
      expect(broken.status, MoveStatus.broken);
      expect(broken.fen, isNull);
      expect(broken.uci, isNull);
      // It still carries geometry, so the user can find it on the page.
      expect(broken.page, 13);
    });
  });
}

class _FakePathProvider extends PathProviderPlatform
    with MockPlatformInterfaceMixin {
  _FakePathProvider(this.root);

  final String root;

  @override
  Future<String?> getApplicationSupportPath() async => root;
}
