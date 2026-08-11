import 'manifest.dart';
import 'move.dart';

/// Everything the reader needs about one imported book: the manifest, the move
/// tree, and the lookups the UI hits on every frame.
///
/// The indexes are built once at load time. The page overlay builder runs for
/// every visible page on every rebuild, so it must never scan the full move
/// list — a 400-page book holds tens of thousands of moves.
class RceBook {
  RceBook({
    required this.manifest,
    required this.games,
    required List<MoveNode> moves,
    required this.sourceFilePath,
  }) : _movesById = {for (final move in moves) move.id: move},
       _gamesById = {for (final game in games) game.id: game},
       _movesByPage = _groupByPage(moves),
       allMoves = List.unmodifiable(moves);

  final RceManifest manifest;
  final List<GameEntry> games;
  final List<MoveNode> allMoves;

  /// Where the source document was unpacked on disk, ready for `pdfrx`.
  final String sourceFilePath;

  final Map<String, MoveNode> _movesById;
  final Map<String, GameEntry> _gamesById;
  final Map<int, List<MoveNode>> _movesByPage;

  static Map<int, List<MoveNode>> _groupByPage(List<MoveNode> moves) {
    final grouped = <int, List<MoveNode>>{};
    for (final move in moves) {
      (grouped[move.page] ??= <MoveNode>[]).add(move);
    }
    return grouped;
  }

  /// Moves printed on [page] (1-based). Empty for a page with no notation.
  List<MoveNode> movesOnPage(int page) => _movesByPage[page] ?? const [];

  MoveNode? moveById(String id) => _movesById[id];

  GameEntry? gameById(String id) => _gamesById[id];

  /// Pages carrying at least one move, in order — used to skip straight to the
  /// next annotated page.
  List<int> get annotatedPages => _movesByPage.keys.toList()..sort();

  /// The position [move] is played from.
  ///
  /// That is its parent's resulting position, or the game's starting position
  /// when [move] opens the line. Returns null when the parent is itself
  /// broken, in which case there is no position to play from.
  String? fenBefore(MoveNode move) {
    final parentId = move.parentId;
    if (parentId == null) return _gamesById[move.gameId]?.initialFen;
    return _movesById[parentId]?.fen;
  }

  /// The line leading to [move], root first, [move] last.
  List<MoveNode> lineTo(MoveNode move) {
    final line = <MoveNode>[move];
    var current = move;
    // A malformed file could hold a parent cycle; the visited set keeps a
    // corrupt archive from hanging the UI.
    final visited = <String>{move.id};
    while (true) {
      final parentId = current.parentId;
      if (parentId == null) break;
      final parent = _movesById[parentId];
      if (parent == null || !visited.add(parent.id)) break;
      line.insert(0, parent);
      current = parent;
    }
    return line;
  }

  /// Direct continuations of [move], main line first.
  List<MoveNode> childrenOf(MoveNode move) =>
      (allMoves.where((m) => m.parentId == move.id).toList()
        ..sort((a, b) => a.variationIndex.compareTo(b.variationIndex)));

  int get brokenCount =>
      allMoves.where((m) => m.status == MoveStatus.broken).length;

  int get uncertainCount =>
      allMoves.where((m) => m.status == MoveStatus.uncertain).length;
}
