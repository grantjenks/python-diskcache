import diskcache

a = diskcache.Cache('/tmp/abcde', sqlite_query_only=True)
print(f'Query-only: ', a.sqlite_query_only)

o = [1, 2, 3, 4]
# a['qq'] = o

for k in a:
    print(k)

o = [1, 2, 3, 4]
a['qqe'] = o

