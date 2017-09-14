import bs4, requests, signal, urllib.parse

signal.signal(signal.SIGINT, lambda signum, frame: exit())

root='http://127.0.0.1:8000/'


def get(url):
    "Get url and return response text."
    print(url)
    response = requests.get(url)
    return response.text


def parse(url, text):
    "Parse url with given text and yield links."
    soup = bs4.BeautifulSoup(text, 'lxml')

    for anchor in soup.find_all('a', href=True):
        full_url = urllib.parse.urljoin(url, anchor['href'])
        href, _ = urllib.parse.urldefrag(full_url)

        if href.startswith(root):
            yield href


from collections import deque

def crawl():
    "Crawl root url."
    urls = deque([root])
    results = dict()

    while True:
        try:
            url = urls.popleft()
        except IndexError:
            break

        if url in results:
            continue

        text = get(url)

        for link in parse(url, text):
            urls.append(link)

        results[url] = text


if __name__ == '__main__':
    crawl()
