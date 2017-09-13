import time

from django.http import HttpResponse
from django.views.decorators.cache import cache_page

# @cache_page(3600, cache='filebased')
# @cache_page(3600, cache='memcached')
# @cache_page(3600, cache='diskcache')
def echo(request, value):
    time.sleep(0.1)
    return HttpResponse(value, content_type='text/plain')
