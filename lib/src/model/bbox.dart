import 'dart:ui';

/// A box on a PDF page, in the coordinate system of `moves.json`:
/// **PDF user-space points, origin at the bottom-left of the page**, with [y]
/// measuring the box's *bottom* edge.
///
/// Flutter measures from the top-left with y growing downwards, so every use
/// of a box in the UI goes through [toPageRect]. Keeping that conversion in
/// one place is deliberate: an off-by-one-flip here is invisible in tests that
/// only check numbers, and shows up as clickable zones landing a few
/// millimetres above the move.
class RceBBox {
  const RceBBox({
    required this.x,
    required this.y,
    required this.w,
    required this.h,
  });

  factory RceBBox.fromJson(Map<String, dynamic> json) => RceBBox(
    x: (json['x'] as num).toDouble(),
    y: (json['y'] as num).toDouble(),
    w: (json['w'] as num).toDouble(),
    h: (json['h'] as num).toDouble(),
  );

  /// Distance from the left page edge to the box's left edge, in points.
  final double x;

  /// Distance from the **bottom** page edge to the box's **bottom** edge.
  final double y;

  final double w;
  final double h;

  Map<String, dynamic> toJson() => {'x': x, 'y': y, 'w': w, 'h': h};

  /// This box as a rectangle inside a rendered page.
  ///
  /// [pageSize] is the page in points, as reported by `pdfrx`. [renderedSize]
  /// is the size the page currently occupies on screen — it already carries
  /// the viewer's zoom, so a single uniform scale is all that separates the
  /// two spaces and the result stays aligned at any zoom level.
  ///
  /// The returned rectangle is relative to the page's top-left corner, which
  /// is the origin `pdfrx` lays page overlays out in.
  Rect toPageRect({required Size pageSize, required Size renderedSize}) {
    final scaleX = renderedSize.width / pageSize.width;
    final scaleY = renderedSize.height / pageSize.height;
    return Rect.fromLTWH(
      x * scaleX,
      (pageSize.height - y - h) * scaleY, // flip to a top-left origin
      w * scaleX,
      h * scaleY,
    );
  }

  /// Grows the box by [points] on every side.
  ///
  /// A move token is roughly 20 x 10 points — under a finger that is a hard
  /// target, so the tap zone is padded a little beyond the ink.
  RceBBox inflate(double points) => RceBBox(
    x: x - points,
    y: y - points,
    w: w + points * 2,
    h: h + points * 2,
  );

  @override
  String toString() => 'RceBBox($x, $y, $w, $h)';

  @override
  bool operator ==(Object other) =>
      other is RceBBox &&
      other.x == x &&
      other.y == y &&
      other.w == w &&
      other.h == h;

  @override
  int get hashCode => Object.hash(x, y, w, h);
}
