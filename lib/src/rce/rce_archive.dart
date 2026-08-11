import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive.dart';
import 'package:crypto/crypto.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../model/manifest.dart';
import '../model/move.dart';
import '../model/rce_book.dart';

/// Raised when an archive cannot be read. Carries a message meant to be shown
/// to the user, not a stack trace.
class RceFormatException implements Exception {
  const RceFormatException(this.message);

  final String message;

  @override
  String toString() => message;
}

/// Reads `.rce` archives.
///
/// The source document is unpacked to a cache directory because `pdfrx` renders
/// from a file, and re-inflating a 40 MB PDF on every page turn would be
/// wasteful. Everything else is small enough to stay in memory.
class RceArchive {
  const RceArchive._();

  static const _manifestEntry = 'manifest.json';
  static const _movesEntry = 'moves.json';

  /// Opens the archive at [path] and returns the book it describes.
  ///
  /// The extracted source is verified against `manifest.source.sha256`: a
  /// mismatch means the archive was tampered with or truncated, and every box
  /// in it would point somewhere arbitrary.
  static Future<RceBook> open(String path) async {
    final bytes = await File(path).readAsBytes();
    return openBytes(bytes, cacheKey: p.basenameWithoutExtension(path));
  }

  /// Opens an archive already held in memory — the shape file pickers hand
  /// back on platforms with no readable path.
  static Future<RceBook> openBytes(
    Uint8List bytes, {
    required String cacheKey,
  }) async {
    final Archive archive;
    try {
      archive = ZipDecoder().decodeBytes(bytes);
    } catch (error) {
      throw const RceFormatException(
        'This file is not a readable .rce archive.',
      );
    }
    if (archive.isEmpty) {
      // Handed something that is not a ZIP at all — a bare PDF, most likely —
      // the decoder returns an empty archive rather than throwing. Saying so
      // plainly beats complaining about a missing manifest.
      throw const RceFormatException(
        'This file is not a readable .rce archive.',
      );
    }

    final manifest = RceManifest.fromJson(
      _readJsonObject(archive, _manifestEntry),
    );
    if (!manifest.isPdf) {
      // EPUB has no stable coordinates, so its boxes would be meaningless
      // here; it is a separate v2, not an extension of this reader.
      throw RceFormatException(
        'Only PDF-based archives are supported; this one holds '
        '${manifest.mediaType}.',
      );
    }

    final movesJson = _readJsonObject(archive, _movesEntry);
    final games = (movesJson['games'] as List<dynamic>? ?? const [])
        .map((game) => GameEntry.fromJson(game as Map<String, dynamic>))
        .toList();
    final moves = (movesJson['moves'] as List<dynamic>? ?? const [])
        .map((move) => MoveNode.fromJson(move as Map<String, dynamic>))
        .toList();

    final sourceBytes = _readEntry(archive, manifest.sourcePath);
    final digest = sha256.convert(sourceBytes).toString();
    if (digest != manifest.sourceSha256) {
      throw const RceFormatException(
        'The document inside the archive does not match its recorded hash; '
        'the archive is damaged.',
      );
    }

    final sourceFilePath = await _cacheSource(
      sourceBytes,
      cacheKey: cacheKey,
      filename: manifest.sourceFilename,
      digest: digest,
    );

    return RceBook(
      manifest: manifest,
      games: games,
      moves: moves,
      sourceFilePath: sourceFilePath,
    );
  }

  static Future<String> _cacheSource(
    Uint8List bytes, {
    required String cacheKey,
    required String filename,
    required String digest,
  }) async {
    final root = await getApplicationSupportDirectory();
    // The hash is part of the path, so a re-import of a different edition
    // cannot silently reuse the previous file.
    final directory = Directory(
      p.join(root.path, 'books', '${_sanitise(cacheKey)}-${digest.substring(0, 12)}'),
    );
    await directory.create(recursive: true);

    final file = File(p.join(directory.path, _sanitise(filename)));
    if (!file.existsSync() || await file.length() != bytes.length) {
      await file.writeAsBytes(bytes, flush: true);
    }
    return file.path;
  }

  static String _sanitise(String name) =>
      name.replaceAll(RegExp(r'[^A-Za-z0-9._-]'), '_');

  static Uint8List _readEntry(Archive archive, String name) {
    final file = archive.findFile(name);
    final content = file?.readBytes();
    if (content == null) {
      throw RceFormatException('The archive has no "$name" entry.');
    }
    return content;
  }

  static Map<String, dynamic> _readJsonObject(Archive archive, String name) {
    final decoded = jsonDecode(utf8.decode(_readEntry(archive, name)));
    if (decoded is! Map<String, dynamic>) {
      throw RceFormatException('"$name" is not a JSON object.');
    }
    return decoded;
  }
}
