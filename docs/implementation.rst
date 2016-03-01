DiskCache Implementation
========================

If only we had some kind of file-based database... we do! It's called
SQLite. For metadata and small stuff, use SQLite and for bigger things use
files.

- Leverages SQLite native types: int, float, unicode, blob.
- Small values stored in database
- Use WAL
- Use memory-mapped pages
- Keep transactions short
- Always use an index
