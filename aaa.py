import diskcache

a = diskcache.Cache('/tmp/abcde', sqlite_query_only=True)

o = [1, 2, 3, 4]
# a['qq'] = o

for k in a:
    print(k)

o = [1, 2, 3, 4]
# a['qqe'] = o
