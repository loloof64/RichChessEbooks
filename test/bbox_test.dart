import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';
import 'package:rich_chess_ebooks/src/model/bbox.dart';

/// The conversion these tests cover is the project's first identified risk:
/// a clickable zone built from PDF coordinates has to stay over its move at
/// any zoom level. Get the flip wrong and every zone lands mirrored about the
/// page's middle — which looks plausible on a symmetric layout and is wrong
/// everywhere else.
void main() {
  // A4 in points.
  const pageSize = Size(595.0, 842.0);

  group('RceBBox.toPageRect', () {
    test('flips the origin from bottom-left to top-left at 1:1', () {
      const box = RceBBox(x: 72.0, y: 640.0, w: 18.0, h: 10.0);

      final rect = box.toPageRect(pageSize: pageSize, renderedSize: pageSize);

      expect(rect.left, 72.0);
      // The box's bottom edge sits 640 pt above the page bottom, so its top
      // edge is 842 - 640 - 10 = 192 pt below the page top.
      expect(rect.top, 192.0);
      expect(rect.width, 18.0);
      expect(rect.height, 10.0);
    });

    test('scales with the rendered page, so zoom does not shift it', () {
      const box = RceBBox(x: 72.0, y: 640.0, w: 18.0, h: 10.0);
      const zoom = 3.0;
      final rendered = pageSize * zoom;

      final atOne = box.toPageRect(
        pageSize: pageSize,
        renderedSize: pageSize,
      );
      final atThree = box.toPageRect(
        pageSize: pageSize,
        renderedSize: rendered,
      );

      expect(atThree.left, atOne.left * zoom);
      expect(atThree.top, atOne.top * zoom);
      expect(atThree.width, atOne.width * zoom);
      expect(atThree.height, atOne.height * zoom);
    });

    test('a box on the page bottom edge lands at the rendered bottom', () {
      const box = RceBBox(x: 0.0, y: 0.0, w: 10.0, h: 10.0);

      final rect = box.toPageRect(pageSize: pageSize, renderedSize: pageSize);

      expect(rect.bottom, pageSize.height);
    });

    test('a box on the page top edge lands at the rendered top', () {
      const box = RceBBox(x: 0.0, y: 832.0, w: 10.0, h: 10.0);

      final rect = box.toPageRect(pageSize: pageSize, renderedSize: pageSize);

      expect(rect.top, 0.0);
    });

    test('handles a rendered page whose aspect ratio differs slightly', () {
      // Renderers round page sizes to whole pixels, so width and height do not
      // always scale by exactly the same factor.
      const box = RceBBox(x: 100.0, y: 400.0, w: 20.0, h: 10.0);
      const rendered = Size(1190.0, 1685.0);

      final rect = box.toPageRect(pageSize: pageSize, renderedSize: rendered);

      expect(rect.left, closeTo(100.0 * 1190.0 / 595.0, 1e-9));
      expect(rect.top, closeTo((842.0 - 400.0 - 10.0) * 1685.0 / 842.0, 1e-9));
    });
  });

  group('RceBBox.inflate', () {
    test('grows on all four sides and keeps the centre', () {
      const box = RceBBox(x: 72.0, y: 640.0, w: 18.0, h: 10.0);

      final padded = box.inflate(2.0);

      expect(padded.x, 70.0);
      expect(padded.y, 638.0);
      expect(padded.w, 22.0);
      expect(padded.h, 14.0);

      final before = box.toPageRect(pageSize: pageSize, renderedSize: pageSize);
      final after = padded.toPageRect(
        pageSize: pageSize,
        renderedSize: pageSize,
      );
      expect(after.center.dx, closeTo(before.center.dx, 1e-9));
      expect(after.center.dy, closeTo(before.center.dy, 1e-9));
    });
  });

  test('round-trips through JSON', () {
    const box = RceBBox(x: 72.5, y: 640.25, w: 18.0, h: 10.0);

    expect(RceBBox.fromJson(box.toJson()), box);
  });
}
