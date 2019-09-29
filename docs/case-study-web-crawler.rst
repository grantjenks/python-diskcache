Case Study: Web Crawler
=======================

:doc:`DiskCache <index>` version 2.7 added a couple persistent data
structures. Let's see how they're useful with a case study in crawling the
web. Easy enough, right? We'll start with code to retrieve urls:

    >>> from time import sleep
    >>> def get(url):
    ...     "Get data for url."
    ...     sleep(url / 1000.0)
    ...     return str(url)

No, we're not actually crawling the web. Our urls are numbers and we'll simply
go to sleep to simulate downloading a web page.

    >>> get(20)
    '20'

Once we download some data, we'll need to parse it and extract the links.

    >>> from random import randrange, seed
    >>> def parse(data):
    ...     "Parse data and return list of links."
    ...     seed(int(data))
    ...     count = randrange(1, 10)
    ...     return [randrange(100) for _ in range(count)]

Again, we're not really parsing data. We're just returning a list of one to ten
integers between zero and one hundred. In our imaginary web, urls are just
integers.

    >>> parse('20')
    [68, 76, 90, 25, 63, 90, 87, 57, 16]

Alright, this is a pretty basic pattern. The ``get`` function returns data and
the ``parse`` function returns a list of more data to go get. We can use the
deque data type from the standard library's collection module to crawl our web.

    >>> from collections import deque
    >>> def crawl():
    ...     urls = deque([0])
    ...     results = dict()
    ...
    ...     while True:
    ...         try:
    ...             url = urls.popleft()
    ...         except IndexError:
    ...             break
    ...
    ...         if url in results:
    ...             continue
    ...
    ...         data = get(url)
    ...
    ...         for link in parse(data):
    ...             urls.append(link)
    ...
    ...         results[url] = data
    ...
    ...     print('Results: %s' % len(results))

We're doing a breadth-first search crawl of the web. Our initial seed is zero
and we use that to initialize our queue. All the results are stored in a
dictionary mapping url to data. We then iterate by repeatedly popping the first
url from our queue. If we've already visited the url then we continue,
otherwise we get the corresponding data and parse it. The parsed results are
appended to our queue. Finally we store the data in our results
dictionary.

    >>> crawl()
    Results: 99

The results of our current code are ephemeral. All results are lost once the
program terminates. To make the results persistent, we can use :doc:`DiskCache
<index>` data structures and store the results in the local file
system. :doc:`DiskCache <index>` provides both :class:`Deque <diskcache.Deque>`
and :class:`Index <diskcache.Index>` data structures which can replace our urls
and results variables.

    >>> from diskcache import Deque, Index
    >>> def crawl():
    ...     urls = Deque([0], 'data/urls')
    ...     results = Index('data/results')
    ...
    ...     while True:
    ...         try:
    ...             url = urls.popleft()
    ...         except IndexError:
    ...             break
    ...
    ...         if url in results:
    ...             continue
    ...
    ...         data = get(url)
    ...
    ...         for link in parse(data):
    ...             urls.append(link)
    ...
    ...         results[url] = data
    ...
    ...     print('Results: %s' % len(results))

Look familiar? Only three lines changed. The import at the top changed so now
we're using ``diskcache`` rather than the ``collections`` module. Then, when we
initialize the urls and results objects, we pass relative paths to directories
where we want the data stored. Again, let's try it out:

    >>> crawl()
    Results: 99

Our results are now persistent. We can initialize our results index outside of
the crawl function and query it.

    >>> results = Index('data/results')
    >>> len(results)
    99

As an added benefit, our code also now works in parallel.

    >>> results.clear()
    >>> from multiprocessing import Process
    >>> processes = [Process(target=crawl) for _ in range(4)]
    >>> for process in processes:
    ...     process.start()
    >>> for process in processes:
    ...     process.join()
    >>> len(results)
    99

Each of the processes uses the same deque and index to crawl our web. Work is
automatically divided among the processes as they pop urls from the queue. If
this were run as a script then multiple Python processes could be started and
stopped as desired.

Interesting, no? Three simple changes and our code goes from ephemeral and
single-process to persistent and multi-process. Nothing truly new has happened
here but the API is convenient and that makes a huge difference. We're also no
longer constrained by memory. :doc:`DiskCache <index>` makes efficient use of
your disk and you can customize how much memory is used. By default the maximum
memory consumption of deque and index objects is only a few dozen
megabytes. Now our simple script can efficiently process terabytes of data.

Go forth and build and share!
