import 'dart:convert';
import 'dart:typed_data';

import 'package:archive/archive.dart';
import 'package:crypto/crypto.dart';

/// Bytes standing in for the source document.
///
/// The loader hashes this file but never parses it, so anything works — which
/// keeps the tests free of a checked-in binary.
final Uint8List fakePdfBytes = Uint8List.fromList(
  utf8.encode('%PDF-1.7\n% not a real document, only something to hash\n'),
);

/// The first four moves of the Ruy Lopez, plus one variation branching off
/// Black's second move, and one move the pipeline could not read.
const List<Map<String, dynamic>> sampleMoves = [
  {
    'id': 'g1-m1',
    'game_id': 'g1',
    'parent_id': null,
    'san': 'e4',
    'uci': 'e2e4',
    'fen': 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1',
    'ply': 1,
    'page': 12,
    'bbox': {'x': 72.0, 'y': 640.0, 'w': 18.0, 'h': 10.0},
    'variation_index': 0,
    'comment': null,
    'confidence': 1.0,
    'status': 'ok',
  },
  {
    'id': 'g1-m2',
    'game_id': 'g1',
    'parent_id': 'g1-m1',
    'san': 'e5',
    'uci': 'e7e5',
    'fen': 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2',
    'ply': 2,
    'page': 12,
    'bbox': {'x': 96.0, 'y': 640.0, 'w': 18.0, 'h': 10.0},
    'variation_index': 0,
    'comment': 'The classical reply.',
    'confidence': 1.0,
    'status': 'ok',
  },
  {
    'id': 'g1-m3',
    'game_id': 'g1',
    'parent_id': 'g1-m1',
    'san': 'c5',
    'uci': 'c7c5',
    'fen': 'rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2',
    'ply': 2,
    'page': 12,
    'bbox': {'x': 120.0, 'y': 628.0, 'w': 18.0, 'h': 10.0},
    'variation_index': 1,
    'comment': null,
    'confidence': 1.0,
    'status': 'ok',
  },
  {
    'id': 'g1-m4',
    'game_id': 'g1',
    'parent_id': 'g1-m2',
    'san': 'Nf3',
    'uci': 'g1f3',
    'fen': 'rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2',
    'ply': 3,
    'page': 13,
    'bbox': {'x': 72.0, 'y': 600.0, 'w': 24.0, 'h': 10.0},
    'variation_index': 0,
    'comment': null,
    'confidence': 1.0,
    'status': 'ok',
  },
  {
    'id': 'g1-m5',
    'game_id': 'g1',
    'parent_id': 'g1-m4',
    'san': 'Nc8',
    'uci': null,
    'fen': null,
    'ply': 4,
    'page': 13,
    'bbox': {'x': 100.0, 'y': 600.0, 'w': 24.0, 'h': 10.0},
    'variation_index': 0,
    'comment': null,
    'confidence': 0.0,
    'status': 'broken',
  },
];

/// Builds a `.rce` archive in memory.
///
/// [corruptHash] writes a manifest hash that does not match the source, to
/// exercise the integrity check.
Uint8List buildFixtureArchive({
  bool corruptHash = false,
  String mediaType = 'application/pdf',
  List<Map<String, dynamic>> moves = sampleMoves,
}) {
  final digest = sha256.convert(fakePdfBytes).toString();

  final manifest = {
    'schema_version': '1.0.0',
    'source': {
      'path': 'source/book.pdf',
      'filename': 'book.pdf',
      'media_type': mediaType,
      'sha256': corruptHash ? '0' * 64 : digest,
      'page_count': 210,
    },
    'notation': {
      'style': 'figurine_unicode',
      'language': null,
      'confidence': 0.98,
    },
    'generator': {
      'name': 'rce-pipeline',
      'version': '0.1.0',
      'generated_at': '2026-08-11T09:12:00Z',
    },
    'counts': {'games': 1, 'moves': moves.length},
  };

  final movesJson = {
    'schema_version': '1.0.0',
    'games': [
      {
        'id': 'g1',
        'title': 'Ruy Lopez, illustrative game',
        'initial_fen':
            'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
        'root_move_id': 'g1-m1',
        'page_start': 12,
      },
    ],
    'moves': moves,
  };

  final archive = Archive()
    ..addFile(
      ArchiveFile.bytes('source/book.pdf', fakePdfBytes),
    )
    ..addFile(_jsonEntry('manifest.json', manifest))
    ..addFile(_jsonEntry('moves.json', movesJson));

  return Uint8List.fromList(ZipEncoder().encode(archive));
}

ArchiveFile _jsonEntry(String name, Map<String, dynamic> payload) {
  final bytes = utf8.encode(jsonEncode(payload));
  return ArchiveFile.bytes(name, bytes);
}
