/// How the pieces are written in the source book.
enum NotationStyle {
  /// Unicode chess characters, U+2654–U+265F. The only style v1 of the
  /// pipeline parses.
  figurineUnicode,

  /// Latin letters rendered through a font whose glyphs are piece drawings.
  figurineFont,

  /// Plain letters, which alphabet depending on the language.
  letters;

  static NotationStyle parse(String? value) => switch (value) {
    'figurine_unicode' => NotationStyle.figurineUnicode,
    'figurine_font' => NotationStyle.figurineFont,
    _ => NotationStyle.letters,
  };
}

/// Metadata read from `manifest.json`.
class RceManifest {
  const RceManifest({
    required this.schemaVersion,
    required this.sourcePath,
    required this.sourceFilename,
    required this.mediaType,
    required this.sourceSha256,
    required this.notationStyle,
    this.language,
    this.pageCount,
    this.generatorName,
    this.generatorVersion,
  });

  factory RceManifest.fromJson(Map<String, dynamic> json) {
    final source = json['source'] as Map<String, dynamic>;
    final notation = json['notation'] as Map<String, dynamic>? ?? const {};
    final generator = json['generator'] as Map<String, dynamic>? ?? const {};
    return RceManifest(
      schemaVersion: json['schema_version'] as String? ?? '0.0.0',
      sourcePath: source['path'] as String,
      sourceFilename: source['filename'] as String? ?? 'source',
      mediaType: source['media_type'] as String? ?? 'application/octet-stream',
      sourceSha256: source['sha256'] as String,
      notationStyle: NotationStyle.parse(notation['style'] as String?),
      language: notation['language'] as String?,
      pageCount: (source['page_count'] as num?)?.toInt(),
      generatorName: generator['name'] as String?,
      generatorVersion: generator['version'] as String?,
    );
  }

  final String schemaVersion;

  /// Where the original document sits inside the archive. The reader follows
  /// this rather than guessing a filename.
  final String sourcePath;

  final String sourceFilename;
  final String mediaType;

  /// SHA-256 of the original file's bytes, which ties `patches.json` to this
  /// exact edition of the book.
  final String sourceSha256;

  final NotationStyle notationStyle;
  final String? language;
  final int? pageCount;
  final String? generatorName;
  final String? generatorVersion;

  bool get isPdf => mediaType == 'application/pdf';
}
