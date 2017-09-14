import random, time

from django.http import HttpResponse
from django.views.decorators.cache import cache_page

# @cache_page(3600, cache='filebased')
# @cache_page(3600, cache='memcached')
# @cache_page(3600, cache='diskcache')
def echo(request, value):
    time.sleep(0.1)
    return HttpResponse(value, content_type='text/plain')


def index(request):
    return HttpResponse('<html><a href="/crawl/0">0</a></html>')


def crawl(request, value):
    time.sleep(random.random())
    value = int(value)
    random.seed(value)
    nums = random.sample(range(100), 5)
    link = '<a href="/crawl/{0}">{0}</a><br>'
    links = ''.join(link.format(num) for num in nums)
    return HttpResponse('<html>{}</html>'.format(links))
