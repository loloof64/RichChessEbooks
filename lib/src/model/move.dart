import 'bbox.dart';

/// How much the pipeline trusts a move, as set by its legality pass.
enum MoveStatus {
  /// Legal in the parent position and unambiguous.
  ok,

  /// Accepted after repairing a scanning confusion (`0`/`O`, `1`/`l`, `8`/`B`).
  uncertain,

  /// No legal reading found. [MoveNode.fen] and [MoveNode.uci] are null, but
  /// the move keeps its page and box so the user can find and fix it.
  broken;

  static MoveStatus parse(String? value) => switch (value) {
    'ok' => MoveStatus.ok,
    'uncertain' => MoveStatus.uncertain,
    _ => MoveStatus.broken,
  };
}

/// One move, as a node in the game tree.
///
/// Variations are reconstructed from [parentId]; the order moves appear in
/// `moves.json` carries no meaning.
class MoveNode {
  const MoveNode({
    required this.id,
    required this.gameId,
    required this.parentId,
    required this.san,
    required this.uci,
    required this.fen,
    required this.ply,
    required this.page,
    required this.bbox,
    required this.variationIndex,
    required this.confidence,
    required this.status,
    this.comment,
  });

  factory MoveNode.fromJson(Map<String, dynamic> json) => MoveNode(
    id: json['id'] as String,
    gameId: json['game_id'] as String,
    parentId: json['parent_id'] as String?,
    san: json['san'] as String,
    uci: json['uci'] as String?,
    fen: json['fen'] as String?,
    ply: (json['ply'] as num).toInt(),
    page: (json['page'] as num).toInt(),
    bbox: RceBBox.fromJson(json['bbox'] as Map<String, dynamic>),
    variationIndex: (json['variation_index'] as num).toInt(),
    confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
    status: MoveStatus.parse(json['status'] as String?),
    comment: json['comment'] as String?,
  );

  final String id;
  final String gameId;

  /// The move played immediately before, or null for a game's first move.
  final String? parentId;

  final String san;

  /// Long algebraic form (`e2e4`, `e7e8q`), used to highlight the from/to
  /// squares without re-deriving them from [san]. Null when [status] is
  /// [MoveStatus.broken].
  final String? uci;

  /// The position **after** [san] is played — what the board shows.
  final String? fen;

  /// 1-based half-move index within the game.
  final int ply;

  /// 1-based page number.
  final int page;

  final RceBBox bbox;

  /// 0 on the main line, greater inside a variation.
  final int variationIndex;

  final double confidence;
  final MoveStatus status;
  final String? comment;

  /// True when this move branches away from its parent's main continuation.
  bool get isVariation => variationIndex > 0;

  /// The move number as printed: `12.` for White, `12…` for Black.
  String get numberLabel {
    final fullMove = (ply + 1) ~/ 2;
    return ply.isOdd ? '$fullMove.' : '$fullMove…';
  }

  /// `12. Nf3`, ready to show as a title.
  String get label => '$numberLabel $san';

  MoveNode copyWith({
    String? san,
    String? uci,
    String? fen,
    int? page,
    RceBBox? bbox,
    double? confidence,
    MoveStatus? status,
  }) => MoveNode(
    id: id,
    gameId: gameId,
    parentId: parentId,
    san: san ?? this.san,
    uci: uci ?? this.uci,
    fen: fen ?? this.fen,
    ply: ply,
    page: page ?? this.page,
    bbox: bbox ?? this.bbox,
    variationIndex: variationIndex,
    confidence: confidence ?? this.confidence,
    status: status ?? this.status,
    comment: comment,
  );
}

/// A game found in the book: a root move plus the position it starts from.
class GameEntry {
  const GameEntry({
    required this.id,
    required this.initialFen,
    required this.rootMoveId,
    this.title,
    this.pageStart,
  });

  factory GameEntry.fromJson(Map<String, dynamic> json) => GameEntry(
    id: json['id'] as String,
    initialFen: json['initial_fen'] as String,
    rootMoveId: json['root_move_id'] as String?,
    title: json['title'] as String?,
    pageStart: (json['page_start'] as num?)?.toInt(),
  );

  final String id;

  /// Position before the first move — the standard start unless the book sets
  /// up a study.
  final String initialFen;

  final String? rootMoveId;
  final String? title;
  final int? pageStart;
}
