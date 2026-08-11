import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:path/path.dart' as p;

import '../model/rce_book.dart';
import '../rce/rce_archive.dart';
import 'reader_page.dart';

/// Entry screen: pick a `.rce` archive and open it.
class LibraryPage extends StatefulWidget {
  const LibraryPage({super.key});

  @override
  State<LibraryPage> createState() => _LibraryPageState();
}

class _LibraryPageState extends State<LibraryPage> {
  bool _loading = false;
  String? _error;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Rich Chess Ebooks')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  Icons.menu_book_outlined,
                  size: 64,
                  color: theme.colorScheme.primary,
                ),
                const SizedBox(height: 16),
                Text(
                  'Open a .rce archive',
                  style: theme.textTheme.headlineSmall,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 8),
                Text(
                  'An archive holds the book as it was published, plus the '
                  'moves the pipeline extracted from it.',
                  style: theme.textTheme.bodyMedium,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 24),
                FilledButton.icon(
                  onPressed: _loading ? null : _pickArchive,
                  icon: _loading
                      ? const SizedBox.square(
                          dimension: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.folder_open),
                  label: Text(_loading ? 'Opening…' : 'Choose a file'),
                ),
                if (_error != null) ...[
                  const SizedBox(height: 24),
                  _ErrorPanel(message: _error!),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _pickArchive() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      // Filtering by extension is unreliable on several platforms — Android
      // in particular has no MIME type for .rce — so anything can be picked
      // and the archive itself decides whether it is valid.
      final selection = await FilePicker.pickFiles(dialogTitle: 'Open a .rce archive');
      final file = selection?.files.singleOrNull;
      if (file == null) return; // cancelled

      final book = await _open(file);
      if (!mounted) return;
      Navigator.of(context).push(
        MaterialPageRoute<void>(builder: (_) => ReaderPage(book: book)),
      );
    } on RceFormatException catch (error) {
      setState(() => _error = error.message);
    } catch (error) {
      setState(() => _error = 'Could not open this file: $error');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<RceBook> _open(PlatformFile file) {
    final path = file.path;
    if (path != null) return RceArchive.open(path);

    final bytes = file.bytes;
    if (bytes == null) {
      throw const RceFormatException('This file could not be read.');
    }
    return RceArchive.openBytes(
      bytes,
      cacheKey: p.basenameWithoutExtension(file.name),
    );
  }
}

class _ErrorPanel extends StatelessWidget {
  const _ErrorPanel({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: theme.colorScheme.errorContainer,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.error_outline, color: theme.colorScheme.onErrorContainer),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              message,
              style: TextStyle(color: theme.colorScheme.onErrorContainer),
            ),
          ),
        ],
      ),
    );
  }
}
