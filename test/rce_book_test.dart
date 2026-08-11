import 'package:flutter_test/flutter_test.dart';
import 'package:rich_chess_ebooks/src/model/manifest.dart';
import 'package:rich_chess_ebooks/src/model/move.dart';
import 'package:rich_chess_ebooks/src/model/rce_book.dart';

import 'support/fixture.dart';

/// These cover the tree navigation the reader relies on. The move list is
/// flat and unordered by contract, so anything that assumes array order is a
/// bug waiting for the first book with variations.
void main() {
  late RceBook book;

  setUp(() {
    book = RceBook(
      manifest: const RceManifest(
        schemaVersion: '1.0.0',
        sourcePath: 'source/book.pdf',
        sourceFilename: 'book.pdf',
        mediaType: 'application/pdf',
        sourceSha256: '0',
        notationStyle: NotationStyle.figurineUnicode,
      ),
      games: [
        GameEntry.fromJson(const {
          'id': 'g1',
          'initial_fen':
              'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
          'root_move_id': 'g1-m1',
        }),
      ],
      moves: sampleMoves.map(MoveNode.fromJson).toList(),
      sourceFilePath: '/tmp/book.pdf',
    );
  });

  group('page lookup', () {
    test('groups moves by the page they are printed on', () {
      expect(
        book.movesOnPage(12).map((m) => m.id),
        ['g1-m1', 'g1-m2', 'g1-m3'],
      );
      expect(book.movesOnPage(13).map((m) => m.id), ['g1-m4', 'g1-m5']);
    });

    test('returns nothing for a page with no notation', () {
      expect(book.movesOnPage(99), isEmpty);
    });

    test('lists annotated pages in order', () {
      expect(book.annotatedPages, [12, 13]);
    });
  });

  group('fenBefore', () {
    test("uses the game's starting position for a first move", () {
      final first = book.moveById('g1-m1')!;

      expect(book.fenBefore(first), startsWith('rnbqkbnr/pppppppp'));
    });

    test("uses the parent's resulting position otherwise", () {
      final second = book.moveById('g1-m2')!;

      expect(book.fenBefore(second), book.moveById('g1-m1')!.fen);
    });

    test('has no position to offer when the parent is broken', () {
      final orphan = MoveNode.fromJson({
        ...sampleMoves.first,
        'id': 'g1-m6',
        'parent_id': 'g1-m5', // the broken move
      });
      final withOrphan = RceBook(
        manifest: book.manifest,
        games: book.games,
        moves: [...book.allMoves, orphan],
        sourceFilePath: book.sourceFilePath,
      );

      expect(withOrphan.fenBefore(orphan), isNull);
    });
  });

  group('tree navigation', () {
    test('walks the line back to the root, root first', () {
      final last = book.moveById('g1-m4')!;

      expect(book.lineTo(last).map((m) => m.san), ['e4', 'e5', 'Nf3']);
    });

    test('lists the main line before its variations', () {
      final first = book.moveById('g1-m1')!;

      final children = book.childrenOf(first);
      expect(children.map((m) => m.san), ['e5', 'c5']);
      expect(children.first.variationIndex, 0);
      expect(children.last.isVariation, isTrue);
    });

    test('survives a parent cycle instead of hanging', () {
      // A corrupt archive should degrade, not freeze the reader.
      final looping = [
        MoveNode.fromJson({...sampleMoves[0], 'parent_id': 'g1-m2'}),
        MoveNode.fromJson({...sampleMoves[1], 'parent_id': 'g1-m1'}),
      ];
      final corrupt = RceBook(
        manifest: book.manifest,
        games: book.games,
        moves: looping,
        sourceFilePath: book.sourceFilePath,
      );

      expect(corrupt.lineTo(looping.first), hasLength(2));
    });
  });

  group('move labels', () {
    test('numbers White with a dot and Black with an ellipsis', () {
      expect(book.moveById('g1-m1')!.label, '1. e4');
      expect(book.moveById('g1-m2')!.label, '1… e5');
      expect(book.moveById('g1-m4')!.label, '2. Nf3');
    });
  });

  test('counts what needs a human look', () {
    expect(book.brokenCount, 1);
    expect(book.uncertainCount, 0);
  });
}
