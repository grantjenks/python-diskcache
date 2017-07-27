import requests
import time

def get(url):
    response = requests.get(url)
    content = response.content
    time.sleep(1)
    return content


import bs4
import urllib.parse as up

def links(root, url, content):
    soup = bs4.BeautifulSoup(content, 'lxml')
    anchors = soup.find_all('a', href=True)
    hrefs = [anchor['href'] for anchor in anchors]
    join_links = [up.urljoin(url, href) for href in hrefs]
    defrag_links = [up.urldefrag(url)[0] for url in join_links]
    root_links = [url for url in defrag_links if url.startswith(root)]
    return root_links


def main1():
    "Single-process, ephemeral."
    root = 'http://www.grantjenks.com'

    results = {}
    urls = [root]

    while urls:
        url = urls.pop()

        if url in results:
            continue

        print(url)
        content = get(url)

        for link in links(root, url, content):
            urls.append(link)

        results[url] = content

    print(len(results))


import diskcache as dc

def main2():
    "Multi-process, persistent."
    root = 'http://www.grantjenks.com'

    results = dc.Index('data/results')
    urls = dc.Queue('data/urls')

    while urls:
        url = urls.pull()

        if url is None or url in results:
            continue

        print(url)
        content = get(url)

        for link in links(root, url, content):
            urls.push(link)

        results[url] = content

    print(len(results))


import diskcache as dc

def main3():
    "Multi-process, persistent, reliable."
    root = 'http://www.grantjenks.com'

    results = dc.Index('data/results')
    urls = dc.Queue('data/urls')

    # TODO

    state = dc.Index('data/state')

    state.setdefault(root, None)

    while True:
        for key in state:
            if state[key] is None:
                urls.push(key)

        while urls:
            url = urls.pull()

            if url is None or url in results:
                continue

            print(url)
            content = get(url)

            for link in links(root, url, content):
                results.setdefault(link, None)
                urls.push(link)

            results[url] = content

    print(len(results))


if __name__ == '__main__':
    main()
